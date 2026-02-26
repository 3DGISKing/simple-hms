"""Design storm temporal distribution and hyetograph."""

import numpy as np
from typing import Union

# SCS 24-hour cumulative distribution: (hour, cumulative fraction 0-1)
# Source: NRCS TR-55 Appendix B, NEH Part 630
_SCS_TYPE_II = np.array([
    [0, 0], [1, 0.011], [2, 0.023], [3, 0.034], [4, 0.046], [5, 0.058],
    [6, 0.070], [7, 0.082], [8, 0.094], [9, 0.106], [10, 0.118], [11, 0.130],
    [11.5, 0.155], [12, 0.210], [12.5, 0.340], [13, 0.470], [13.5, 0.580],
    [14, 0.670], [14.5, 0.740], [15, 0.790], [15.5, 0.830], [16, 0.860],
    [17, 0.900], [18, 0.930], [19, 0.950], [20, 0.965], [21, 0.975],
    [22, 0.985], [23, 0.993], [24, 1.000],
])

# Type I: Pacific NW, more intense
_SCS_TYPE_I = np.array([
    [0, 0], [2, 0.022], [4, 0.048], [6, 0.080], [8, 0.120], [10, 0.165],
    [12, 0.220], [14, 0.290], [16, 0.380], [18, 0.480], [20, 0.600],
    [22, 0.750], [24, 1.000],
])

# Type IA: Pacific NW, milder
_SCS_TYPE_IA = np.array([
    [0, 0], [2, 0.010], [4, 0.022], [6, 0.040], [8, 0.065], [10, 0.095],
    [12, 0.130], [14, 0.175], [16, 0.230], [18, 0.300], [20, 0.390],
    [22, 0.500], [24, 1.000],
])

# Type III: Gulf/southeastern US
_SCS_TYPE_III = np.array([
    [0, 0], [2, 0.013], [4, 0.035], [6, 0.070], [8, 0.110], [10, 0.160],
    [11, 0.220], [12, 0.280], [13, 0.350], [14, 0.420], [15, 0.490],
    [16, 0.560], [17, 0.630], [18, 0.700], [20, 0.820], [22, 0.910],
    [24, 1.000],
])

_PATTERNS = {
    "type1": _SCS_TYPE_I,
    "type1a": _SCS_TYPE_IA,
    "type2": _SCS_TYPE_II,
    "type3": _SCS_TYPE_III,
}


def create_design_hyetograph(
    depth_mm: float,
    duration_hr: float,
    pattern: Union[str, np.ndarray] = "type2",
    timestep_min: int = 15,
) -> np.ndarray:
    """
    Create design rainfall hyetograph (mm per timestep).

    Parameters
    ----------
    depth_mm : float
        Total design rainfall depth (mm).
    duration_hr : float
        Storm duration (hours).
    pattern : str or np.ndarray
        'type1'|'type1a'|'type2'|'type3'|'uniform', or array of incremental
        rainfall (mm) per timestep (bypasses built-in patterns).
    timestep_min : int
        Timestep duration (minutes).

    Returns
    -------
    np.ndarray
        Rainfall depth (mm) per timestep, shape (n_timesteps,).
    """
    n_steps = int(np.ceil(duration_hr * 60 / timestep_min))

    if isinstance(pattern, np.ndarray):
        # User-specified: use as-is, trim or pad to n_steps
        arr = np.asarray(pattern, dtype=float).ravel()
        if len(arr) != n_steps:
            if len(arr) < n_steps:
                arr = np.pad(arr, (0, n_steps - len(arr)), constant_values=0)
            else:
                arr = arr[:n_steps]
        # Scale to match depth if needed
        total = arr.sum()
        if total > 0:
            arr = arr * (depth_mm / total)
        return arr

    if pattern == "uniform":
        return np.full(n_steps, depth_mm / n_steps)

    # SCS Type I/IA/II/III
    if pattern not in _PATTERNS:
        raise ValueError(f"Unknown pattern: {pattern}. Use type1, type1a, type2, type3, uniform, or array.")

    table = _PATTERNS[pattern]
    hours = table[:, 0]
    cum_frac = table[:, 1]

    # Scale 24-h distribution to target duration
    # Map t in [0, duration_hr] to t_24 in [0, 24] for lookup
    step_hr = timestep_min / 60
    t_center = np.arange(0.5 * step_hr, duration_hr, step_hr)[:n_steps]
    t_24 = t_center * (24 / duration_hr) if duration_hr != 24 else t_center

    cum_interp = np.interp(t_24, hours, cum_frac)
    cum_interp = np.clip(cum_interp, 0, 1)
    # Pad start with 0 for first increment
    cum_full = np.concatenate([[0], cum_interp])
    incr_frac = np.diff(cum_full)
    incr_frac = incr_frac / incr_frac.sum()  # Normalize to 1
    return (incr_frac * depth_mm).astype(float)
