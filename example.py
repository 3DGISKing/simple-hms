"""Example: compute design hydrograph from DEM, CN map, and design rainfall."""

import logging
import sys
from pathlib import Path

# Add src to path for standalone run
sys.path.insert(0, str(Path(__file__).parent))

# Enable INFO logging for full DEM example
logging.basicConfig(level=logging.INFO, format="%(message)s")

from src.rainfall import create_design_hyetograph
from src.runoff import compute_excess_rainfall
from src.unit_hydrograph import scs_unit_hydrograph


def run_synthetic_example():
    """Run without DEM: test rainfall, runoff, UH, and convolution."""
    import numpy as np
    import pandas as pd

    print("Synthetic example (no DEM)...")
    depth_mm = 100
    duration_hr = 24
    timestep_min = 15
    cn = 70

    hyetograph = create_design_hyetograph(
        depth_mm, duration_hr, pattern="type2", timestep_min=timestep_min
    )
    print(f"  Hyetograph: {len(hyetograph)} steps, total={hyetograph.sum():.2f} mm")

    excess = compute_excess_rainfall(hyetograph, cn)
    print(f"  Excess rainfall: total={excess.sum():.2f} mm")

    uh = scs_unit_hydrograph(
        area_km2=10,
        lag_min=60,
        timestep_min=timestep_min,
        prf=484,
    )
    flow = np.convolve(excess, uh, mode="full")
    print(f"  Peak flow: {flow.max():.2f} m³/s")

    # Build DataFrame and plot
    n = max(len(hyetograph), len(flow))
    time_min = np.arange(n, dtype=float) * timestep_min
    df = pd.DataFrame({
        "time_min": time_min,
        "flow_m3s": np.pad(flow, (0, n - len(flow)), constant_values=0),
        "rainfall_mm": np.pad(hyetograph, (0, n - len(hyetograph)), constant_values=0),
        "excess_mm": np.pad(excess, (0, n - len(excess)), constant_values=0),
    })
    from src.plot import plot_hydrograph
    plot_hydrograph(df, output_path="outputs/hydrograph_synthetic.png")
    print("  Plot saved to outputs/hydrograph_synthetic.png")

    # Q-stage from Manning's equation (rectangular b=5m, trapezoidal b=10m z=2)
    from src.rating_curve import (
        q_from_stage_rectangular,
        q_from_stage_trapezoidal,
        rating_curve_rectangular,
    )
    q_rect = q_from_stage_rectangular(1.0, b=5.0, n=0.03, s=0.001)
    q_trap = q_from_stage_trapezoidal(1.0, b=10.0, z=2.0, n=0.03, s=0.001)
    print(f"  Q-stage (Manning): rectangular h=1m -> Q={q_rect:.2f} m³/s")
    print(f"  Q-stage (Manning): trapezoidal h=1m -> Q={q_trap:.2f} m³/s")
    rc = rating_curve_rectangular(b=5.0, n_pts=5)
    print(f"  Rating curve sample (rect b=5m): {rc[:3]}...")
    print("  OK (synthetic)")


def run_floodmap_example(dem_path: str, cn_path: str, outlet_x: float, outlet_y: float):
    """Run full pipeline including flood map (hydrograph + inundation extent)."""
    from src.flood_map import compute_design_flood_map
    from src.rating_curve import rating_curve_trapezoidal

    # Q-stage from Manning's equation for trapezoidal channel (b=10m, z=2:1, n=0.03, S=0.001)
    rating_curve = rating_curve_trapezoidal(b=10.0, z=2.0, n=0.03, s=0.001, h_max=5.0)

    out_path = Path("outputs/flood_map.tif")
    df, flood_raster, _ = compute_design_flood_map(
        dem_path=dem_path,
        cn_path=cn_path,
        outlet_x=outlet_x,
        outlet_y=outlet_y,
        design_depth_mm=100,
        duration_hr=24,
        pattern="type2",
        p2_24hr_mm=50,
        timestep_min=15,
        rating_curve=rating_curve,
        output_path=str(out_path),
    )
    peak_idx = df["flow_m3s"].idxmax()
    print("First 10 rows (early storm; flow=0 until excess rainfall exceeds Ia):")
    print(df.head(10))
    print("\nPeak flow row:")
    print(df.loc[[peak_idx]])
    print(f"\nPeak flow: {df['flow_m3s'].max():.2f} m³/s")
    from src.plot import plot_hydrograph
    plot_hydrograph(df, output_path="outputs/hydrograph_floodmap.png")
    print("Plot saved to outputs/hydrograph_floodmap.png")
    if flood_raster is not None:
        import numpy as np
        inundated = (flood_raster > 0) & np.isfinite(flood_raster)
        print(f"Flood extent: {np.sum(inundated)} cells inundated, saved to {out_path}")
    else:
        print("Flood extent: skipped (provide rating_curve or stage_m)")
    return df, flood_raster


def run_full_example(dem_path: str, cn_path: str, outlet_x: float, outlet_y: float):
    """Run full pipeline with DEM and CN map."""
    from src.hydrograph import compute_design_hydrograph
    from src.plot import plot_hydrograph

    df = compute_design_hydrograph(
        dem_path=dem_path,
        cn_path=cn_path,
        outlet_x=outlet_x,
        outlet_y=outlet_y,
        design_depth_mm=100,
        duration_hr=24,
        pattern="type2",
        p2_24hr_mm=50,
        timestep_min=15,
    )
    peak_idx = df["flow_m3s"].idxmax()
    print("First 10 rows (early storm; flow=0 until excess rainfall exceeds Ia):")
    print(df.head(10))
    print("\nPeak flow row:")
    print(df.loc[[peak_idx]])
    print(f"\nPeak flow: {df['flow_m3s'].max():.2f} m³/s")

    plot_hydrograph(df, output_path="outputs/hydrograph.png")
    print("Plot saved to outputs/hydrograph.png")
    return df


def run_gui_app():
    """Launch the GUI for flood map and hydrograph visualization."""
    from src.gui import run_gui
    run_gui()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() == "gui":
        run_gui_app()
        sys.exit(0)

    run_synthetic_example()

    dem = Path("data/dem.tif")
    cn = Path("data/cn.tif")
    if dem.exists() and cn.exists():
        print("\nFull example with DEM...")
        for name in ("src.hydrograph", "src.watershed"):
            logging.getLogger(name).setLevel(logging.INFO)
        df = run_full_example(str(dem), str(cn), 1074538, 1476948)

        # Export watershed and stream network as GeoJSON
        from src.watershed import (
            delineate_watershed,
            export_watershed_geojson,
            export_stream_network_geojson,
        )
        ws = delineate_watershed(str(dem), 1074538, 1476948)
        export_watershed_geojson(ws, "outputs/watershed.geojson", dem_path=str(dem))
        export_stream_network_geojson(ws, "outputs/stream_network.geojson", dem_path=str(dem))

        print("\nFlood map example...")
        for name in ("src.hydrograph", "src.watershed", "src.flood_map"):
            logging.getLogger(name).setLevel(logging.INFO)
        run_floodmap_example(str(dem), str(cn), 1074538, 1476948)
    else:
        print("\nSkipping full example (data/dem.tif and data/cn.tif not found)")
