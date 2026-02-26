# FAQ — Hypothetical Storm Hydrograph Calculator

Frequently asked questions and answers. Updated as questions arise.

---

## Questions

### I only have DEM and CN map. What else do I need?

**DEM and CN are the only spatial datasets required.** You must also supply:

- **Outlet coordinates** — (x, y) in the DEM’s CRS. The point where the watershed drains (e.g., gauge, culvert, dam). There is no auto-detection; you specify the outlet.
- **Design storm** — depth (mm), duration (hr), and temporal pattern (e.g. `type2`, `uniform`).
- **P2** — 2-year 24-hour rainfall (mm) for time-of-concentration. Default is 50 mm; use NOAA Atlas 14 or regional data for better accuracy.

For **flood maps**, you also need a rating curve (Q vs stage) or direct stage input. Use `rating_curve_rectangular` or `rating_curve_trapezoidal` from `src.rating_curve` for simple channel geometries.

### What is P2 (2-yr 24-hr rainfall)?

**P2** is the **24-hour rainfall depth** for a storm with a **2-year return period**—i.e., a storm that, on average, is exceeded once every 2 years (about 50% annual exceedance probability). It is a precipitation frequency statistic from regional climate data.

**Why it matters:** P2 is used in the **sheet-flow** term of the time-of-concentration (Tc) formula. The TR-55 sheet-flow equation is `t_sheet = 0.007(nL)^0.8 / (P2^0.5 × S^0.4)` (hr). P2 appears in the denominator—wetter climates (higher P2) yield shorter sheet-flow times and faster runoff response.

**Units:** Use **mm** in this tool. NOAA Atlas 14 and many regional datasets provide values in inches; convert with 1 in = 25.4 mm.

