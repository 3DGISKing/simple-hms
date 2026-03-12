---
date: 2026-02-26
topic: hydrocesium-port-simple-hms
---

# Port simple-hms Hydrology into hydrocesium (TypeScript)

## What We're Building

A TypeScript implementation of simple-hms's hydrology inside **hydrocesium** (`D:\MyResearch\hydrocesium`). End-to-end capability: use existing watershed and HAND from hydrocesium; add design storm → SCS runoff → unit hydrograph → design hydrograph; flood extent from design flow using existing HAND + rating curve. No Python at runtime; everything runs in the hydrocesium stack (Vue + Cesium + geotiff, turf, d3, etc.).

**Scope:** Add the missing hydrology *functions* into hydrocesium — not a separate service. New code lives in a dedicated hydrology module; watershed and HAND are **reused** from `src/core/watershed/`, not reimplemented.

## Why This Approach

- **Port to TypeScript** (not Python backend, not hybrid): single stack, no backend deployment, in-browser or Node execution.
- **Reuse:** hydrocesium already has GeoTIFF loading, terrain/flood visualization (`floodRunner.ts`), layers, **Watershed from DEM**, and **HAND**. The new hydrology module consumes these and adds only rainfall, runoff, unit hydrograph, hydrograph, and flood-extent logic (Q→stage, inundation from HAND).

## Key Decisions

| Decision | Rationale |
|----------|------------|
| **Port algorithms to TS** | Single stack; no Python runtime; aligns with "add functions into hydrocesium." |
| **Hydrocesium = target repo** | All new hydrology code lives under `D:\MyResearch\hydrocesium` (e.g. `src/core/hydrology/` or similar). |
| **New hydrology module, then integrate** | Build a dedicated module with clear boundaries; integrate with Vue/Cesium after the pipeline is complete. |
| **Do not reimplement Watershed or HAND** | hydrocesium already has DEM → flow direction, flow accumulation, catchment delineation, river network (`src/core/watershed/runFlowDirection.ts`, `runFlowAccumulation.ts`, `runCatchment.ts`, `runExtractRiverNetwork.ts`) and HAND (`runComputeHand.ts`). The hydrology module **consumes** their outputs (e.g. watershed mask, HAND raster) instead of reimplementing. |
| **Hydrology module scope** | Implement only: design rainfall (hyetograph), SCS runoff (CN aggregation, excess rainfall), SCS unit hydrograph, convolution → design hydrograph; and flood extent logic that uses **existing** HAND + rating curve (Q→stage, inundation = HAND ≤ stage). |
| **Use existing deps first** | geotiff for rasters; existing watershed/HAND APIs; add minimal new deps. |

### What the hydrology module contains (and does not)

| In hydrology module (port from simple-hms) | Reuse from hydrocesium (do not port) |
|-------------------------------------------|--------------------------------------|
| Design rainfall (hyetograph: Type I/IA/II/III, uniform) | Watershed from DEM: flow direction, flow accumulation, catchment delineation, river network (`src/core/watershed/`) |
| SCS runoff: weighted CN from raster, excess rainfall | HAND computation (`runComputeHand.ts`) |
| SCS unit hydrograph, convolution → design hydrograph | Raster/terrain loading, Cesium visualization |
| Time of concentration (Tc) from watershed stats if not already exposed | |
| Flood extent: Q→stage (rating curve), inundation = HAND ≤ stage using existing HAND raster | |

## Chosen Approach: New hydrology module, then integrate

Create a dedicated module (e.g. `src/core/hydrology/`) with **only what hydrocesium does not yet have**:

- **Reuse:** Watershed (flow direction, flow accumulation, catchment, river network) and HAND from `src/core/watershed/` — hydrology module consumes their outputs (catchment mask, HAND raster, Tc/area if exposed).
- **New:** `rainfall.ts`, `runoff.ts`, `unitHydrograph.ts`, `hydrograph.ts`, and flood-extent logic (Q→stage, inundation = HAND ≤ stage). Subbasin routing (lag/Muskingum) is optional, to be added in the same module if needed.

Build the module first; then wire it into Vue/Cesium in one integration pass. The plan phase should define interfaces between watershed and hydrology (e.g. Tc, area, HAND raster).

## Open Questions

- **Raster size / performance:** For large DEMs, run in main thread vs Web Worker (or Node script) to avoid UI freeze? Defer until first bottleneck.
- **CRS and units:** simple-hms uses rasterio transform and consistent mm/m³/s. Hydrocesium needs a single convention (e.g. WGS84 + m, or match DEM CRS) and consistent units in the port.
- **Testing:** Compare against simple-hms outputs (same DEM, CN, outlet, storm) for regression; consider fixture rasters and expected hydrograph/HAND snippets.

## Resolved Questions

- **Clone type:** New product inspired by simple-hms (not a literal repo copy).
- **Hydrocesium meaning:** The project at `D:\MyResearch\hydrocesium`.
- **Integration style:** Port hydrology to TypeScript inside hydrocesium (no Python backend).
- **Approach:** New hydrology module, then integrate. Watershed and HAND reused from `src/core/watershed/`; hydrology module consumes their outputs.

## Next Steps

→ Run `/workflows:plan` when ready to turn this into an implementation plan (file layout, order of port, APIs, and how each piece plugs into existing hydrocesium UI and Cesium layers).
