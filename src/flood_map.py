"""HAND computation, Q-to-stage conversion, inundation extent."""

import logging
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import rasterio

from .hydrograph import compute_design_hydrograph, compute_design_hydrograph_subbasins
from .watershed import delineate_watershed, subdivide_watershed, WatershedResult

logger = logging.getLogger(__name__)

# D8 flow direction: (64, 128, 1, 2, 4, 8, 16, 32) = N, NE, E, SE, S, SW, W, NW
# Row/col offsets for downstream neighbor (row increases downward)
_D8_OFFSETS = {
    64: (-1, 0),   # N
    128: (-1, 1),  # NE
    1: (0, 1),    # E
    2: (1, 1),    # SE
    4: (1, 0),    # S
    8: (1, -1),   # SW
    16: (0, -1),  # W
    32: (-1, -1), # NW
}


def _to_array(x: Any) -> np.ndarray:
    """Extract numpy array from Raster or array."""
    if hasattr(x, "__array__"):
        return np.asarray(x)
    return np.asarray(x)


def compute_hand(
    dem_conditioned: np.ndarray,
    flow_dir: np.ndarray,
    stream_mask: np.ndarray,
) -> np.ndarray:
    """
    Compute Height Above Nearest Drainage (HAND) raster.

    For each cell: trace flow path downstream to stream; HAND = elevation - stream elevation.

    Parameters
    ----------
    dem_conditioned : np.ndarray
        Conditioned DEM (after fill_pits, fill_depressions, resolve_flats).
    flow_dir : np.ndarray
        D8 flow direction (pysheds encoding: 64=N, 128=NE, 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW).
    stream_mask : np.ndarray
        Boolean mask, True = stream/drainage cell.

    Returns
    -------
    np.ndarray
        HAND raster (m). Stream cells = 0. NoData outside domain = np.nan.
    """
    dem = _to_array(dem_conditioned).astype(np.float64)
    fdir = _to_array(flow_dir)
    stream = _to_array(stream_mask).astype(bool)

    rows, cols = dem.shape
    hand = np.full_like(dem, np.nan, dtype=np.float64)
    stream_elev = np.full_like(dem, np.nan, dtype=np.float64)

    # Stream cells: HAND = 0, stream_elev = dem
    hand[stream] = 0
    stream_elev[stream] = dem[stream]

    # Process cells in ascending elevation order (downstream first)
    valid = np.isfinite(dem) & ~stream
    order = np.argsort(dem.ravel())
    for idx in order:
        r, c = np.unravel_index(idx, dem.shape)
        if not valid[r, c]:
            continue
        d = int(fdir[r, c])
        if d not in _D8_OFFSETS:
            continue
        dr, dc = _D8_OFFSETS[d]
        rn, cn = r + dr, c + dc
        if 0 <= rn < rows and 0 <= cn < cols and np.isfinite(stream_elev[rn, cn]):
            stream_elev[r, c] = stream_elev[rn, cn]
            hand[r, c] = dem[r, c] - stream_elev[r, c]

    # Resolve flats: propagate remaining cells in multiple passes
    remaining = valid & ~np.isfinite(hand)
    while np.any(remaining):
        prev = np.sum(remaining)
        for r in range(rows):
            for c in range(cols):
                if not remaining[r, c]:
                    continue
                d = int(fdir[r, c])
                if d not in _D8_OFFSETS:
                    continue
                dr, dc = _D8_OFFSETS[d]
                rn, cn = r + dr, c + dc
                if 0 <= rn < rows and 0 <= cn < cols and np.isfinite(stream_elev[rn, cn]):
                    stream_elev[r, c] = stream_elev[rn, cn]
                    hand[r, c] = dem[r, c] - stream_elev[r, c]
                    remaining[r, c] = False
        if np.sum(remaining) >= prev:
            break

    return hand


def discharge_to_stage(
    peak_q_m3s: float,
    rating_curve: Optional[List[Tuple[float, float]]] = None,
    stage_m: Optional[float] = None,
) -> float:
    """
    Convert peak discharge to water surface elevation (m).

    Parameters
    ----------
    peak_q_m3s : float
        Peak discharge (m³/s).
    rating_curve : list of (Q, stage) tuples, optional
        Rating curve: [(Q1, H1), (Q2, H2), ...]. Interpolated linearly.
    stage_m : float, optional
        Direct stage (m). Overrides rating curve if provided.

    Returns
    -------
    float
        Water level H (m).

    Raises
    ------
    ValueError
        If neither rating_curve nor stage_m provided, or Q outside rating curve range.
    """
    if stage_m is not None:
        return float(stage_m)
    if not rating_curve or len(rating_curve) < 2:
        raise ValueError(
            "Provide rating_curve (list of (Q, stage) pairs) or stage_m for Q-to-stage conversion."
        )
    from scipy.interpolate import interp1d

    q_vals = np.array([p[0] for p in rating_curve])
    h_vals = np.array([p[1] for p in rating_curve])
    if peak_q_m3s < q_vals.min() or peak_q_m3s > q_vals.max():
        raise ValueError(
            f"Peak Q {peak_q_m3s:.2f} m³/s outside rating curve range [{q_vals.min():.2f}, {q_vals.max():.2f}]"
        )
    f = interp1d(q_vals, h_vals, kind="linear", fill_value="extrapolate")
    return float(f(peak_q_m3s))


