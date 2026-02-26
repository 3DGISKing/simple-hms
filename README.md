# Hypothetical Storm Hydrograph Calculator

Python-based hydrograph calculator that replicates HEC-HMS hypothetical storm methodology: process DEM and CN map, extract watershed/stream network, apply design rainfall with temporal distribution, compute excess rainfall via SCS Curve Number, generate hydrograph via SCS Unit Hydrograph with convolution, and optionally produce HAND-based flood maps.

## Requirements

- Python 3.10+
- DEM (GeoTIFF)
- CN map (Curve Number raster, same CRS/extent as DEM)
- Design rainfall depth and duration
- Outlet coordinates (x, y in DEM CRS)
- P2: 2-year 24-hour rainfall (mm) for time-of-concentration
- Optional: `snap_threshold` (default 500) — min flow accumulation for outlet snap

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### CLI

```bash
python example.py           # Synthetic + full DEM + flood map example
python example.py --subbasins   # Use subbasin subdivision + lag routing
python example.py gui       # Launch GUI
```

### Python API

```python
from src.hydrograph import compute_design_hydrograph
from src.plot import plot_hydrograph

df = compute_design_hydrograph(
    dem_path="data/dem.tif",
    cn_path="data/cn.tif",
    outlet_x=...,
    outlet_y=...,
    design_depth_mm=100,
    duration_hr=24,
    pattern="type2",
    p2_24hr_mm=50,
    timestep_min=15,
)
# Optional: base_flow_m3s, base_flow_recession_k_min for constant or recession base flow
# df columns: time_min, flow_m3s, rainfall_mm, excess_mm
plot_hydrograph(df, output_path="outputs/hydrograph.png")
```

### Subbasin mode (subdivide + route)

Subdivide watershed at stream junctions, compute runoff per subbasin, route with lag or Muskingum, and aggregate at outlet:

```python
from src.hydrograph import compute_design_hydrograph_subbasins

df = compute_design_hydrograph_subbasins(
    dem_path="data/dem.tif",
    cn_path="data/cn.tif",
    outlet_x=...,
    outlet_y=...,
    design_depth_mm=100,
    duration_hr=24,
    routing_method="lag",      # or "muskingum"
    muskingum_x=0.25,          # when routing_method="muskingum"
    min_subbasin_area_km2=0.1,
    max_subbasins=20,
)
```

If no stream junctions are found, falls back to lumped watershed.

**Export and draw subbasins:**
```python
from src.watershed import subdivide_watershed, export_subbasins_geojson
from src.plot import plot_subbasins
import rasterio.transform
import matplotlib.pyplot as plt

ws, subbasins = subdivide_watershed("data/dem.tif", outlet_x, outlet_y)
if subbasins:
    export_subbasins_geojson(subbasins, ws.transform, "outputs/subbasins.geojson", dem_path="data/dem.tif")
    fig, ax = plt.subplots()
    extent = rasterio.transform.array_bounds(ws.mask.shape[0], ws.mask.shape[1], ws.transform)
    extent = (extent[0], extent[2], extent[1], extent[3])  # (left, right, bottom, top)
    ax.imshow(ws.dem, extent=extent, origin="upper", cmap="terrain")
    plot_subbasins(ax, subbasins, ws.transform, extent, as_boundaries=True)
    plt.savefig("outputs/subbasins_map.png")
```

### Flood map

```python
from src.flood_map import compute_design_flood_map
from src.rating_curve import rating_curve_trapezoidal

# Q-stage from Manning's equation (trapezoidal: b=10m, z=2:1, n=0.03, S=0.001)
rating_curve = rating_curve_trapezoidal(b=10.0, z=2.0, n=0.03, s=0.001, h_max=5.0)

df, flood_raster, watershed, subbasins = compute_design_flood_map(
    dem_path="data/dem.tif",
    cn_path="data/cn.tif",
    outlet_x=...,
    outlet_y=...,
    design_depth_mm=100,
    duration_hr=24,
    rating_curve=rating_curve,  # or stage_m=2.0 for fixed stage
    output_path="outputs/flood_map.tif",
)
# Optional: use_subbasins=True for subbasin subdivision + routing
```

### GUI

Run `python example.py gui` or use the **Python: GUI** launch config in VS Code (F5).

- **Inputs:** DEM path, CN path, outlet X/Y, design depth, duration, stage (direct m or from rating curve), base flow and recession (optional)
- **Map layers:** Toggle DEM, watershed, stream network, subbasins, inundation visibility
- **Progress:** Determinate progress bar during pipeline run
- **Outputs:** Layered map (left) + hydrograph (right)

### Q-stage (Manning's equation)

For simple channel geometries, Q-stage can be derived from Manning's equation:

