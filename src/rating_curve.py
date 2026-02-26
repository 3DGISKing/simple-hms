"""Q-stage (discharge vs stage) from Manning's equation for simple channel geometries."""

from typing import List, Optional, Tuple, Union

import numpy as np


def q_from_stage_rectangular(
    h: Union[float, np.ndarray],
    b: float,
    n: float = 0.03,
    s: float = 0.001,
) -> Union[float, np.ndarray]:
    """
    Discharge Q (m³/s) from stage h (m) for a rectangular channel using Manning's equation.

    Q = (1/n) * A * R^(2/3) * S^(1/2)
    where A = b*h, P = b + 2h, R = A/P.

    Parameters
    ----------
    h : float or array
        Water depth / stage (m).
    b : float
        Channel bottom width (m).
    n : float
        Manning roughness coefficient (default 0.03).
    s : float
        Channel slope (m/m).

    Returns
    -------
    float or array
        Discharge Q (m³/s).
    """
    h = np.atleast_1d(np.asarray(h, dtype=float))
    h = np.maximum(h, 0.0)
    a = b * h
    p = b + 2 * h
    r = np.where(p > 0, a / p, 0.0)
    q = (1.0 / n) * a * (r ** (2.0 / 3.0)) * (s ** 0.5)
    return float(q.flat[0]) if q.size == 1 else q


def q_from_stage_trapezoidal(
    h: Union[float, np.ndarray],
    b: float,
    z: float,
    n: float = 0.03,
    s: float = 0.001,
) -> Union[float, np.ndarray]:
    """
    Discharge Q (m³/s) from stage h (m) for a trapezoidal channel using Manning's equation.

    Q = (1/n) * A * R^(2/3) * S^(1/2)
    where A = h*(b + z*h), P = b + 2*h*sqrt(1+z²), R = A/P.
    z = horizontal:vertical side slope (e.g. z=2 means 2:1).

    Parameters
    ----------
    h : float or array
        Water depth / stage (m).
    b : float
        Channel bottom width (m).
    z : float
        Side slope (horizontal:vertical). z=0 gives rectangular.
    n : float
        Manning roughness coefficient (default 0.03).
    s : float
        Channel slope (m/m).

    Returns
    -------
    float or array
        Discharge Q (m³/s).
    """
    h = np.atleast_1d(np.asarray(h, dtype=float))
    h = np.maximum(h, 0.0)
    a = h * (b + z * h)
    p = b + 2 * h * np.sqrt(1.0 + z * z)
    r = np.where(p > 0, a / p, 0.0)
    q = (1.0 / n) * a * (r ** (2.0 / 3.0)) * (s ** 0.5)
    return float(q.flat[0]) if q.size == 1 else q


