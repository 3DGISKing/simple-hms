# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Subbasin subdivision and routing** — `subdivide_watershed` finds stream junctions and delineates incremental subbasins; `compute_design_hydrograph_subbasins` computes runoff per subbasin, routes with lag or Muskingum, and aggregates at outlet. Falls back to lumped watershed when no junctions found. `routing.py`: `lag_route`, `muskingum_route`, `estimate_reach_travel_time_hr`. CLI: `python example.py --subbasins`.
- **Subbasin GeoJSON export** — `export_subbasins_geojson` exports subbasin polygons with id, area_km2, downstream_id. `plot_subbasins` draws subbasin boundaries or filled polygons on matplotlib axes.
- **Flood map subbasin support** — `compute_design_flood_map` accepts `use_subbasins`, `min_subbasin_area_km2`, `max_subbasins`; returns 4-tuple `(df, flood_raster, watershed, subbasins)`.
- **GUI subbasin mode** — Checkbox "Use subbasins"; subbasins layer toggle in map layers; subbasin boundaries drawn when available.
- **Path-based time of concentration (Tc)** — Traces longest flow path from watershed boundary to outlet; segments into sheet (≤100 m), shallow concentrated (next 300 m), and channel flow; applies TR-55 formulas per segment. Falls back to area-based estimate when fdir/acc/transform/outlet unavailable. Optional `shallow_paved` and `channel_r_m` parameters.

### Changed

- **Tc computation** — `compute_time_of_concentration` now accepts optional `fdir`, `acc`, `transform`, `snapped_outlet`, `stream_threshold` for path-based TR-55 Tc; hydrograph pipeline passes these when available.
- **`compute_design_flood_map` return** — Now returns `(df, flood_raster, watershed, subbasins)`; subbasins is `None` when `use_subbasins=False`.
- Documentation updates: README, PLAN, FAQ — subbasins, routing, flood map API, Tc implementation, limitations, comparison table

## [1.1.0] - 2026-02-26

### Added

- **Base flow** — Optional constant or exponential recession base flow in `compute_design_hydrograph` and `compute_design_flood_map` via `base_flow_m3s` and `base_flow_recession_k_min` parameters
- Base flow inputs in GUI: "Base flow (m³/s, 0=none)" and "Base recession k (min, blank=constant)"
- Base flow visualization in hydrograph plot (dashed brown line for base flow, solid red for total flow)

### Changed

- Documentation updates: README, PLAN, FAQ — project structure (`simple-hms`), base flow API, limitations, comparison table
- Hydrograph DataFrame may include optional `base_flow_m3s` column when base flow is used

## [1.0.0] - 2026-02-26

### Added

- **Rainfall** (`rainfall.py`) — SCS Type I/IA/II/III, uniform, and user-specified hyetograph; design storm temporal distribution
- **Runoff** (`runoff.py`) — SCS Curve Number excess rainfall; CN aggregation from raster within watershed
- **Unit hydrograph** (`unit_hydrograph.py`) — SCS dimensionless unit hydrograph with discrete ordinates
- **Watershed** (`watershed.py`) — DEM conditioning (fill pits, depressions, resolve flats); flow direction and accumulation; pour-point snapping; watershed delineation; stream network extraction; time of concentration; GeoJSON export for watershed and stream network
- **Hydrograph** (`hydrograph.py`) — Convolution pipeline; `compute_design_hydrograph` main API
- **Rating curve** (`rating_curve.py`) — Q-stage from Manning's equation for rectangular and trapezoidal channels
- **Flood map** (`flood_map.py`) — HAND computation; Q-to-stage conversion; inundation extent; `compute_design_flood_map`
- **Plot** (`plot.py`) — Hydrograph plotting (rainfall, excess, flow over time)
- **GUI** (`gui.py`) — Tkinter GUI: flood map + hydrograph visualization; layer toggles (DEM, watershed, stream network, inundation); progress bar; stage via direct input or rating curve
- **Example** (`example.py`) — Synthetic run, full DEM run, flood map run; CLI and GUI entry point (`python example.py`, `python example.py gui`)
- Example data (Pistol Creek DEM, CN raster) and reference documents (HEC-22, HEC-HMS, NRCS Part 630, Johnson et al. 2019)
- Project documentation: README, PLAN, FAQ, references/README
