"""SCS dimensionless unit hydrograph generation."""

import numpy as np

# SCS dimensionless UH ordinates (t/Tp, q/qp) from NRCS NEH
# Time base ~5*Tp
_DIMENSIONLESS_UH = np.array([
    [0.0, 0.00], [0.1, 0.03], [0.2, 0.10], [0.3, 0.19], [0.4, 0.31], [0.5, 0.47],
    [0.6, 0.66], [0.7, 0.82], [0.8, 0.93], [0.9, 0.99], [1.0, 1.00], [1.1, 0.99],
    [1.2, 0.93], [1.3, 0.86], [1.4, 0.78], [1.5, 0.68], [1.6, 0.56], [1.7, 0.46],
    [1.8, 0.39], [1.9, 0.33], [2.0, 0.28], [2.2, 0.207], [2.4, 0.147], [2.6, 0.107],
    [2.8, 0.077], [3.0, 0.055], [3.2, 0.040], [3.4, 0.029], [3.6, 0.021],
    [3.8, 0.015], [4.0, 0.011], [4.5, 0.005], [5.0, 0.000],
])


def scs_unit_hydrograph(
    area_km2: float,
    lag_min: float,
    timestep_min: int,
    prf: float = 484,
) -> np.ndarray:
    """
    Generate SCS unit hydrograph ordinates (m³/s per mm excess).

    Parameters
    ----------
    area_km2 : float
        Watershed area (km²).
    lag_min : float
        Basin lag (minutes).
    timestep_min : int
        Timestep duration (minutes).
    prf : float
        Peak rate factor (default 484).

    Returns
    -------
    np.ndarray
        UH ordinates (m³/s per mm excess), length ~5*Tp/timestep.
    """
    tr_hr = timestep_min / 60
    tp_hr = lag_min / 60
    tp_min = lag_min
    Tp_hr = tr_hr / 2 + tp_hr
    Tp_min = Tp_hr * 60

    Qp = 0.208 * area_km2 * prf / Tp_hr

    t_tp = _DIMENSIONLESS_UH[:, 0]
    q_qp = _DIMENSIONLESS_UH[:, 1]

    n_uh = int(np.ceil(5 * Tp_min / timestep_min))
    t_min = np.arange(0, n_uh * timestep_min, timestep_min, dtype=float)
    t_tp_vals = t_min / Tp_min

    q_qp_interp = np.interp(t_tp_vals, t_tp, q_qp)
    uh = q_qp_interp * Qp

    # Normalize so volume = 1 mm over area
    # Volume = A_km2 * 1e6 m² * 0.001 m = A_km2 * 1000 m³
    timestep_sec = timestep_min * 60
    actual_vol = np.sum(uh) * timestep_sec
    target_vol = area_km2 * 1e6 * 0.001
    if actual_vol > 0:
        uh = uh * (target_vol / actual_vol)

    return uh.astype(float)
