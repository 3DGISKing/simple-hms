# FAQ — Hypothetical Storm Hydrograph Calculator

Frequently asked questions and answers. Updated as questions arise.

---

## Questions

### How is the outlet specified?

The outlet (pour point) is **specified manually by the user** as coordinates (x, y) in the DEM’s CRS. There is no automatic outlet detection. The user provides the point where the watershed drains; the tool then snaps it to the nearest high-flow cell (where flow accumulation > `snap_threshold`) before delineation. The default `snap_threshold` is 500 cells; increase it for larger watersheds or if the outlet snaps to a tributary.

### Why can’t the outlet be auto-detected?

It’s not technically impossible, but automatic outlet detection isn’t used because the outlet is inherently a **design choice**. A DEM can drain to many points (stream junctions, gauges, dams, coast). There is no single “correct” outlet without knowing the user’s purpose (e.g., “watershed above this gauge” or “above this dam”). Auto-detection would need extra rules (e.g., “lowest point,” “largest stream”) that may not match the intended analysis. Manual specification keeps the workflow explicit and under user control.

### Does the hydrograph have meaning for the outlet?

**Yes.** The hydrograph is the **flow at the outlet**—discharge (Q, m³/s) over time from the watershed draining to that point. The watershed is delineated upstream of the outlet, so the hydrograph represents the combined runoff from all contributing area reaching the outlet. Use it for design at that location (e.g., culvert, bridge, dam spillway, gauge).

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
