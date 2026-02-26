"""Channel routing: lag and Muskingum methods for subbasin aggregation."""

import logging
import numpy as np

logger = logging.getLogger(__name__)


def lag_route(
    inflow_m3s: np.ndarray,
    lag_min: float,
    timestep_min: int,
) -> np.ndarray:
    """
    Route inflow hydrograph with lag (simple time shift).

    Q_out(t) = Q_in(t - lag_min). Values before lag are zero.

    Parameters
    ----------
    inflow_m3s : np.ndarray
        Inflow discharge (m³/s) per timestep.
    lag_min : float
        Lag time (minutes).
    timestep_min : int
        Timestep duration (minutes).

    Returns
    -------
    np.ndarray
        Outflow discharge (m³/s), same length as inflow.
    """
    n = len(inflow_m3s)
    n_lag = int(round(lag_min / timestep_min))
    if n_lag <= 0:
        return np.asarray(inflow_m3s, dtype=float).copy()
    out = np.zeros(n, dtype=float)
    out[n_lag:] = inflow_m3s[: n - n_lag]
    return out


def muskingum_route(
    inflow_m3s: np.ndarray,
    k_hr: float,
    x: float,
    timestep_min: int,
    q_init: float = 0.0,
) -> np.ndarray:
    """
    Route inflow hydrograph with Muskingum method.

    Storage: S = K[x*I + (1-x)*Q]
    Routing: Q2 = C0*I2 + C1*I1 + C2*Q1
    where C0 + C1 + C2 = 1 for volume conservation.

    Parameters
    ----------
    inflow_m3s : np.ndarray
        Inflow discharge (m³/s) per timestep.
    k_hr : float
        Travel time through reach (hours).
    x : float
        Weighting factor (0–0.5). 0 = max attenuation, 0.5 = no attenuation.
    timestep_min : int
        Timestep duration (minutes).
    q_init : float
        Initial outflow (m³/s) at t=0.

    Returns
    -------
    np.ndarray
        Outflow discharge (m³/s), same length as inflow.
    """
    dt_hr = timestep_min / 60.0
    if k_hr <= 0 or dt_hr <= 0:
        return np.asarray(inflow_m3s, dtype=float).copy()

    # Muskingum coefficients (McCarthy 1938)
    denom = 2 * k_hr * (1 - x) + dt_hr
    if denom <= 0:
        return np.asarray(inflow_m3s, dtype=float).copy()

    c0 = (dt_hr - 2 * k_hr * x) / denom
    c1 = (dt_hr + 2 * k_hr * x) / denom
    c2 = (2 * k_hr * (1 - x) - dt_hr) / denom

    # Stability: C0, C1, C2 should be non-negative for numerical stability
    # If not, fall back to lag routing with K as lag
    if c0 < -1e-9 or c1 < -1e-9 or c2 < -1e-9:
        logger.warning(
            "Muskingum coefficients unstable (K=%.2f hr, x=%.2f, dt=%.2f hr). "
            "Using lag routing with K.",
            k_hr, x, dt_hr,
        )
        return lag_route(inflow_m3s, k_hr * 60, timestep_min)

    n = len(inflow_m3s)
    outflow = np.zeros(n, dtype=float)
    outflow[0] = q_init
    for i in range(1, n):
        i1 = inflow_m3s[i - 1]
        i2 = inflow_m3s[i]
        q1 = outflow[i - 1]
        outflow[i] = c0 * i2 + c1 * i1 + c2 * q1
        outflow[i] = max(0.0, outflow[i])

    return outflow


def estimate_reach_travel_time_hr(
    reach_length_m: float,
    slope: float,
    n_manning: float = 0.05,
    r_hydraulic_m: float = 0.3,
) -> float:
    """
    Estimate reach travel time (hours) from length and Manning velocity.

    V = (1/n) * R^(2/3) * S^(1/2)
    T = L / V

    Parameters
    ----------
    reach_length_m : float
        Reach length (m).
    slope : float
        Channel slope (m/m).
    n_manning : float
        Manning roughness.
    r_hydraulic_m : float
        Hydraulic radius (m).

    Returns
    -------
    float
        Travel time (hours).
    """
    slope = max(slope, 1e-6)
    v_ms = (1.0 / n_manning) * (r_hydraulic_m ** (2 / 3)) * (slope ** 0.5)
    if v_ms <= 0:
        return 1.0
    return reach_length_m / (v_ms * 3600)
