"""Convolution pipeline and main hydrograph API."""

import logging
from typing import Literal, Optional

import numpy as np
import pandas as pd
import rasterio

from .rainfall import create_design_hyetograph
from .runoff import aggregate_cn, compute_excess_rainfall
from .routing import (
    estimate_reach_travel_time_hr,
    lag_route,
    muskingum_route,
)
from .unit_hydrograph import scs_unit_hydrograph
from .watershed import (
    SubbasinResult,
    compute_time_of_concentration,
    delineate_watershed,
    subdivide_watershed,
)

logger = logging.getLogger(__name__)


def _compute_base_flow(
    n_timesteps: int,
    timestep_min: int,
    base_flow_m3s: float,
    recession_k_min: float | None,
) -> np.ndarray:
    """
    Compute base flow time series (constant or exponential recession).

    Parameters
    ----------
    n_timesteps : int
        Number of timesteps.
    timestep_min : int
        Timestep duration (minutes).
    base_flow_m3s : float
        Initial/base flow (m³/s).
    recession_k_min : float or None
        Recession time constant (minutes). If None, constant base flow.
        Q(t) = Q0 * exp(-t / k).

    Returns
    -------
    np.ndarray
        Base flow (m³/s) per timestep.
    """
    if recession_k_min is None:
        return np.full(n_timesteps, base_flow_m3s, dtype=float)
    time_min = np.arange(n_timesteps, dtype=float) * timestep_min
    return base_flow_m3s * np.exp(-time_min / recession_k_min)


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
    base_flow_m3s: float | None = None,
    base_flow_recession_k_min: float | None = None,
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
    base_flow_m3s : float, optional
        Base flow (m³/s) to add to direct runoff. If None, no base flow.
    base_flow_recession_k_min : float, optional
        Recession time constant (minutes). If provided with base_flow_m3s,
        use exponential recession Q(t) = Q0 * exp(-t/k). If None, constant base flow.

    Returns
    -------
    pd.DataFrame
        Columns: time_min, flow_m3s, rainfall_mm, excess_mm [, base_flow_m3s]
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
        fdir=ws.fdir,
        acc=ws.acc,
        transform=ws.transform,
        snapped_outlet=ws.snapped_outlet,
        stream_threshold=snap_threshold,
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
    logger.info("  -> Peak direct runoff: %.2f m³/s", float(np.max(flow)))

    n_rain = len(hyetograph)
    n_flow = len(flow)
    n = max(n_rain, n_flow)

    time_min = np.arange(n, dtype=float) * timestep_min
    rainfall_mm = np.pad(hyetograph, (0, n - n_rain), constant_values=0)
    excess_mm = np.pad(excess, (0, n - n_rain), constant_values=0)
    flow_m3s = np.pad(flow, (0, n - n_flow), constant_values=0)

    # Add base flow (constant or recession) to direct runoff
    if base_flow_m3s is not None and base_flow_m3s > 0:
        base_flow = _compute_base_flow(
            n, timestep_min, base_flow_m3s, base_flow_recession_k_min
        )
        flow_m3s = flow_m3s + base_flow
        logger.info("  -> Base flow added: Q0=%.2f m³/s, recession_k=%s", base_flow_m3s, base_flow_recession_k_min)
        logger.info("  -> Peak total flow: %.2f m³/s", float(np.max(flow_m3s)))

        return pd.DataFrame({
            "time_min": time_min,
            "flow_m3s": flow_m3s,
            "rainfall_mm": rainfall_mm,
            "excess_mm": excess_mm,
            "base_flow_m3s": base_flow,
        })
    return pd.DataFrame({
        "time_min": time_min,
        "flow_m3s": flow_m3s,
        "rainfall_mm": rainfall_mm,
        "excess_mm": excess_mm,
    })


