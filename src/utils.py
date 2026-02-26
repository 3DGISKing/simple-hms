"""Unit conversions and helpers."""

# SI conversions
MM_PER_INCH = 25.4
M_PER_FT = 0.3048
KM2_PER_SQMI = 2.58999
M3S_PER_CFS = 0.0283168


def in_to_mm(inches: float) -> float:
    """Convert inches to mm."""
    return inches * MM_PER_INCH


def mm_to_in(mm: float) -> float:
    """Convert mm to inches."""
    return mm / MM_PER_INCH


def ft_to_m(ft: float) -> float:
    """Convert feet to meters."""
    return ft * M_PER_FT


def m_to_ft(m: float) -> float:
    """Convert meters to feet."""
    return m / M_PER_FT


def sqmi_to_km2(sqmi: float) -> float:
    """Convert square miles to km²."""
    return sqmi * KM2_PER_SQMI


def km2_to_sqmi(km2: float) -> float:
    """Convert km² to square miles."""
    return km2 / KM2_PER_SQMI


def cfs_to_m3s(cfs: float) -> float:
    """Convert cfs to m³/s."""
    return cfs * M3S_PER_CFS


def m3s_to_cfs(m3s: float) -> float:
    """Convert m³/s to cfs."""
    return m3s / M3S_PER_CFS
