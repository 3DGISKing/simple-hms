---
title: Add hydrology module to hydrocesium (port from simple-hms)
type: feat
status: active
date: 2026-02-26
---

# Add hydrology module to hydrocesium (port from simple-hms)

## Enhancement Summary

**Deepened on:** 2026-02-26  
**Sections enhanced:** Proposed Solution, Technical Considerations, Implementation Phases (Phases 1–4), References.  
**Research sources:** Context7 (TypeScript), Web search (SCS/TR-55/HAND best practices, HEC-HMS docs).

### Key Improvements

1. **SCS/TR-55 formulas** — Documented Tc segment formulas (sheet, shallow concentrated, channel) and SCS UH parameters (Tp, Qp, PRF) with references for implementation.
2. **TypeScript API design** — Optional parameters and interfaces for hydrology module public API; separate options types per submodule to keep watershed ↔ hydrology boundary clear.
3. **HAND + rating curve** — Clarified that inundation = HAND ≤ stage; stage from Q via synthetic rating curve (e.g. Manning); roughness (n) is critical; reference to NWM–HAND methodology.
4. **Edge cases and validation** — CN bounds (1–100), Ia = 0.2S, PRF range; TR-55 unit conversions (ft vs m); no double-accounting of initial abstraction vs depression storage.

### New Considerations Discovered

- **PRF (Peak Rate Factor):** Standard ~484; steep terrain ~600; flat areas ≤100; should be configurable in `scsUnitHydrograph` and `computeDesignHydrograph`.
- **TR-55 units:** Original TR-55 uses feet and inches; simple-hms uses metric (m, mm). Port must use consistent metric internally; document any conversion from P2 (mm) in formulas.
- **CN aggregation:** HEC-HMS supports gridded CN with “CURVE NUMBER” and composite vs pervious-only; avoid double-accounting with impervious % or Ia overrides.
- **HAND accuracy:** NWM–HAND studies show ~70% of cases with ≥80% agreement; accuracy lower in lower-order streams and low relief; document as limitation in flood extent output.

---

## Overview

Implement a new **hydrology module** in the hydrocesium project (`D:\MyResearch\hydrocesium`) that provides design-storm hydrograph and flood-extent logic by porting the relevant parts of simple-hms. Watershed-from-DEM and HAND are **not** reimplemented; they are consumed from hydrocesium’s existing `src/core/watershed/`. The new module adds: design rainfall (hyetograph), SCS runoff (CN, excess rainfall), time of concentration (Tc), SCS unit hydrograph, convolution pipeline, and flood extent from Q→stage using existing HAND.

**Source of truth:** Brainstorm `docs/brainstorms/2026-02-26-hydrocesium-port-simple-hms-brainstorm.md`.

## Problem Statement / Motivation

- Hydrocesium already has watershed delineation, flow direction, flow accumulation, catchment, and HAND in TypeScript.
- It does not yet compute design hydrographs (design storm → SCS runoff → unit hydrograph → flow) or derive flood extent from a design flow and rating curve.
- Porting these from simple-hms (Python) into a dedicated hydrology module in hydrocesium allows a single stack (Vue + Cesium + TS), no Python backend, and end-to-end workflow: DEM + CN + outlet + design storm → hydrograph and HAND-based flood map.

## Proposed Solution

- Add `src/core/hydrology/` (or equivalent) under hydrocesium.
- Implement only the pieces simple-hms has that hydrocesium lacks:
  - **rainfall.ts** — Design hyetograph (SCS Type I/IA/II/III, uniform); same inputs/outputs as `simple-hms/src/rainfall.py`.
  - **runoff.ts** — Weighted CN from raster (or from pre-aggregated value), SCS excess rainfall from hyetograph + CN; port of `runoff.py` logic.
  - **timeOfConcentration.ts** — Tc (hr) and lag (min) from longest flow path + TR-55; port of `watershed.compute_time_of_concentration` and path-tracing helpers; consumes fdir, acc, dem, catchment mask, transform, outlet from watershed module.
  - **unitHydrograph.ts** — SCS dimensionless UH ordinates, lag → Tp → Qp, normalize to 1 mm; port of `unit_hydrograph.py`.
  - **hydrograph.ts** — Convolution of excess rainfall with UH; optional base flow; main API that composes rainfall → runoff → Tc → UH → convolution; returns time series (time_min, flow_m3s, rainfall_mm, excess_mm).
  - **floodExtent.ts** — Given design flow (m³/s), rating curve (Q→stage), and existing HAND raster from watershed module: compute stage from Q, then inundation = cells where HAND ≤ stage; output raster or mask compatible with existing Cesium/raster display.
