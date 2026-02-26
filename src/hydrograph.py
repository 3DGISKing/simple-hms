"""Convolution pipeline and main hydrograph API."""

import logging
import numpy as np
import pandas as pd
import rasterio

from .rainfall import create_design_hyetograph
from .runoff import aggregate_cn, compute_excess_rainfall
from .unit_hydrograph import scs_unit_hydrograph
from .watershed import compute_time_of_concentration, delineate_watershed

logger = logging.getLogger(__name__)


def compute_design_hydrograph(
    dem_path: str,
    cn_path: str,
    outlet_x: float,
    outlet_y: float,
    design_depth_mm: float,
    duration_hr: float,
    pattern: str = "type2",
    p2_24hr_mm: float = 50,
    timestep_min: int = 15,
    prf: float = 484,
    snap_threshold: int = 500,
    watershed=None,
) -> pd.DataFrame:
    """
    Compute design hydrograph from DEM, CN map, and design rainfall.

    Parameters
    ----------
    dem_path : str
        Path to DEM GeoTIFF.
    cn_path : str
        Path to CN (Curve Number) GeoTIFF.
    outlet_x, outlet_y : float
        Outlet coordinates (DEM CRS).
    design_depth_mm : float
        Total design rainfall depth (mm).
    duration_hr : float
        Storm duration (hours).
    pattern : str
        'type1'|'type1a'|'type2'|'type3'|'uniform'.
    p2_24hr_mm : float
        2-year 24-hour rainfall (mm) for Tc.
    timestep_min : int
        Timestep (minutes).
    prf : float
        Peak rate factor for SCS UH.
    snap_threshold : int
        Min accumulation for outlet snap.

    Returns
    -------
    pd.DataFrame
        Columns: time_min, flow_m3s, rainfall_mm, excess_mm
    """
    if watershed is None:
        logger.info("Step 1/7: Delineating watershed from DEM (outlet=%.2f, %.2f)...", outlet_x, outlet_y)
        ws = delineate_watershed(dem_path, outlet_x, outlet_y, snap_threshold)
    else:
        ws = watershed
        logger.info("Step 1/7: Using provided watershed (area=%.2f km²)...", ws.area_km2)
    logger.info("  -> Watershed area: %.2f km², cell size: %.2f m", ws.area_km2, ws.cell_size)

    logger.info("Step 2/7: Aggregating CN within watershed...")
    with rasterio.open(dem_path) as dem_src:
        dem_crs = dem_src.crs
    cn = aggregate_cn(
        cn_path,
        ws.mask,
        ws.transform,
        ws.mask.shape,
        dem_crs=dem_crs,
    )
    logger.info("  -> Weighted CN: %.2f", cn)

    logger.info("Step 3/7: Creating design hyetograph (depth=%.0f mm, %g hr, %s)...", design_depth_mm, duration_hr, pattern)
    hyetograph = create_design_hyetograph(
        design_depth_mm,
        duration_hr,
        pattern=pattern,
        timestep_min=timestep_min,
    )
    logger.info("  -> %d steps, total rainfall: %.2f mm", len(hyetograph), float(hyetograph.sum()))

    logger.info("Step 4/7: Computing excess rainfall (SCS CN)...")
    excess = compute_excess_rainfall(hyetograph, cn)
    logger.info("  -> Total excess: %.2f mm", float(excess.sum()))

    logger.info("Step 5/7: Computing time of concentration...")
    tc_hr, lag_min = compute_time_of_concentration(
        ws.mask,
        ws.dem_conditioned,
        ws.stream_network,
        p2_24hr_mm,
        ws.cell_size,
    )
    logger.info("  -> Tc: %.2f hr, lag: %.1f min", tc_hr, lag_min)

    logger.info("Step 6/7: Building SCS unit hydrograph (area=%.2f km², lag=%.1f min)...", ws.area_km2, lag_min)
    uh = scs_unit_hydrograph(
        ws.area_km2,
        lag_min,
        timestep_min,
        prf=prf,
    )

    logger.info("Step 7/7: Convolving excess rainfall with unit hydrograph...")
    flow = _convolve(excess, uh)
    logger.info("  -> Peak flow: %.2f m³/s", float(np.max(flow)))

    n_rain = len(hyetograph)
    n_flow = len(flow)
    n = max(n_rain, n_flow)

    time_min = np.arange(n, dtype=float) * timestep_min
    rainfall_mm = np.pad(hyetograph, (0, n - n_rain), constant_values=0)
    excess_mm = np.pad(excess, (0, n - n_rain), constant_values=0)
    flow_m3s = np.pad(flow, (0, n - n_flow), constant_values=0)

    return pd.DataFrame({
        "time_min": time_min,
        "flow_m3s": flow_m3s,
        "rainfall_mm": rainfall_mm,
        "excess_mm": excess_mm,
    })


def _convolve(excess: np.ndarray, uh: np.ndarray) -> np.ndarray:
    """Convolve excess rainfall with unit hydrograph."""
    return np.convolve(excess, uh, mode="full")
