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


# D8 flow direction: upstream neighbor (dr, dc) flows into (r,c) if its fdir equals:
# (r-1,c): S=4, (r-1,c+1): SW=8, (r,c+1): W=16, (r+1,c+1): NW=32,
# (r+1,c): N=64, (r+1,c-1): NE=128, (r,c-1): E=1, (r-1,c-1): SE=2
_UPSTREAM_NEIGHBORS = [
    (-1, 0, 4), (-1, 1, 8), (0, 1, 16), (1, 1, 32),
    (1, 0, 64), (1, -1, 128), (0, -1, 1), (-1, -1, 2),
]


def _trace_longest_flow_path(
    outlet_row: int,
    outlet_col: int,
    fdir: np.ndarray,
    watershed_mask: np.ndarray,
    cell_size: float,
) -> list:
    """
    Trace longest flow path from watershed boundary to outlet (head to outlet order).

    Uses BFS from outlet to compute flow distance; returns path from head to outlet.
    """
    rows, cols = fdir.shape
    fdir = np.asarray(fdir)
    SQRT2 = 1.4142135623730951

    # BFS: dist[cell] = longest distance from outlet along flow path
    dist = np.full((rows, cols), -np.inf)
    dist[outlet_row, outlet_col] = 0.0
    queue = [(outlet_row, outlet_col)]
    head_row, head_col = outlet_row, outlet_col
    max_dist = 0.0

    for i in range(rows * cols):
        if i >= len(queue):
            break
        r, c = queue[i]
        if not watershed_mask[r, c]:
            continue
        d_here = dist[r, c]
        for dr, dc, required_fdir in _UPSTREAM_NEIGHBORS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and watershed_mask[nr, nc]:
                if int(fdir[nr, nc]) == required_fdir:
                    edge = cell_size * (SQRT2 if dr != 0 and dc != 0 else 1.0)
                    new_dist = d_here + edge
                    if new_dist > dist[nr, nc]:
                        dist[nr, nc] = new_dist
                        queue.append((nr, nc))
                        if new_dist > max_dist:
                            max_dist = new_dist
                            head_row, head_col = nr, nc

    # Trace path from head to outlet (follow flow direction downstream)
    path = [(head_row, head_col)]
    r, c = head_row, head_col
    # D8 downstream: 64=N->(-1,0), 128=NE->(-1,1), 1=E->(0,1), 2=SE->(1,1), 4=S->(1,0), 8=SW->(1,-1), 16=W->(0,-1), 32=NW->(-1,-1)
    dirmap = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}
    while (r, c) != (outlet_row, outlet_col):
        d = int(fdir[r, c])
        if d not in dirmap:
            break
        dr, dc = dirmap[d]
        r, c = r + dr, c + dc
        if 0 <= r < rows and 0 <= c < cols:
            path.append((r, c))
        else:
            break
    return path


def compute_time_of_concentration(
    watershed_mask: np.ndarray,
    dem: np.ndarray,
    stream_network: Dict,
    p2_24hr_mm: float,
    cell_size: float,
    fdir: Optional[np.ndarray] = None,
    acc: Optional[np.ndarray] = None,
    transform: Any = None,
    snapped_outlet: Optional[Tuple[float, float]] = None,
    stream_threshold: int = 500,
    n_manning: float = 0.05,
    shallow_paved: bool = False,
    channel_r_m: float = 0.3,
) -> Tuple[float, float]:
    """
    Estimate time of concentration (hr) and lag (min) using SCS/TR-55.

    Traces longest flow path from watershed boundary to outlet, segments into
    sheet (≤100 m), shallow concentrated (next 300 m), and channel flow;
    applies TR-55 formulas per segment. Falls back to area-based estimate if
    path tracing is not possible (missing fdir/acc/transform/outlet).

    Parameters
    ----------
    watershed_mask : np.ndarray
        Boolean mask of watershed.
    dem : np.ndarray
        Elevation grid (conditioned).
    stream_network : dict
        Stream network GeoJSON (used for stream mask when acc provided).
    p2_24hr_mm : float
        2-year 24-hour rainfall (mm).
    cell_size : float
        Cell size (m).
    fdir : np.ndarray, optional
        D8 flow direction. Required for path-based Tc.
    acc : np.ndarray, optional
        Flow accumulation. Required for stream mask.
    transform : Affine, optional
        Raster transform for outlet coord conversion.
    snapped_outlet : tuple, optional
        (x, y) snapped outlet coordinates.
    stream_threshold : int
        Min accumulation for stream cells (channel segment).
    n_manning : float
        Manning n for channel flow.
    shallow_paved : bool
        Use paved velocity for shallow flow (20.33√S vs 16.13√S).
    channel_r_m : float
        Hydraulic radius (m) for channel flow Manning estimate.

    Returns
    -------
    (Tc_hr, lag_min) : tuple
    """
    from .utils import m_to_ft, mm_to_in

    p2_in = mm_to_in(p2_24hr_mm)
    dem = np.asarray(dem)
    watershed_mask = np.asarray(watershed_mask).astype(bool)

    # Path-based Tc when all required inputs available
    if fdir is not None and acc is not None and transform is not None and snapped_outlet is not None:
        try:
            from rasterio.transform import rowcol
            out_row, out_col = rowcol(transform, snapped_outlet[0], snapped_outlet[1])
            rows, cols = fdir.shape
            if 0 <= out_row < rows and 0 <= out_col < cols and watershed_mask[out_row, out_col]:
                path = _trace_longest_flow_path(
                    out_row, out_col, fdir, watershed_mask, cell_size
                )
                if len(path) >= 2:
                    Tc_hr = _tc_from_path(
                        path, dem, cell_size, p2_in,
                        n_manning, shallow_paved, channel_r_m
                    )
                    if Tc_hr is not None:
                        lag_min = 0.6 * Tc_hr * 60
                        logger.debug(
                            "Tc from flow path: %.3f hr, lag %.1f min",
                            Tc_hr, lag_min
                        )
                        return (float(Tc_hr), float(lag_min))
        except Exception as e:
            logger.debug("Path-based Tc failed, using fallback: %s", e)

    # Fallback: area-based estimate
    area_m2 = np.sum(watershed_mask) * cell_size * cell_size
    elev = np.where(watershed_mask, dem, np.nan)
    if not np.any(np.isfinite(elev)):
        Tc_hr = 0.5
    else:
        elev_min, elev_max = np.nanmin(elev), np.nanmax(elev)
        L_ft = m_to_ft(min(np.sqrt(area_m2), 914.4))
        S = max((elev_max - elev_min) / (L_ft * 0.3048), 0.001)

        t_sheet_hr = 0.007 * (n_manning * min(L_ft, 300)) ** 0.8 / (
            (p2_in ** 0.5) * (S ** 0.4)
        )
        L_shallow = max(L_ft - 300, 0)
        if L_shallow > 0:
            V = 20.33 * (S ** 0.5) if shallow_paved else 16.13 * (S ** 0.5)
            t_shallow_hr = (L_shallow / 3.28084) / (V * 0.3048) / 3600
        else:
            t_shallow_hr = 0.0
        Tc_hr = max(t_sheet_hr + t_shallow_hr, 0.1)

    lag_min = 0.6 * Tc_hr * 60
    return (float(Tc_hr), float(lag_min))