def compute_flood_extent(
    hand: np.ndarray,
    stage_m: float,
    watershed_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Compute inundation depth raster from HAND and water level.

    Inundated where HAND < H; depth = H - HAND.

    Parameters
    ----------
    hand : np.ndarray
        HAND raster (m).
    stage_m : float
        Water surface elevation (m).
    watershed_mask : np.ndarray, optional
        Boolean mask to clip extent. If None, use full domain.

    Returns
    -------
    np.ndarray
        Inundation depth (m). 0 = not inundated. np.nan where HAND is nodata.
    """
    hand_arr = _to_array(hand)
    depth = np.where(
        np.isfinite(hand_arr) & (hand_arr < stage_m),
        stage_m - hand_arr,
        0.0,
    )
    depth = np.where(np.isnan(hand_arr), np.nan, depth)
    if watershed_mask is not None:
        depth = np.where(_to_array(watershed_mask), depth, 0.0)
    return depth.astype(np.float32)


def compute_design_flood_map(
    dem_path: str,
    cn_path: str,
    outlet_x: float,
    outlet_y: float,
    design_depth_mm: float = 100,
    duration_hr: float = 24,
    pattern: str = "type2",
    rating_curve: Optional[List[Tuple[float, float]]] = None,
    stage_m: Optional[float] = None,
    p2_24hr_mm: float = 50,
    timestep_min: int = 15,
    snap_threshold: int = 500,
    output_path: Optional[Union[str, Path]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    base_flow_m3s: Optional[float] = None,
    base_flow_recession_k_min: Optional[float] = None,
    use_subbasins: bool = False,
    min_subbasin_area_km2: float = 0.1,
    max_subbasins: int = 20,
) -> Tuple[pd.DataFrame, Optional[np.ndarray], WatershedResult, Optional[list]]:
    """
    Compute design hydrograph and flood extent raster.

    Parameters
    ----------
    dem_path, cn_path, outlet_x, outlet_y : str, float
        DEM, CN map, outlet coordinates.
    design_depth_mm, duration_hr, pattern : float, float, str
        Design storm parameters.
    rating_curve : list of (Q, stage) tuples, optional
        Rating curve for Q-to-stage. Required if stage_m not provided.
    stage_m : float, optional
        Direct water level (m). Overrides rating curve if provided.
    output_path : str or Path, optional
        Path to save flood extent GeoTIFF.
    base_flow_m3s : float, optional
        Base flow (m³/s) to add to direct runoff.
    base_flow_recession_k_min : float, optional
        Recession time constant (minutes) for base flow. If None, constant base flow.

    use_subbasins : bool
        If True, use subbasin subdivision and routing; returns subbasins for drawing.
    min_subbasin_area_km2, max_subbasins : float, int
        Subbasin parameters when use_subbasins=True.

    Returns
    -------
    (pd.DataFrame, np.ndarray or None, WatershedResult, list or None)
        Hydrograph DataFrame, flood depth raster (m), watershed result, and subbasins
        (None when use_subbasins=False). Flood raster is None if stage cannot be computed.
    """
    def _progress(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    subbasins = None
    if use_subbasins:
        logger.info("Subbasin mode: delineating and subdividing watershed...")
        _progress(5, "Delineating watershed...")
        ws, subbasins = subdivide_watershed(
            dem_path, outlet_x, outlet_y, snap_threshold,
            min_subbasin_area_km2=min_subbasin_area_km2,
            max_subbasins=max_subbasins,
        )
        _progress(25, "Computing hydrograph (subbasins)...")
        df = compute_design_hydrograph_subbasins(
            dem_path=dem_path,
            cn_path=cn_path,
            outlet_x=outlet_x,
            outlet_y=outlet_y,
            design_depth_mm=design_depth_mm,
            duration_hr=duration_hr,
            pattern=pattern,
            p2_24hr_mm=p2_24hr_mm,
            timestep_min=timestep_min,
            snap_threshold=snap_threshold,
            watershed=ws,
            subbasins=subbasins,
            base_flow_m3s=base_flow_m3s,
            base_flow_recession_k_min=base_flow_recession_k_min,
        )
    else:
        logger.info("Delineating watershed for flood map...")
        _progress(5, "Delineating watershed...")
        ws = delineate_watershed(dem_path, outlet_x, outlet_y, snap_threshold)
        _progress(25, "Computing hydrograph...")
        df = compute_design_hydrograph(
            dem_path=dem_path,
            cn_path=cn_path,
            outlet_x=outlet_x,
            outlet_y=outlet_y,
            design_depth_mm=design_depth_mm,
            duration_hr=duration_hr,
            pattern=pattern,
            p2_24hr_mm=p2_24hr_mm,
            timestep_min=timestep_min,
            snap_threshold=snap_threshold,
            watershed=ws,
            base_flow_m3s=base_flow_m3s,
            base_flow_recession_k_min=base_flow_recession_k_min,
        )

    peak_q = float(df["flow_m3s"].max())
    logger.info("Peak flow: %.2f m³/s", peak_q)
    _progress(50, "Computing HAND...")

    try:
        stage = discharge_to_stage(peak_q, rating_curve=rating_curve, stage_m=stage_m)
    except ValueError as e:
        logger.warning("Cannot compute stage: %s. Skipping flood extent.", e)
        return df, None, ws, subbasins

    logger.info("Computing HAND...")
    stream_mask = _to_array(ws.acc) > snap_threshold
    hand = compute_hand(
        ws.dem_conditioned,
        ws.fdir,
        stream_mask,
    )
    _progress(75, "Computing flood extent...")

    logger.info("Computing flood extent (stage=%.2f m)...", stage)
    flood_raster = compute_flood_extent(hand, stage, ws.mask)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dem_path) as src:
            profile = src.profile.copy()
            profile.update(dtype=rasterio.float32, nodata=np.nan)
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
        with rasterio.open(str(output_path), "w", **profile) as dst:
            dst.write(flood_raster, 1)
        logger.info("Flood extent saved to %s", output_path)

    _progress(100, "Done")
    return df, flood_raster, ws, subbasins