- Define clear **interfaces** between watershed and hydrology: e.g. `SingleBandRaster` (or equivalent) for DEM, fdir, acc, HAND, catchment mask; geotransform and dimensions; outlet (x, y); optional stream network / Tc inputs.
- Use **existing deps** in hydrocesium (geotiff, etc.); add no new dependencies unless necessary.
- **CRS and units:** Adopt one convention (e.g. mm for rainfall, m for elevation, m³/s for flow, minutes for time) and document it; align with simple-hms for comparability.

## Technical Considerations

- **Watershed outputs:** Hydrology module will receive from `src/core/watershed/`: flow direction raster, flow accumulation raster, catchment mask (boolean or raster), DEM (conditioned), HAND raster, geotransform (originX, originY, resX, resY), cell size, and outlet (x, y). Area (km²) can be computed from catchment mask and cell size. Stream network (for Tc) can be derived from acc + threshold or passed in if already computed.
- **CN aggregation:** simple-hms uses rasterio to reproject/aggregate CN raster to watershed grid. In hydrocesium, CN may be available as a raster (geotiff); aggregate within catchment mask (weighted mean) in TS, or accept a single pre-aggregated CN for the catchment.
- **Tc:** simple-hms implements longest-flow-path tracing and TR-55 sheet/shallow/channel segments. Port this logic into the hydrology module so it takes fdir, acc, dem, mask, transform, outlet, p2_24hr_mm, stream_threshold and returns tc_hr, lag_min.
- **Performance:** For large DEMs, consider running heavy raster steps (e.g. CN aggregation, Tc path tracing) in a Web Worker to avoid UI freeze; defer until needed.
- **Testing:** Compare hydrograph and flood extent outputs against simple-hms for the same inputs (fixture DEM, CN, outlet, design storm, P2).

### Research Insights

**SCS Unit Hydrograph (HEC-HMS alignment):**

- Time to peak: **Tp = (tr/2) + tp** (tr = timestep, tp = lag). Peak discharge: **Qp = (PRF × A) / Tp** (A in consistent area units). Lag tp ≈ 0.6 × Tc.
- PRF: typically 484; range ~100 (flat) to ~600 (steep). Expose as parameter in `scsUnitHydrograph` and options.

**TR-55 Time of concentration:**

- Tc = T_sheet + T_shallow + T_channel. Sheet flow (e.g. first 100 m): **Tt = 0.007(nL)^0.8 / (P2^0.5 × s^0.4)** (n = Manning, L = length, P2 = 2-yr 24-h rainfall, s = slope). Use metric conversion where TR-55 is in ft/in.
- Shallow concentrated: velocity V = 16.13√s (unpaved) or 20.33√s (paved) m/s equivalent; Tt = L/(3600×V).
- Channel: Manning’s equation for velocity; travel time = length/velocity. Sum segment times for Tc, then lag_min = 0.6 × Tc_hr × 60.

**HAND flood extent:**

- Inundation = cells where HAND ≤ stage (m). Stage from Q via rating curve (synthetic or table). Synthetic curves often use Manning (geometry + n); roughness n is the most sensitive parameter.
- Reference: NWM–HAND style mapping; acceptable agreement in many cases but lower in small streams and low relief—document as limitation.

**TypeScript API design:**

- Use interfaces with optional parameters for options objects (e.g. `ComputeTimeOfConcentrationOptions` with required fdir, acc, dem, mask, outlet; optional streamThreshold, p2_24hr_mm). Keep watershed types (e.g. `SingleBandRaster`) in watershed; hydrology imports and uses them without redefining.

**References:**