def stage_from_q_rectangular(
    q: float,
    b: float,
    n: float = 0.03,
    s: float = 0.001,
    h_max: float = 20.0,
    tol: float = 1e-6,
) -> float:
    """
    Stage h (m) from discharge Q (m³/s) for a rectangular channel.

    Solves Q(h) = Q numerically (bisection).

    Parameters
    ----------
    q : float
        Discharge (m³/s).
    b : float
        Channel bottom width (m).
    n, s : float
        Manning n and slope.
    h_max : float
        Upper bound for depth search (m).
    tol : float
        Convergence tolerance on Q.

    Returns
    -------
    float
        Water depth h (m).

    Raises
    ------
    ValueError
        If Q <= 0 or no solution found.
    """
    if q <= 0:
        return 0.0
    q_at_max = q_from_stage_rectangular(h_max, b, n, s)
    if q > q_at_max:
        raise ValueError(
            f"Q={q:.2f} m³/s exceeds capacity at h_max={h_max} m "
            f"(Q_max≈{q_at_max:.2f}). Increase h_max or channel size."
        )
    lo, hi = 0.0, h_max
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        q_mid = q_from_stage_rectangular(mid, b, n, s)
        if abs(q_mid - q) < tol:
            return float(mid)
        if q_mid < q:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def stage_from_q_trapezoidal(
    q: float,
    b: float,
    z: float,
    n: float = 0.03,
    s: float = 0.001,
    h_max: float = 20.0,
    tol: float = 1e-6,
) -> float:
    """
    Stage h (m) from discharge Q (m³/s) for a trapezoidal channel.

    Solves Q(h) = Q numerically (bisection).

    Parameters
    ----------
    q : float
        Discharge (m³/s).
    b : float
        Channel bottom width (m).
    z : float
        Side slope (horizontal:vertical).
    n, s : float
        Manning n and slope.
    h_max : float
        Upper bound for depth search (m).
    tol : float
        Convergence tolerance on Q.

    Returns
    -------
    float
        Water depth h (m).

    Raises
    ------
    ValueError
        If Q <= 0 or no solution found.
    """
    if q <= 0:
        return 0.0
    q_at_max = q_from_stage_trapezoidal(h_max, b, z, n, s)
    if q > q_at_max:
        raise ValueError(
            f"Q={q:.2f} m³/s exceeds capacity at h_max={h_max} m "
            f"(Q_max≈{q_at_max:.2f}). Increase h_max or channel size."
        )
    lo, hi = 0.0, h_max
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        q_mid = q_from_stage_trapezoidal(mid, b, z, n, s)
        if abs(q_mid - q) < tol:
            return float(mid)
        if q_mid < q:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def rating_curve_rectangular(
    b: float,
    n: float = 0.03,
    s: float = 0.001,
    stages: Optional[np.ndarray] = None,
    h_min: float = 0.01,
    h_max: float = 5.0,
    n_pts: int = 50,
) -> List[Tuple[float, float]]:
    """
    Build a rating curve [(Q, stage), ...] for a rectangular channel.

    Parameters
    ----------
    b : float
        Channel bottom width (m).
    n, s : float
        Manning n and slope.
    stages : array, optional
        Stage values (m). If None, use log-spaced points from h_min to h_max.
    h_min, h_max : float
        Min/max stage for default stages (m).
    n_pts : int
        Number of points for default stages.

    Returns
    -------
    list of (Q, stage)
        Rating curve suitable for discharge_to_stage interpolation.
    """
    if stages is None:
        stages = np.logspace(
            np.log10(max(h_min, 1e-4)),
            np.log10(h_max),
            n_pts,
        )
    stages = np.asarray(stages)
    q_vals = q_from_stage_rectangular(stages, b, n, s)
    return [(float(q), float(h)) for q, h in zip(q_vals, stages)]


def rating_curve_trapezoidal(
    b: float,
    z: float,
    n: float = 0.03,
    s: float = 0.001,
    stages: Optional[np.ndarray] = None,
    h_min: float = 0.01,
    h_max: float = 5.0,
    n_pts: int = 50,
) -> List[Tuple[float, float]]:
    """
    Build a rating curve [(Q, stage), ...] for a trapezoidal channel.

    Parameters
    ----------
    b : float
        Channel bottom width (m).
    z : float
        Side slope (horizontal:vertical).
    n, s : float
        Manning n and slope.
    stages : array, optional
        Stage values (m). If None, use log-spaced points from h_min to h_max.
    h_min, h_max : float
        Min/max stage for default stages (m).
    n_pts : int
        Number of points for default stages.

    Returns
    -------
    list of (Q, stage)
        Rating curve suitable for discharge_to_stage interpolation.
    """
    if stages is None:
        stages = np.logspace(
            np.log10(max(h_min, 1e-4)),
            np.log10(h_max),
            n_pts,
        )
    stages = np.asarray(stages)
    q_vals = q_from_stage_trapezoidal(stages, b, z, n, s)
    return [(float(q), float(h)) for q, h in zip(q_vals, stages)]