**Where to get it:** NOAA Atlas 14 Precipitation Frequency Data Server ([hdsc.nws.noaa.gov/pfds/](https://hdsc.nws.noaa.gov/pfds/)) or regional precipitation frequency atlases. Enter your site location and read the 2-year, 24-hour precipitation depth. Default in the tool is 50 mm if not supplied.

### Can I use any rainfall depth and duration (e.g., 150 mm over 10 min)?

**Yes.** The tool accepts any depth (mm) and duration (hours). Duration is in hours—e.g., 10 min = 10/60 ≈ 0.167 hr.

**Does it make sense?** It depends on your design purpose and region:

- **Intensity:** 150 mm in 10 min ≈ 900 mm/hr. That is very high—typical 24-hr design storms have average intensities of ~2–10 mm/hr. Check local **intensity–duration–frequency (IDF)** curves (e.g., NOAA Atlas 14) to ensure your values are plausible for your return period.
- **Time of concentration (Tc):** If Tc > storm duration, the watershed is not fully contributing during the storm; the peak may be underestimated because runoff from the farthest areas arrives after the storm ends.
- **SCS patterns:** Type I/II/III were derived for 24-hour storms. The tool scales them to shorter durations, but the method was not calibrated for very short storms.
- **Typical practice:** Many designs use 24-hour storms because they often produce the critical peak for moderate watersheds. Short storms (e.g., 10 min) are common for small urban catchments or IDF-based designs.

**Summary:** Use any depth and duration that match your local IDF data and design intent. For most watersheds, 24-hour storms are the usual choice unless you have a specific reason for a short-duration event.

### How is the outlet specified?

The outlet (pour point) is **specified manually by the user** as coordinates (x, y) in the DEM’s CRS. There is no automatic outlet detection. The user provides the point where the watershed drains; the tool then snaps it to the nearest high-flow cell (where flow accumulation > `snap_threshold`) before delineation. The default `snap_threshold` is 500 cells; increase it for larger watersheds or if the outlet snaps to a tributary.

### Why can’t the outlet be auto-detected?

It’s not technically impossible, but automatic outlet detection isn’t used because the outlet is inherently a **design choice**. A DEM can drain to many points (stream junctions, gauges, dams, coast). There is no single “correct” outlet without knowing the user’s purpose (e.g., “watershed above this gauge” or “above this dam”). Auto-detection would need extra rules (e.g., “lowest point,” “largest stream”) that may not match the intended analysis. Manual specification keeps the workflow explicit and under user control.

### Does the hydrograph have meaning for the outlet?

**Yes.** The hydrograph is the **flow at the outlet**—discharge (Q, m³/s) over time from the watershed draining to that point. The watershed is delineated upstream of the outlet, so the hydrograph represents the combined runoff from all contributing area reaching the outlet. Use it for design at that location (e.g., culvert, bridge, dam spillway, gauge).

### What is baseflow?

**Baseflow** is the portion of streamflow that comes from **delayed sources** rather than direct runoff. It includes groundwater discharge (water seeping from aquifers into the stream), soil moisture drainage (slow flow through soil and subsurface layers), and interflow (shallow subsurface flow that reaches the channel with delay).

It is contrasted with **stormflow** (quickflow)—the fast response to rainfall from surface runoff and near-surface flow. Baseflow varies slowly, dominates flow between storms and during dry periods, and reflects aquifer and soil properties, geology, and land use. It is often modeled as exponential decay during recession (see baseflow recession). Used for baseflow separation, low-flow analysis, groundwater recharge estimation, and water supply planning.

### What is baseflow recession?

**Baseflow recession** is the **decline in streamflow over time** when there is no rainfall or surface runoff. It describes the falling limb of a hydrograph as flow returns toward pre-storm levels. The recession is driven mainly by groundwater discharge and drainage from soil and shallow aquifers into the stream.

**Typical behavior:** Flow decreases exponentially or as a power law, e.g. Q(t) = Q₀·k^t or Q(t) = Q₀·e^(-αt), where Q₀ is initial flow, k or α is the recession constant, and t is time. The recession constant reflects aquifer and soil properties—slower drainage gives a gentler recession.

**Uses:** Low-flow frequency analysis, baseflow separation (splitting storm runoff from groundwater contribution), groundwater recharge estimation, and calibrating recession parameters in rainfall–runoff models.

### How do I add base flow to the hydrograph?

The tool supports **optional base flow** added to direct runoff. Pass `base_flow_m3s` to `compute_design_hydrograph` or `compute_design_flood_map`; use `base_flow_recession_k_min` for exponential recession instead of constant base flow.

**Constant base flow:** Set `base_flow_m3s` only. Example: `base_flow_m3s=0.5` adds 0.5 m³/s throughout.

**Exponential recession:** Set both `base_flow_m3s` and `base_flow_recession_k_min`. Base flow decays as Q(t) = Q₀·exp(−t/k), where t is time in minutes and k is the recession time constant. Example: `base_flow_m3s=0.5`, `base_flow_recession_k_min=360` gives Q₀ = 0.5 m³/s with e-folding time 6 hours.

```python
# Constant base flow (0.5 m³/s)
df = compute_design_hydrograph(..., base_flow_m3s=0.5)

# Exponential recession (Q0=0.5 m³/s, k=360 min)
df = compute_design_hydrograph(..., base_flow_m3s=0.5, base_flow_recession_k_min=360)
```

The hydrograph plot shows base flow as a dashed brown line and total flow as a solid red line. The GUI has inputs for “Base flow (m³/s, 0=none)” and “Base recession k (min, blank=constant)”.

### What changes when using subbasin mode vs lumped?

**Subbasin mode** subdivides the watershed at stream junctions, computes runoff per subbasin, routes with lag or Muskingum, and aggregates at the outlet. **Lumped mode** treats the whole watershed as one unit.

**Expected differences in results:**

| Aspect | Lumped | Subbasins |
|--------|--------|-----------|
| **Peak flow** | Usually higher | Usually lower (routing spreads flow in time) |
| **Time to peak** | Earlier | Later (routing delays) |
| **Recession limb** | Sharper | Smoother, longer (channel storage) |
| **Total volume** | Same | Same (same rainfall and area) |

**When differences are small:** Simple watersheds (one main stem, few tributaries) or when no stream junctions are found (subbasin mode falls back to lumped).

**When differences are larger:** Branched networks, varying CN/Tc per subbasin, or longer reaches (more routing delay and attenuation).

**Usage:** `compute_design_hydrograph_subbasins(..., routing_method='lag'|'muskingum')` or `python example.py --subbasins`.

### What are lag and Muskingum routing? What are the differences and pros/cons?

**Lag routing** is a simple time shift: the inflow hydrograph is delayed by a fixed lag time; shape and volume are unchanged. Formula: Q_out(t) = Q_in(t − lag). One parameter: lag time (minutes).

**Muskingum routing** is a storage-based method that models channel storage as prism + wedge storage. It delays and attenuates the flood wave. Formula: Q₂ = C₀I₂ + C₁I₁ + C₂Q₁ (mass conserved). Two parameters: K (travel time, hr) and X (weighting factor, 0–0.5).

**Differences:**

| Aspect | Lag | Muskingum |
|--------|-----|-----------|
| Attenuation | None | Yes (peak reduced, recession lengthened) |
| Parameters | Lag time only | K and X |
| Peak | Same as inflow | Lower than inflow |
| Shape | Same as inflow, shifted | Smoothed and spread out |

**Pros/cons:**

**Lag:** Simple — one parameter, easy to estimate (e.g., reach length / velocity). Fast and stable. Good when attenuation is small (short, steep reaches). **Cons:** No attenuation; cannot represent channel storage.

**Muskingum:** Models attenuation; represents storage and hysteresis; widely used in practice (e.g., HEC-HMS). **Cons:** Two parameters (K, X) to estimate or calibrate; X has limited physical meaning; K and X can vary with flow.

**When to use:** Use **lag** for short reaches, steep slopes, or when data are limited. Use **Muskingum** for longer reaches, mild slopes, or when attenuation matters and you can calibrate K and X.

### How is time of concentration (Tc) computed?

**Tc** is the time for runoff to travel from the hydrologically farthest point in the watershed to the outlet. The tool uses **path-based TR-55** when flow direction and accumulation are available:

1. **Trace longest flow path** — From the outlet, trace upstream via D8 flow direction to find the cell farthest from the outlet along the flow path.
2. **Segment the path** — From head to outlet: sheet flow (first ≤100 m), shallow concentrated flow (next 300 m), channel flow (remainder).
3. **Apply TR-55 formulas** — Sheet: `t = 0.007(nL)^0.8/(P2^0.5 S^0.4)` (hr); shallow: `t = L/V` with `V = 16.13√S` (unpaved) or `20.33√S` (paved) ft/s; channel: Manning `V = (1.49/n)R^(2/3)S^(1/2)`, then `t = L/V`.
4. **Lag** — `tp = 0.6 × Tc` (minutes).

If flow direction, accumulation, transform, or outlet are missing, the tool falls back to an area-based estimate. Optional parameters: `shallow_paved` (use paved velocity for shallow flow), `channel_r_m` (hydraulic radius for channel Manning estimate).

### What is a TR-55 estimate?

**TR-55** (Technical Release 55) is the NRCS document *Urban Hydrology for Small Watersheds*. A **TR-55 estimate** is any value or procedure taken from that manual.

**What TR-55 covers:** Curve numbers (CN) for runoff; time of concentration (Tc) from flow-path segments (sheet, shallow concentrated, channel flow); SCS unit hydrograph and lag; SCS rainfall temporal distributions (Type I, IA, II, III) in Appendix B.

**In this tool:** TR-55 is used for rainfall temporal distributions, SCS runoff (excess rainfall from CN), Tc and lag from flow-path segments (sheet, shallow concentrated, channel flow), and unit hydrograph peak rate factor and dimensionless ordinates. Tc is computed by tracing the longest flow path from watershed boundary to outlet, segmenting into sheet (≤100 m), shallow (next 300 m), and channel flow, and applying TR-55 formulas per segment. A TR-55 estimate is thus a value or method derived from that NRCS manual (e.g., Tc, lag, CN-based runoff, or UH parameters).

### What are loss methods?

**Loss methods** are procedures that estimate how much rainfall is **lost** (does not become direct runoff). They partition total rainfall into losses (infiltration, interception, depression storage, etc.) and **excess rainfall** (effective rainfall) that produces runoff.

**Common methods:** SCS Curve Number (empirical, S = 25400/CN − 254, Ia = 0.2S); Green-Ampt (physically based infiltration); Initial & Constant (constant loss rate after initial abstraction); Deficit and Constant; Smith Parlange.

**In this tool:** Only **SCS Curve Number** is implemented. Green-Ampt and Initial & Constant are listed as possible future additions in the plan.

### What is transform (in Possible Updates)?

**Transform** is the step that converts **excess rainfall** into a **runoff hydrograph** (discharge vs. time). Pipeline: (1) **Loss** — rainfall → excess rainfall; (2) **Transform** — excess rainfall → direct runoff hydrograph.

**Current method:** **SCS Unit Hydrograph** — dimensionless UH scaled by area, lag, and peak rate factor, convolved with excess rainfall.

**Possible updates (PLAN.md):** Add alternative transform methods: **Clark** (time–area with storage routing) and **Snyder** (synthetic UH with different peak/time parameters). These would be selectable (e.g. `transform='scs' | 'clark' | 'snyder'`) and produce different hydrograph shapes and timing.

### What parameters would Clark or Snyder UH require?

**Yes.** Both need more parameters than SCS UH.

**Clark:** Tc (time of concentration), R (storage coefficient). Can be estimated from basin geometry (L, Lc, slope) or regional regression equations.

**Snyder:** Ct (time coefficient, ~1.35–1.65 metric), Cp (peak coefficient, ~0.56–0.69), L (main channel length), Lc (length from outlet to watershed centroid). Lag: tl = Ct(L×Lc)^0.3. Ct and Cp are empirical and vary by region, land use, and topography.

**Compared with SCS UH:** SCS uses area, Tc (or lag), and PRF (often default 484)—no Ct, Cp, or R. Clark and Snyder would require these inputs (or regional equations) if added.

### Is the current transform (SCS UH) better than Clark or Snyder?

**It depends.** Each has trade-offs.

**SCS UH advantages:** Fewer inputs (area, Tc, PRF); Tc is already computed from the DEM; no Ct, Cp, R, or Lc; standard for US design (TR-55, NRCS); works well for ungaged watersheds with only DEM, CN, and P2.

**Clark/Snyder advantages:** Clark models storage (R) explicitly; Snyder’s Ct/Cp can be calibrated regionally; both can produce different hydrograph shapes when needed.

**Summary:** SCS is usually better when you have limited data and want simplicity. Clark or Snyder are useful when you have regional parameters or calibration data, or need a different hydrograph shape.

### What parameters would Green-Ampt require?

**Yes.** Green-Ampt is physically based and needs soil and moisture parameters instead of a single curve number.

**Typical parameters:** Saturated hydraulic conductivity (Ks), porosity (θs), initial moisture content (θi), wetting front suction head (ψf). These come from lab/field data or soil databases (e.g., USDA soil texture classes).

**Compared with SCS CN:** SCS CN uses one parameter (CN) from land use and soil type. Green-Ampt would require additional inputs (Ks, θs, θi, ψf) and possibly a soil map or lookup table. SCS CN stays simpler when only a CN map is available.

### What is SCS Type I?

**SCS Type I** is one of four NRCS 24-hour rainfall temporal distributions (I, IA, II, III). It defines how a given storm depth is distributed over time—i.e., the hyetograph shape.

- **Region:** Pacific Northwest (Pacific maritime climate: wet winters, dry summers)
- **Duration:** 24 hours (standard)
- **Intensity:** More intense than Type IA
- **Use:** Design storms for peak discharge and runoff volume in that region

The distribution is given as dimensionless cumulative fractions (percent of total depth vs. percent of duration), e.g. in NRCS NEH Table 4-2. Type II is used for most of the US; Type III for Gulf Coast/southeastern US.

### Can SCS Type I/II/III be used for non-USA areas?

**Use with caution.** SCS rainfall types are calibrated to US regional climates (Pacific NW, continental, Gulf Coast). For non-USA areas, they may not match local storm patterns (e.g., monsoon, Mediterranean, tropical). Prefer **local or regional design storm distributions** from national atlases or hydrology manuals when available. If no local data exist, Type II is sometimes used as a conservative default (front-loaded storm), but results may over- or underestimate peaks. The tool’s **uniform** or **user-specified** hyetograph options allow non-US patterns to be supplied directly.

### How do I use the uniform pattern?

The **uniform** pattern distributes the design rainfall depth evenly over the storm duration—constant intensity for every timestep.

**Usage:** Pass `pattern='uniform'` to the rainfall or main API:

```python
# Rainfall module only
hyetograph = create_design_hyetograph(depth_mm=100, duration_hr=24, pattern='uniform', timestep_min=15)

# Full pipeline
df = compute_design_hydrograph(..., design_depth_mm=100, duration_hr=24, pattern='uniform', ...)
```

**Behavior:** Total depth ÷ number of timesteps = rainfall per timestep. Example: 100 mm over 24 hr with 15-min timesteps → 96 steps → ~1.04 mm per step. No peak concentration; useful when temporal distribution is unknown or for simple sensitivity checks.

### What are the other pattern types?

| Pattern | Value | Description |
|---------|-------|-------------|
| **SCS Type I** | `'type1'` | Pacific Northwest; 24-hr; more intense than IA |
| **SCS Type IA** | `'type1a'` | Pacific Northwest; 24-hr; milder than I |
| **SCS Type II** | `'type2'` | Most of US; 24-hr; front-loaded (default) |
| **SCS Type III** | `'type3'` | Gulf Coast, southeastern US; 24-hr |
| **Uniform** | `'uniform'` | Constant intensity over duration |
| **User-specified** | custom array | Supply your own cumulative or incremental hyetograph (mm per timestep) |

User-specified bypasses the built-in distributions: pass a numpy array of rainfall depth per timestep instead of a pattern string. Use for local/regional design storms or custom scenarios.

### What is Q-to-stage in the plan?

**Q-to-stage** converts peak discharge (Q, m³/s) from the design hydrograph to water surface elevation (stage H, m) at the outlet. The hydrograph gives flow; flood extent needs water level. Q-to-stage provides that link.

**Options in the plan:** (1) **User rating curve**—table of (Q, stage) pairs, interpolate to get stage for peak Q; (2) **Manning uniform-flow**—approximate stage from Q using channel geometry (rectangular/trapezoidal) and slope; (3) **Direct stage**—user supplies H directly, bypassing Q-to-stage.

**API:** `discharge_to_stage(peak_q_m3s, rating_curve=None, stage_m=None) → float` (m). The `discharge_to_stage` function is used internally by `compute_design_flood_map`; you typically pass `rating_curve` or `stage_m` to that function.

### What is stage?

**Stage** is the **water surface elevation**—the height of the water surface above a datum (e.g., m NAVD88). It is the water level at a point (e.g., the outlet). The hydrograph gives discharge (Q, m³/s); stage is the corresponding water level (H, m). Q-to-stage converts peak discharge to stage via a rating curve or Manning’s equation so you can estimate flood depth and extent.

### What is a rating curve? How is it generated?

A **rating curve** is the relationship between **discharge (Q)** and **stage (water level)** at a given cross-section. It is typically a table of (Q, stage) pairs or a power-law such as Q = a(H − b)^c, where H is stage and a, b, c are fitted parameters. It lets you convert discharge to stage (or vice versa) at that location.

**How it is generated:** (1) **Field measurements**—at a stream gauge, discharge is measured (e.g., current meter, ADCP) at various water levels; over time you collect (Q, stage) pairs and fit a curve. (2) **Hydraulic modeling**—use Manning's equation or 1D/2D models with channel geometry to compute Q for given stage (or stage for given Q). (3) **Published data**—agencies (e.g., USGS) publish rating curves for gauged sites from historical measurements. (4) **Theoretical**—for simple geometries (rectangular, trapezoidal), Q–stage can be derived from Manning's equation.

**In this tool:** You can supply a rating curve (list of (Q, stage) pairs) or use the built-in **Manning-based rating curves** in `src.rating_curve` for rectangular and trapezoidal channels. Use `rating_curve_rectangular(b, n, s, ...)` or `rating_curve_trapezoidal(b, z, n, s, ...)` to generate a rating curve from channel geometry, then pass it to `compute_design_flood_map(..., rating_curve=rc)`.

### Can this generate flood maps?

**Yes.** The tool supports **HAND-based flood maps** for design rainfall and duration. Workflow: design rainfall → hydrograph → peak discharge → Q-to-stage (rating curve) → water level H → inundation where HAND < H.

**Requirements:** A rating curve (Q vs stage) or direct stage input. Use `rating_curve_rectangular` or `rating_curve_trapezoidal` from `src.rating_curve` to derive Q-stage from Manning's equation for simple channel geometries. HAND assumes static stage—no routing of the flood wave. Suitable for design flood extent, not dynamic inundation timing.

**For full hydraulic modeling:** Use the output hydrograph as input to HEC-RAS 1D/2D, LISFLOOD-FP, or ANUGA for routing, backwater, and dynamic inundation.

### Can the hydrograph be used as an upstream boundary condition for HEC-RAS or shallow water models?

**Yes.** The hydrograph is a time series of discharge (Q, m³/s) vs time—exactly what HEC-RAS and 2D shallow water models expect for an **inflow boundary condition**.

**HEC-RAS (1D):** Use the hydrograph as an **upstream flow boundary** at the cross-section where the watershed drains. Export the DataFrame columns `time_min` and `flow_m3s` to a file (e.g., two-column text: time, discharge). HEC-RAS typically accepts time in seconds or hours and discharge in m³/s or cfs—convert if needed (e.g., `time_sec = time_min * 60`).

**2D shallow water (HEC-RAS 2D, LISFLOOD-FP, ANUGA, etc.):** Apply the hydrograph as an **inflow boundary** at the cell(s) where flow enters the domain. The discharge time series is specified at the boundary; the model routes it through the domain.

**Spatial alignment:** The hydrograph represents flow at the **watershed outlet** from this tool. Place the boundary in the hydraulic model at the corresponding location—the upstream end of the reach or the inflow edge of the 2D domain where that watershed contributes.

**Export:** The tool returns a pandas DataFrame with `time_min` and `flow_m3s`. Save to CSV or a format your target software accepts:

```python
df = compute_design_hydrograph(...)
df[["time_min", "flow_m3s"]].to_csv("inflow_hydrograph.csv", index=False)
# Or convert time to seconds for HEC-RAS: df["time_sec"] = df["time_min"] * 60
```

### What is 2D diffusive wave?

**2D diffusive wave** is a simplified form of the 2D shallow water equations used for flood inundation. It assumes flow is driven by water surface slope balanced by friction; inertial terms (acceleration, advection) are neglected.

**Characteristics:** Simpler and more stable than full shallow water; suitable for slow, shallow floodplain flow; less accurate for fast flows (e.g., dam breaks). Used in LISFLOOD-FP, ANUGA, and similar models.

**Compared with HAND (current tool):** HAND uses a static water level; inundation = cells where HAND < H; no routing. 2D diffusive wave routes the flood wave over time through the domain and can represent backwater and flow direction changes. PLAN.md lists 2D diffusive wave as a possible replacement for HAND to enable dynamic flood routing.

### Which is better: full shallow water or 2D diffusive wave?

**It depends on the application.** Neither is universally better.

**2D diffusive wave:** Simpler, more stable, larger timesteps, less compute; suitable for slow floodplain flow. Less accurate for fast flows. Use for design flood extent, slow overland flow, gentle terrain.

**Full shallow water (dynamic wave):** Includes inertia and advection; better for fast flows and steep slopes. More complex, can be less stable, needs smaller timesteps and more compute. Use for dam breaks, steep channels, fast flows.

**Summary:** For typical design flood mapping, **2D diffusive wave** is usually sufficient and easier to run. Use **full shallow water** when inertia matters (e.g., dam breaks, fast flows).
