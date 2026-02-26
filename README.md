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

### Flood map

```python
from src.flood_map import compute_design_flood_map
from src.rating_curve import rating_curve_trapezoidal

# Q-stage from Manning's equation (trapezoidal: b=10m, z=2:1, n=0.03, S=0.001)
rating_curve = rating_curve_trapezoidal(b=10.0, z=2.0, n=0.03, s=0.001, h_max=5.0)

df, flood_raster, watershed = compute_design_flood_map(
    dem_path="data/dem.tif",
    cn_path="data/cn.tif",
    outlet_x=...,
    outlet_y=...,
    design_depth_mm=100,
    duration_hr=24,
    rating_curve=rating_curve,  # or stage_m=2.0 for fixed stage
    output_path="outputs/flood_map.tif",
)
```

### GUI

Run `python example.py gui` or use the **Python: GUI** launch config in VS Code (F5).

- **Inputs:** DEM path, CN path, outlet X/Y, design depth, duration, stage (m), base flow (optional)
- **Map layers:** Toggle DEM, watershed, stream network, inundation visibility
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
│   ├── watershed.py      # DEM conditioning, delineation, stream network, Tc, GeoJSON export
│   ├── rainfall.py       # Design storm temporal distribution
│   ├── runoff.py         # SCS CN excess rainfall
│   ├── unit_hydrograph.py # SCS unit hydrograph
│   ├── hydrograph.py     # Convolution pipeline, main API
│   ├── rating_curve.py   # Q-stage from Manning's equation (rectangular, trapezoidal)
│   ├── flood_map.py      # HAND, Q-to-stage, inundation extent
│   ├── plot.py           # Hydrograph plotting (rainfall, excess, flow)
│   ├── gui.py            # Tkinter GUI: flood map + hydrograph
│   └── utils.py          # Unit conversions
├── data/
├── outputs/              # hydrograph.png, flood_map.tif, watershed.geojson, etc.
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

## Comparison with HEC-HMS

This project follows the same conceptual model as HEC-HMS Hypothetical Storm. The three main components map as follows:

| HEC-HMS Component | This Project | Notes |
|-------------------|--------------|-------|
| **Loss** | SCS Curve Number (`runoff.py`) | Same method: S = 25400/CN − 254, Ia = 0.2S, cumulative excess via (P − Ia)²/(P − Ia + S). Area-weighted CN from raster within watershed. |
| **Transform** | SCS Unit Hydrograph (`unit_hydrograph.py`) + convolution | Same method: dimensionless SCS UH, lag from Tc (TR-55), peak rate factor (default 484). Convolve excess rainfall with UH to get direct runoff. |
| **Base Flow** | Optional (`base_flow_m3s`, `base_flow_recession_k_min`) | Constant or exponential recession base flow added to direct runoff. |

### Differences

- **Loss**: Single area-weighted CN for the whole watershed; HEC-HMS can use subbasins with different CNs.
- **Transform**: Single SCS UH for the watershed; HEC-HMS supports Clark, Snyder, and other transform methods.
- **Base Flow**: Optional; pass `base_flow_m3s` and optionally `base_flow_recession_k_min` for constant or exponential recession.

### Limitations

- **Single watershed** — no subbasin routing; one lumped CN and one UH for the whole catchment.
- **Tc simplified** — TR-55-style estimate from area/slope; no full flow-path tracing.
- **No Green-Ampt / other loss methods** — SCS CN only.
- **No Clark / Snyder / other transforms** — SCS UH only.
- **HAND flood map** — assumes simple rating curve or fixed stage; no 2D routing.

## References

- HEC-HMS Hypothetical Storm
- NRCS TR-55, NEH Part 630
- SCS Curve Number method
- SCS dimensionless unit hydrograph
