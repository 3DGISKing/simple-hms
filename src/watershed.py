"""Watershed delineation, stream network extraction, and time of concentration."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

# NumPy 2.x removed np.in1d; pysheds uses it. Provide compatibility.
if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

try:
    from pysheds.grid import Grid
except ImportError:
    Grid = None


@dataclass
class WatershedResult:
    """Result of watershed delineation."""

    mask: np.ndarray
    area_km2: float
    cell_size: float
    transform: Any
    snapped_outlet: Tuple[float, float]
    dem: np.ndarray
    fdir: np.ndarray
    acc: np.ndarray
    dem_conditioned: np.ndarray
    stream_network: Dict
    grid: Any = None  # pysheds Grid for HAND (optional)


def delineate_watershed(
    dem_path: str,
    outlet_x: float,
    outlet_y: float,
    snap_threshold: int = 500,
) -> WatershedResult:
    """
    Delineate watershed from DEM and outlet point.

    Parameters
    ----------
    dem_path : str
        Path to DEM GeoTIFF.
    outlet_x, outlet_y : float
        Outlet coordinates (DEM CRS).
    snap_threshold : int
        Min accumulation for snap; outlet snapped to nearest cell with acc > threshold.

    Returns
    -------
    WatershedResult
    """
    if Grid is None:
        raise ImportError("pysheds is required. Install with: pip install pysheds")

    logger.info("  Loading DEM from %s...", dem_path)
    grid = Grid.from_raster(dem_path)
    dem = grid.read_raster(dem_path)
    logger.info("  DEM shape: %s", dem.shape)

    logger.info("  Filling pits...")
    pit_filled = grid.fill_pits(dem)
    logger.info("  Filling depressions...")
    flooded = grid.fill_depressions(pit_filled)
    logger.info("  Resolving flats...")
    dem_cond = grid.resolve_flats(flooded)

    logger.info("  Computing flow direction...")
    fdir = grid.flowdir(dem_cond)
    logger.info("  Computing flow accumulation...")
    acc = grid.accumulation(fdir)

    logger.info("  Snapping outlet to drainage (threshold=%d)...", snap_threshold)
    try:
        x_snap, y_snap = grid.snap_to_mask(acc > snap_threshold, (outlet_x, outlet_y))
    except (IndexError, ValueError) as e:
        raise ValueError(
            f"Outlet ({outlet_x}, {outlet_y}) could not be snapped to drainage. "
            f"Try lower snap_threshold or check coordinates. {e}"
        ) from e
    logger.info("  Snapped outlet: (%.2f, %.2f)", x_snap, y_snap)

    logger.info("  Delineating catchment...")
    catch = grid.catchment(x=x_snap, y=y_snap, fdir=fdir, xytype="coordinate")
    logger.info("  Extracting stream network...")
    stream_network = grid.extract_river_network(fdir, acc > snap_threshold)

    mask = catch > 0
    cell_size = abs(grid.affine.a)
    area_m2 = np.sum(mask) * cell_size * cell_size
    area_km2 = area_m2 / 1e6

    return WatershedResult(
        mask=mask,
        area_km2=area_km2,
        cell_size=cell_size,
        transform=grid.affine,
        snapped_outlet=(float(x_snap), float(y_snap)),
        dem=dem,
        fdir=fdir,
        acc=acc,
        dem_conditioned=dem_cond,
        stream_network=stream_network,
        grid=grid,
    )


def compute_time_of_concentration(
    watershed_mask: np.ndarray,
    dem: np.ndarray,
    stream_network: Dict,
    p2_24hr_mm: float,
    cell_size: float,
    n_manning: float = 0.05,
) -> Tuple[float, float]:
    """
    Estimate time of concentration (hr) and lag (min) using SCS/TR-55.

    Simplified: uses watershed area and mean slope. For full implementation,
    trace longest flow path and segment into sheet/shallow/channel.

    Parameters
    ----------
    watershed_mask : np.ndarray
        Boolean mask of watershed.
    dem : np.ndarray
        Elevation grid (conditioned).
    stream_network : dict
        Stream network GeoJSON (unused in simplified version).
    p2_24hr_mm : float
        2-year 24-hour rainfall (mm).
    cell_size : float
        Cell size (m).
    n_manning : float
        Manning n for channel flow.

    Returns
    -------
    (Tc_hr, lag_min) : tuple
    """
    from .utils import m_to_ft, mm_to_in

    p2_in = mm_to_in(p2_24hr_mm)
    area_cells = np.sum(watershed_mask)
    area_m2 = area_cells * cell_size * cell_size
    area_ft2 = area_m2 * (3.28084 ** 2)

    elev = np.where(watershed_mask, dem, np.nan)
    valid = np.isfinite(elev)
    if not np.any(valid):
        Tc_hr = 0.5
    else:
        elev_min, elev_max = np.nanmin(elev), np.nanmax(elev)
        L_ft = m_to_ft(np.sqrt(area_m2))
        L_ft = min(L_ft, 3000)
        S = max((elev_max - elev_min) / (L_ft * 3.28084), 0.001)
        S_ft = S

        t_sheet_hr = 0.007 * (n_manning * min(L_ft, 300)) ** 0.8 / (
            (p2_in ** 0.5) * (S_ft ** 0.4)
        )
        L_shallow = max(L_ft - 300, 0)
        if L_shallow > 0:
            V_shallow = 16.13 * (S_ft ** 0.5)
            t_shallow_hr = (L_shallow / 3.28084) / (V_shallow * 0.3048) / 3600
        else:
            t_shallow_hr = 0
        Tc_hr = t_sheet_hr + t_shallow_hr
        Tc_hr = max(Tc_hr, 0.1)

    lag_min = 0.6 * Tc_hr * 60
    return (float(Tc_hr), float(lag_min))


def export_watershed_geojson(
    watershed_result: WatershedResult,
    output_path: Union[str, Path],
    dem_path: Optional[str] = None,
) -> dict:
    """
    Export watershed mask as GeoJSON FeatureCollection.

    Parameters
    ----------
    watershed_result : WatershedResult
        Result from delineate_watershed.
    output_path : str or Path
        Path to write GeoJSON file.
    dem_path : str, optional
        Path to DEM for CRS. If None, CRS is omitted from output.

    Returns
    -------
    dict
        GeoJSON FeatureCollection (also written to output_path).
    """
    import rasterio
    from rasterio.features import shapes

    mask = np.asarray(watershed_result.mask).copy().astype(np.uint8)
    transform = watershed_result.transform

    crs = None
    if dem_path is not None:
        with rasterio.open(dem_path) as src:
            crs = src.crs

    def to_jsonable(obj):
        """Convert numpy/scalar types to JSON-serializable Python types."""
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [to_jsonable(v) for v in obj]
        return obj

    features = []
    for geom, value in shapes(mask, transform=transform, connectivity=8):
        if value == 1:  # watershed cells
            features.append({
                "type": "Feature",
                "geometry": to_jsonable(geom),
                "properties": {"value": 1, "area_km2": float(watershed_result.area_km2)},
            })

    fc = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        fc["crs"] = {"type": "name", "properties": {"name": str(crs)}}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(to_jsonable(fc), f, indent=2)

    logger.info("Watershed exported to %s (%d features)", output_path, len(features))
    return fc


def export_stream_network_geojson(
    watershed_result: WatershedResult,
    output_path: Union[str, Path],
    dem_path: Optional[str] = None,
) -> dict:
    """
    Export stream network as GeoJSON FeatureCollection.

    Parameters
    ----------
    watershed_result : WatershedResult
        Result from delineate_watershed (contains stream_network).
    output_path : str or Path
        Path to write GeoJSON file.
    dem_path : str, optional
        Path to DEM for CRS. If None, CRS is omitted from output.

    Returns
    -------
    dict
        GeoJSON FeatureCollection (also written to output_path).
    """
    stream_network = watershed_result.stream_network

    def to_jsonable(obj):
        """Convert numpy/scalar types to JSON-serializable Python types."""
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [to_jsonable(v) for v in obj]
        return obj

    # Handle geojson.FeatureCollection (dict-like) or plain dict
    if hasattr(stream_network, "__geo_interface__"):
        fc = stream_network.__geo_interface__
    elif isinstance(stream_network, dict):
        fc = stream_network
    else:
        fc = dict(stream_network)
    fc = to_jsonable(fc)

    if dem_path is not None:
        import rasterio
        with rasterio.open(dem_path) as src:
            crs = src.crs
        fc["crs"] = {"type": "name", "properties": {"name": str(crs)}}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(fc, f, indent=2)

    n_features = len(fc.get("features", []))
    logger.info("Stream network exported to %s (%d segments)", output_path, n_features)
    return fc