```python
from src.rating_curve import (
    q_from_stage_rectangular,
    q_from_stage_trapezoidal,
    stage_from_q_rectangular,
    rating_curve_rectangular,
    rating_curve_trapezoidal,
)

# Rectangular: Q from stage h
q = q_from_stage_rectangular(1.0, b=5.0, n=0.03, s=0.001)

# Trapezoidal: build rating curve for flood_map
rc = rating_curve_trapezoidal(b=10.0, z=2.0, n=0.03, s=0.001, h_max=5.0)
```

### GeoJSON export

```python
from src.watershed import delineate_watershed, export_watershed_geojson, export_stream_network_geojson

ws = delineate_watershed("data/dem.tif", outlet_x, outlet_y)
export_watershed_geojson(ws, "outputs/watershed.geojson", dem_path="data/dem.tif")
export_stream_network_geojson(ws, "outputs/stream_network.geojson", dem_path="data/dem.tif")
```

## Project Structure

```
simple-hms/
├── src/
│   ├── watershed.py      # DEM conditioning, delineation, stream network, subbasins, Tc, GeoJSON export
│   ├── rainfall.py       # Design storm temporal distribution
│   ├── runoff.py         # SCS CN excess rainfall
│   ├── unit_hydrograph.py # SCS unit hydrograph
│   ├── routing.py        # Lag and Muskingum channel routing
│   ├── hydrograph.py     # Convolution pipeline, main API (lumped + subbasins)
│   ├── rating_curve.py   # Q-stage from Manning's equation (rectangular, trapezoidal)
│   ├── flood_map.py      # HAND, Q-to-stage, inundation extent
│   ├── plot.py           # Hydrograph plotting, subbasin map
│   ├── gui.py            # Tkinter GUI: flood map + hydrograph
│   └── utils.py          # Unit conversions
├── data/
├── outputs/              # hydrograph.png, flood_map.tif, watershed.geojson, subbasins.geojson, etc.
├── .vscode/launch.json   # Python: example.py, Python: GUI
├── PLAN.md              # Architecture, technical details, implementation notes
├── FAQ.md               # Frequently asked questions
├── references/README.md # Reference documents and download links
└── example.py           # CLI + GUI entry point
```

## Example Outputs

- `outputs/hydrograph_synthetic.png` — Synthetic run (no DEM)
- `outputs/hydrograph.png` — Full DEM run
- `outputs/hydrograph_floodmap.png` — Flood map run
- `outputs/flood_map.tif` — Inundation depth raster
- `outputs/watershed.geojson` — Watershed polygon
- `outputs/stream_network.geojson` — Stream network polylines
- `outputs/subbasins.geojson` — Subbasin polygons (when using `--subbasins`)

## Comparison with HEC-HMS

This project follows the same conceptual model as HEC-HMS Hypothetical Storm. The main components map as follows:

| HEC-HMS Component | This Project | Notes |
|-------------------|--------------|-------|
| **Loss** | SCS Curve Number (`runoff.py`) | Same method: S = 25400/CN − 254, Ia = 0.2S, cumulative excess via (P − Ia)²/(P − Ia + S). Area-weighted CN from raster within watershed. |
| **Transform** | SCS Unit Hydrograph (`unit_hydrograph.py`) + convolution | Same method: dimensionless SCS UH, lag from Tc (path-based TR-55: longest flow path, sheet/shallow/channel segments), peak rate factor (default 484). Convolve excess rainfall with UH to get direct runoff. |
| **Routing** | Lag or Muskingum (`routing.py`) | When using subbasins: lag (time shift) or Muskingum channel routing between subbasins. Reach travel time from length and slope. |
| **Base Flow** | Optional (`base_flow_m3s`, `base_flow_recession_k_min`) | Constant or exponential recession base flow added to direct runoff. |

### Differences

- **Loss**: Lumped mode uses single area-weighted CN; subbasin mode computes CN per subbasin.
- **Transform**: Single SCS UH for the watershed; HEC-HMS supports Clark, Snyder, and other transform methods.
- **Base Flow**: Optional; pass `base_flow_m3s` and optionally `base_flow_recession_k_min` for constant or exponential recession.

### Limitations

- **Subbasins** — optional: `compute_design_hydrograph_subbasins` subdivides at stream junctions, routes with lag or Muskingum.
- **Tc** — path-based TR-55 when fdir/acc/transform/outlet are available: traces longest flow path, segments into sheet (≤100 m), shallow (next 300 m), and channel flow, applies TR-55 formulas per segment. Falls back to area-based estimate (L from √area, S from elev range, sheet+shallow only) if path tracing fails or inputs are missing; default 0.5 hr when no valid data.
- **No Green-Ampt / other loss methods** — SCS CN only.
- **No Clark / Snyder / other transforms** — SCS UH only.
- **HAND flood map** — assumes simple rating curve or fixed stage; no 2D routing.

## References

- HEC-HMS Hypothetical Storm
- NRCS TR-55, NEH Part 630
- SCS Curve Number method
- SCS dimensionless unit hydrograph