def compute_design_hydrograph_subbasins(
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
    min_subbasin_area_km2: float = 0.1,
    max_subbasins: int = 20,
    routing_method: Literal["lag", "muskingum"] = "lag",
    muskingum_x: float = 0.25,
    base_flow_m3s: Optional[float] = None,
    base_flow_recession_k_min: Optional[float] = None,
    watershed=None,
    subbasins=None,
) -> pd.DataFrame:
    """
    Compute design hydrograph using subbasins and channel routing.

    Subdivides watershed at stream junctions, computes runoff per subbasin,
    routes with lag or Muskingum, and aggregates at outlet.

    Parameters
    ----------
    dem_path, cn_path, outlet_x, outlet_y,
    design_depth_mm, duration_hr, pattern, p2_24hr_mm, timestep_min, prf,
    snap_threshold, base_flow_m3s, base_flow_recession_k_min
        Same as compute_design_hydrograph.
    min_subbasin_area_km2 : float
        Minimum subbasin area (km²) to include.
    max_subbasins : int
        Maximum number of subbasins.
    routing_method : 'lag' | 'muskingum'
        Channel routing method.
    muskingum_x : float
        Muskingum X parameter (0–0.5) when routing_method='muskingum'.
    watershed : WatershedResult, optional
        Pre-computed watershed. If provided with subbasins, skips subdivide.
    subbasins : list of SubbasinResult, optional
        Pre-computed subbasins. If provided with watershed, skips subdivide.

    Returns
    -------
    pd.DataFrame
        Same columns as compute_design_hydrograph.
    """
    if watershed is not None and subbasins is not None:
        ws = watershed
    else:
        logger.info("Subbasin mode: delineating and subdividing watershed...")
        ws, subbasins = subdivide_watershed(
            dem_path,
            outlet_x,
            outlet_y,
            snap_threshold=snap_threshold,
            min_subbasin_area_km2=min_subbasin_area_km2,
            max_subbasins=max_subbasins,
        )

    if not subbasins:
        logger.info("No subbasins; using lumped watershed.")
        return compute_design_hydrograph(
            dem_path=dem_path,
            cn_path=cn_path,
            outlet_x=outlet_x,
            outlet_y=outlet_y,
            design_depth_mm=design_depth_mm,
            duration_hr=duration_hr,
            pattern=pattern,
            p2_24hr_mm=p2_24hr_mm,
            timestep_min=timestep_min,
            prf=prf,
            snap_threshold=snap_threshold,
            watershed=ws,
            base_flow_m3s=base_flow_m3s,
            base_flow_recession_k_min=base_flow_recession_k_min,
        )

    with rasterio.open(dem_path) as dem_src:
        dem_crs = dem_src.crs

    hyetograph = create_design_hyetograph(
        design_depth_mm,
        duration_hr,
        pattern=pattern,
        timestep_min=timestep_min,
    )
    n_steps = len(hyetograph)

    # Compute local runoff for each subbasin
    local_runoffs: list[np.ndarray] = []
    for i, sb in enumerate(subbasins):
        cn = aggregate_cn(
            cn_path,
            sb.mask,
            ws.transform,
            ws.mask.shape,
            dem_crs=dem_crs,
        )
        excess = compute_excess_rainfall(hyetograph, cn)
        tc_hr, lag_min = compute_time_of_concentration(
            sb.mask,
            ws.dem_conditioned,
            ws.stream_network,
            p2_24hr_mm,
            ws.cell_size,
            fdir=ws.fdir,
            acc=ws.acc,
            transform=ws.transform,
            snapped_outlet=sb.snapped_outlet,
            stream_threshold=snap_threshold,
        )
        uh = scs_unit_hydrograph(sb.area_km2, lag_min, timestep_min, prf=prf)
        q = _convolve(excess, uh)
        local_runoffs.append(q)

    # Pad to same length
    max_len = max(len(q) for q in local_runoffs)
    for i in range(len(local_runoffs)):
        pad = max_len - len(local_runoffs[i])
        if pad > 0:
            local_runoffs[i] = np.pad(
                local_runoffs[i], (0, pad), mode="constant", constant_values=0
            )

    # Process subbasins in topological order (headwaters first)
    done = set()
    downstream_inflow: dict[int, np.ndarray] = {i: np.zeros(max_len) for i in range(len(subbasins))}
    outlet_flow = np.zeros(max_len)

    while len(done) < len(subbasins):
        progress = False
        for i, sb in enumerate(subbasins):
            if i in done:
                continue
            # upstream of i: all j with downstream_id[j] == i
            upstream = [j for j in range(len(subbasins)) if subbasins[j].downstream_id == i]
            if any(u not in done for u in upstream):
                continue

            inflow = local_runoffs[i].copy()
            for u in upstream:
                inflow += downstream_inflow[u]

            if routing_method == "lag":
                k_hr = estimate_reach_travel_time_hr(
                    max(sb.reach_length_m, 1),
                    max(sb.reach_slope, 0.001),
                )
                lag_min = k_hr * 60
                outflow = lag_route(inflow, lag_min, timestep_min)
            else:
                k_hr = estimate_reach_travel_time_hr(
                    max(sb.reach_length_m, 1),
                    max(sb.reach_slope, 0.001),
                )
                if sb.reach_length_m <= 0:
                    k_hr = 0.1
                outflow = muskingum_route(
                    inflow,
                    k_hr=k_hr,
                    x=muskingum_x,
                    timestep_min=timestep_min,
                )

            if sb.downstream_id >= 0:
                downstream_inflow[sb.downstream_id] += outflow
            else:
                outlet_flow += outflow

            done.add(i)
            progress = True
            break
        if not progress:
            break

    # Build DataFrame
    n = max(n_steps, len(outlet_flow))
    time_min = np.arange(n, dtype=float) * timestep_min
    rainfall_mm = np.pad(hyetograph, (0, n - n_steps), constant_values=0)
    excess_mm = np.pad(
        compute_excess_rainfall(
            hyetograph,
            aggregate_cn(cn_path, ws.mask, ws.transform, ws.mask.shape, dem_crs=dem_crs),
        ),
        (0, n - n_steps),
        constant_values=0,
    )
    flow_m3s = np.pad(outlet_flow, (0, n - len(outlet_flow)), constant_values=0)

    if base_flow_m3s is not None and base_flow_m3s > 0:
        base_flow = _compute_base_flow(
            n, timestep_min, base_flow_m3s, base_flow_recession_k_min
        )
        flow_m3s = flow_m3s + base_flow
        return pd.DataFrame({
            "time_min": time_min,
            "flow_m3s": flow_m3s,
            "rainfall_mm": rainfall_mm,
            "excess_mm": excess_mm,
            "base_flow_m3s": base_flow,
        })
    return pd.DataFrame({
        "time_min": time_min,
        "flow_m3s": flow_m3s,
        "rainfall_mm": rainfall_mm,
        "excess_mm": excess_mm,
    })


def _convolve(excess: np.ndarray, uh: np.ndarray) -> np.ndarray:
    """Convolve excess rainfall with unit hydrograph."""
    return np.convolve(excess, uh, mode="full")