def _tc_from_path(
    path: list,
    dem: np.ndarray,
    cell_size: float,
    p2_in: float,
    n_manning: float,
    shallow_paved: bool,
    channel_r_m: float,
) -> Optional[float]:
    """
    Compute Tc from flow path segments using TR-55 formulas.

    path: list of (row, col) from head to outlet.
    """
    from .utils import m_to_ft

    SQRT2 = 1.4142135623730951
    L_sheet_max = 100.0
    L_shallow_max = 300.0

    # Cumulative length from head
    lengths = [0.0]
    for i in range(1, len(path)):
        r0, c0 = path[i - 1]
        r1, c1 = path[i]
        d = cell_size * (SQRT2 if (r1 - r0) != 0 and (c1 - c0) != 0 else 1.0)
        lengths.append(lengths[-1] + d)

    total_len = lengths[-1]
    if total_len <= 0:
        return None

    elevs = [dem[r, c] for r, c in path]
    if not all(np.isfinite(e) for e in elevs):
        return None

    def slope_for_segment(i_start: int, i_end: int) -> float:
        if i_end <= i_start:
            return 0.001
        L = lengths[i_end] - lengths[i_start]
        if L <= 0:
            return 0.001
        drop = elevs[i_start] - elevs[i_end]
        return max(drop / L, 0.001)

    t_sheet_hr = 0.0
    t_shallow_hr = 0.0
    t_channel_hr = 0.0

    # Sheet: first L_sheet_max m from head
    i = 0
    while i < len(lengths) - 1 and lengths[i + 1] <= L_sheet_max:
        i += 1
    i_sheet_end = i
    if i_sheet_end > 0:
        L_sheet = lengths[i_sheet_end] - lengths[0]
        L_sheet = min(L_sheet, L_sheet_max)
        S_sheet = slope_for_segment(0, i_sheet_end)
        L_ft = m_to_ft(L_sheet)
        t_sheet_hr = 0.007 * (n_manning * L_ft) ** 0.8 / (
            (p2_in ** 0.5) * (S_sheet ** 0.4)
        )

    # Shallow: next L_shallow_max m
    i_start = i_sheet_end
    i = i_start
    L_shallow_done = 0.0
    while i < len(lengths) - 1 and L_shallow_done < L_shallow_max:
        seg = min(lengths[i + 1] - lengths[i], L_shallow_max - L_shallow_done)
        L_shallow_done += lengths[i + 1] - lengths[i]
        i += 1
    i_shallow_end = i
    if i_shallow_end > i_start:
        L_shallow = min(lengths[i_shallow_end] - lengths[i_start], L_shallow_max)
        S_shallow = slope_for_segment(i_start, i_shallow_end)
        V_fts = 20.33 * (S_shallow ** 0.5) if shallow_paved else 16.13 * (S_shallow ** 0.5)
        t_shallow_hr = (m_to_ft(L_shallow) / 3.28084) / (V_fts * 0.3048) / 3600

    # Channel: remainder to outlet
    i_channel_start = i_shallow_end
    if i_channel_start < len(path) - 1:
        L_channel = lengths[-1] - lengths[i_channel_start]
        S_channel = slope_for_segment(i_channel_start, len(path) - 1)
        R_ft = channel_r_m / 0.3048
        V_fts = (1.49 / n_manning) * (R_ft ** (2 / 3)) * (S_channel ** 0.5)
        t_channel_hr = (m_to_ft(L_channel) / 3.28084) / (V_fts * 0.3048) / 3600

    Tc_hr = t_sheet_hr + t_shallow_hr + t_channel_hr
    return max(Tc_hr, 0.1)


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