- [HEC-HMS SCS Unit Hydrograph](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/scs-unit-hydrograph-model)
- [TR-55 Chapter 3 (Tc)](https://ce531.groups.et.byu.net/syllabus/Documents/TR55Chap3.pdf)
- [NWM–HAND flood mapping evaluation](https://nhess.copernicus.org/articles/19/2405/2019/)
- [GIS synthetic rating curves and HAND](https://link.springer.com/article/10.1007/s11069-021-04892-6)

## Acceptance Criteria

- [x] **rainfall.ts** — `createDesignHyetograph(depthMm, durationHr, pattern, timestepMin)` returns array of mm per timestep; patterns: type1, type1a, type2, type3, uniform.
- [x] **runoff.ts** — `computeExcessRainfall(hyetographMm, cn)` returns incremental excess mm; `aggregateCn(cnData, catchmentMask, width, height)` returns weighted mean CN (same-dimension raster; no reprojection in Phase 1).
- [x] **timeOfConcentration.ts** — `computeTimeOfConcentration(options)` with fdir, acc, dem, watershedMask, width, height, geotransform, outlet, p2_24hr_mm returns `{ tcHr, lagMin }`; path-based TR-55 + area fallback.
- [x] **unitHydrograph.ts** — `scsUnitHydrograph(areaKm2, lagMin, timestepMin, prf)` returns UH ordinates (m³/s per mm excess); SCS dimensionless curve and 1 mm normalization.
- [x] **hydrograph.ts** — `computeDesignHydrograph(options)` accepts watershed rasters + dimensions + geotransform, outlet, cn, design storm, P2, timestep; returns `{ timeMin, flowM3s, rainfallMm, excessMm }` with optional baseFlowM3s; pipeline: rainfall → runoff → Tc → UH → convolution.
- [x] **floodExtent.ts** — `computeFloodExtent(handData, stageM, catchmentMask?)` returns depth Float32Array; `computeDesignFloodExtent(opts)` resolves stage from designFlowM3s + ratingCurveOrStage (fixed stage, function, or table); depth = stage − HAND where HAND < stage; optional catchment mask.
- [x] **Interfaces:** Types in hydrology (options for Tc, hydrograph, flood extent); watershed outputs consumed as raw arrays + dimensions + geotransform; no reimplementation of flow dir, flow acc, catchment, or HAND.
- [x] **Integration:** Wire hydrograph + flood extent into Vue/Cesium (e.g. "Design storm" action, hydrograph chart, flood layer); exact UI scope can be a follow-up task.

## Success Metrics

- Same DEM, CN, outlet, design storm, and P2 produce hydrograph and flood extent in hydrocesium within acceptable tolerance of simple-hms (e.g. peak flow and inundation area within a few percent, or documented differences).
- No duplicate watershed or HAND implementation; all such data comes from `src/core/watershed/`.

## Dependencies & Risks

- **Dependencies:** hydrocesium’s existing watershed APIs (`runFlowDirection`, `runFlowAccumulation`, `runCatchment`, `runComputeHand`, `SingleBandRaster`, geotransform). Raster/CN loading via geotiff or existing patterns.
- **Risks:** Tc/lag implementation detail may differ from simple-hms (e.g. path tracing on different grid representation); document and test with fixtures. Large rasters may require worker or chunking later.

## Implementation Phases

### Phase 1: Rainfall and runoff

- Add `src/core/hydrology/` in hydrocesium.
- Implement **rainfall.ts**: SCS cumulative curves (Type I, IA, II, III), uniform; `createDesignHyetograph(depthMm, durationHr, pattern, timestepMin)`.
- Implement **runoff.ts**: `computeExcessRainfall(hyetographMm, cn)` (SCS CN formula); `aggregateCn(...)` using catchment mask and CN raster/array (geotiff or in-memory).
- Add minimal types (e.g. `Hyetograph`, `ExcessRainfall`).
- Unit tests or fixture comparison with simple-hms for one storm and CN.

**Research insights (Phase 1):** SCS excess: S = 25400/CN − 254 (mm), Ia = 0.2×S; cumulative excess Pe = (P−Ia)²/(P−Ia+S) for P > Ia. Clip CN to 1–100. Do not combine custom Ia with depression storage (avoid double-accounting). For gridded CN, use area-weighted mean over catchment; ensure grid aligns with DEM/catchment extent.

### Phase 2: Time of concentration and unit hydrograph

- Implement **timeOfConcentration.ts**: longest flow path tracing from outlet to boundary (port from simple-hms `_trace_longest_flow_path`), TR-55 sheet/shallow/channel segments, return tc_hr and lag_min; inputs: fdir, acc, dem, mask, transform, outlet, p2_24hr_mm, stream_threshold.
- Implement **unitHydrograph.ts**: SCS dimensionless UH table, Tp from lag, Qp formula, interpolation to timestep, normalize to 1 mm over area; `scsUnitHydrograph(areaKm2, lagMin, timestepMin, prf)`.
- Convolution helper (excess × UH) in **hydrograph.ts** or a small `convolution.ts`.

**Research insights (Phase 2):** Longest flow path: BFS from outlet upstream using D8 reverse directions; sum segment lengths (√2×cell for diagonals). Segment path into sheet (e.g. ≤100 m), shallow (next ~300 m), channel (rest); apply TR-55 travel-time formula per segment. SCS dimensionless UH: use standard ordinates (t/Tp, q/qp); interpolate to timestep; normalize so volume = 1 mm over watershed area (A_km²×1e6×0.001 m³).

### Phase 3: Design hydrograph API

- Implement **hydrograph.ts**: `computeDesignHydrograph(options)` that:
  - Takes watershed-derived inputs (area, fdir, acc, dem, mask, transform, outlet, stream network or threshold), CN (or path to CN raster), design storm (depth, duration, pattern), P2, timestep, optional base flow.
  - Calls rainfall → runoff → Tc → UH → convolution; returns `{ timeMin, flowM3s, rainfallMm, excessMm }`.
- Document options type and units.
- Compare end-to-end with simple-hms on a small fixture (same DEM, CN, outlet, storm).

**Research insights (Phase 3):** Convolution: direct runoff at step i = Σ(excess[j] × UH[i−j]) for j ≤ i. Pad time series so length = len(excess) + len(UH) − 1; align time_min with timestep_min. Optional base flow: constant or exponential recession Q(t)=Q0×exp(−t/k). Expose options interface with optional fields (baseFlowM3s?, baseFlowRecessionKMin?) so callers can omit them.

### Phase 4: Flood extent and integration

- Implement **floodExtent.ts**: given HAND raster (from `runComputeHand`), design Q (m³/s), and rating curve (Q→stage in m) or fixed stage: compute stage, then inundation = HAND ≤ stage; return mask or raster compatible with `SingleBandRaster` / existing display.
- Optional: **ratingCurve.ts** — simple Q→stage from Manning (trapezoidal/rectangular) or table lookup, if not already present elsewhere.
- Integration: Add a way to run the full pipeline from the app (e.g. “Design storm” action that uses current catchment + HAND, runs hydrograph + flood extent, shows chart and flood layer); can be minimal (button + console or panel).

**Research insights (Phase 4):** Rating curve: accept (Q_m3s) => stage_m or table lookup; for Manning-based synthetic, document n and geometry. Inundation raster: same dimensions as HAND; value = 1 where HAND ≤ stage, 0 or noData elsewhere; mask by catchment so only wetted area within watershed is shown. HAND accuracy is lower in low-order streams and flat areas—consider a short disclaimer in UI or docs.

## References & Research

- **Brainstorm:** `docs/brainstorms/2026-02-26-hydrocesium-port-simple-hms-brainstorm.md`
- **simple-hms (reference):**
  - `src/rainfall.py` — hyetograph
  - `src/runoff.py` — excess rainfall, aggregate_cn
  - `src/unit_hydrograph.py` — SCS UH
  - `src/watershed.py` — `compute_time_of_concentration`, `_trace_longest_flow_path`
  - `src/hydrograph.py` — `compute_design_hydrograph`, convolution
  - `src/flood_map.py` — HAND usage, Q→stage, inundation
- **hydrocesium (consumers):**
  - `src/core/watershed/runFlowDirection.ts`, `runFlowAccumulation.ts`, `runCatchment.ts`, `runComputeHand.ts`, `SingleBandRaster.ts`, `runExtractRiverNetwork.ts`
  - `src/core/watershed/watershedRunner.ts` — how catchment/HAND are run and displayed

**External (from deepen research):**

- [HEC-HMS SCS Unit Hydrograph](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/scs-unit-hydrograph-model)
- [TR-55 Chapter 3 — Time of concentration](https://ce531.groups.et.byu.net/syllabus/Documents/TR55Chap3.pdf)
- [NWM–HAND flood mapping evaluation](https://nhess.copernicus.org/articles/19/2405/2019/)
- [GIS synthetic rating curves and HAND](https://link.springer.com/article/10.1007/s11069-021-04892-6)
- [Importing gridded SCS CN in HEC-HMS](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/gis-tools-and-terrain-data/gis-tutorials-and-guides/importing-gridded-scs-curve-number-in-hec-hms)

## Next Steps

- Run **`/workflows:work`** to start implementing (e.g. Phase 1 in hydrocesium).
- Optional: **Review and refine** this plan (e.g. clarify CRS or CN aggregation API).
- Plan has been **deepened** (2026-02-26) with SCS/TR-55 formulas, HAND best practices, and phase-level implementation notes.
