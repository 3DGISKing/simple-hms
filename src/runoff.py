"""SCS Curve Number excess rainfall and CN aggregation."""

import numpy as np
from typing import Tuple, Any

# S = 25400/CN - 254 (mm)
# Ia = 0.2 * S


def compute_excess_rainfall(hyetograph_mm: np.ndarray, cn: float) -> np.ndarray:
    """
    Compute incremental excess rainfall (mm) from hyetograph using SCS CN method.

    Parameters
    ----------
    hyetograph_mm : np.ndarray
        Rainfall depth (mm) per timestep.
    cn : float
        Curve number (1-100).

    Returns
    -------
    np.ndarray
        Incremental excess rainfall (mm) per timestep, same length as hyetograph.
    """
    cn = np.clip(cn, 1, 100)
    s_mm = 25400 / cn - 254
    ia_mm = 0.2 * s_mm

    p_cum = np.cumsum(hyetograph_mm)
    pe_cum = np.zeros_like(p_cum)

    for i, p in enumerate(p_cum):
        if p <= ia_mm:
            pe_cum[i] = 0
        else:
            pe_cum[i] = (p - ia_mm) ** 2 / (p - ia_mm + s_mm)

    pe_incr = np.diff(pe_cum, prepend=0)
    return pe_incr.astype(float)


def aggregate_cn(
    cn_raster_path: str,
    watershed_mask: np.ndarray,
    transform: Any,
    shape: Tuple[int, int],
    dem_crs: Any = None,
) -> float:
    """
    Compute area-weighted mean CN within watershed.

    Parameters
    ----------
    cn_raster_path : str
        Path to CN GeoTIFF.
    watershed_mask : np.ndarray
        Boolean mask, True = in watershed. Must align with DEM grid.
    transform : Affine
        Geotransform from DEM (watershed grid).
    shape : tuple
        (rows, cols) of watershed mask.
    dem_crs : CRS, optional
        DEM coordinate reference system. Required when DEM and CN have different
        CRS or extent. Ensures correct reprojection of CN to watershed grid.

    Returns
    -------
    float
        Area-weighted mean curve number.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling

    with rasterio.open(cn_raster_path) as src:
        cn_data = src.read(1)
        cn_transform = src.transform
        cn_shape = cn_data.shape
        src_crs = src.crs
        src_nodata = src.nodata

    if cn_shape != shape:
        cn_resampled = np.empty(shape, dtype=np.float32)
        cn_resampled[:] = np.nan
        dst_crs = dem_crs if dem_crs is not None else src_crs
        reproject(
            cn_data.astype(np.float32),
            cn_resampled,
            src_transform=cn_transform,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            src_nodata=src_nodata,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        cn_data = cn_resampled

    # Mask common nodata values when not set in raster metadata
    if src_nodata is None:
        for nodata_val in (-9999, -999):
            cn_data = np.where(cn_data == nodata_val, np.nan, cn_data)

    valid = watershed_mask & np.isfinite(cn_data) & (cn_data > 0) & (cn_data <= 100)
    if not np.any(valid):
        n_ws = int(np.sum(watershed_mask))
        n_finite = int(np.sum(watershed_mask & np.isfinite(cn_data)))
        cn_in_ws = cn_data[watershed_mask]
        cn_min, cn_max = float(np.nanmin(cn_in_ws)), float(np.nanmax(cn_in_ws))
        raise ValueError(
            "No valid CN values within watershed. "
            f"Watershed cells: {n_ws}, with finite CN: {n_finite}. "
            f"CN range in watershed: [{cn_min:.1f}, {cn_max:.1f}]. "
            "Ensure DEM and CN share the same CRS and extent, or that the CN raster "
            "covers the watershed. Valid CN values must be in (0, 100]."
        )

    return float(np.mean(cn_data[valid]))
