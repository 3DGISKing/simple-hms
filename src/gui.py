"""GUI for flood map and hydrograph visualization."""

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from mpl_toolkits.axes_grid1 import make_axes_locatable

from .flood_map import compute_design_flood_map
from .rating_curve import rating_curve_rectangular, rating_curve_trapezoidal

logger = logging.getLogger(__name__)


def _get_extent_from_transform(transform, rows: int, cols: int) -> tuple:
    """Return (left, right, bottom, top) for matplotlib imshow extent."""
    import rasterio.transform
    left, bottom, right, top = rasterio.transform.array_bounds(rows, cols, transform)
    return (left, right, bottom, top)


def _plot_stream_network(ax, stream_network, color="#1E88E5", linewidth=0.8):
    """Plot stream network LineStrings on axes."""
    fc = stream_network
    if hasattr(fc, "__geo_interface__"):
        fc = fc.__geo_interface__
    features = fc.get("features", [])
    for feat in features:
        geom = feat.get("geometry")
        if geom and geom.get("type") == "LineString":
            coords = np.array(geom["coordinates"])
            if len(coords) >= 2:
                ax.plot(coords[:, 0], coords[:, 1], color=color, linewidth=linewidth)


def run_gui():
    """Launch the Hypothetical Storm GUI."""
    root = tk.Tk()
    root.title("Hypothetical Storm — Flood Map & Hydrograph")
    root.minsize(900, 600)
    root.geometry("1200x750")

    # Ensure window is visible (fixes off-screen/hidden window on Windows/IDE)
    root.deiconify()
    root.update_idletasks()
    w, h = 1200, 750
    x = max(0, (root.winfo_screenwidth() - w) // 2)
    y = max(0, (root.winfo_screenheight() - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    # State
    df_result = [None]
    flood_raster_result = [None]
    watershed_result = [None]

    # Input frame
    input_frame = ttk.LabelFrame(root, text="Inputs", padding=8)
    input_frame.pack(fill=tk.X, padx=8, pady=4)

    def add_row(parent, label: str, default: str = "", width: int = 40) -> tk.Entry:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=18, anchor=tk.W).pack(side=tk.LEFT)
        entry = ttk.Entry(row, width=width)
        entry.insert(0, default)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        return entry

    dem_entry = add_row(input_frame, "DEM path:", "data/dem.tif")
    cn_entry = add_row(input_frame, "CN path:", "data/cn.tif")
    outlet_x_entry = add_row(input_frame, "Outlet X:", "1074538", width=12)
    outlet_y_entry = add_row(input_frame, "Outlet Y:", "1476948", width=12)
    depth_entry = add_row(input_frame, "Design depth (mm):", "100", width=10)
    duration_entry = add_row(input_frame, "Duration (hr):", "24", width=10)
    base_flow_entry = add_row(input_frame, "Base flow (m³/s, 0=none):", "0", width=10)
    recession_k_entry = add_row(input_frame, "Base recession k (min, blank=constant):", "", width=10)

    # Stage: direct or from rating curve (matches API)
    stage_frame = ttk.LabelFrame(input_frame, text="Stage (water level)", padding=4)
    stage_frame.pack(fill=tk.X, pady=4)
    stage_mode_var = tk.StringVar(value="direct")
    ttk.Radiobutton(stage_frame, text="Direct (m)", variable=stage_mode_var, value="direct").pack(side=tk.LEFT, padx=8)
    ttk.Radiobutton(stage_frame, text="From rating curve (Q→stage)", variable=stage_mode_var, value="rating_curve").pack(side=tk.LEFT, padx=8)

    stage_row = ttk.Frame(stage_frame)
    stage_row.pack(fill=tk.X, pady=2)
    ttk.Label(stage_row, text="Stage (m):", width=12, anchor=tk.W).pack(side=tk.LEFT)
    stage_entry = ttk.Entry(stage_row, width=10)
    stage_entry.insert(0, "2.0")
    stage_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

    rc_frame = ttk.Frame(stage_frame)
    rc_row1 = ttk.Frame(rc_frame)
    rc_row1.pack(fill=tk.X, pady=1)
    ttk.Label(rc_row1, text="Channel:", width=10, anchor=tk.W).pack(side=tk.LEFT)
    rc_channel_var = tk.StringVar(value="trapezoidal")
    ttk.Combobox(rc_row1, textvariable=rc_channel_var, values=["rectangular", "trapezoidal"], state="readonly", width=12).pack(side=tk.LEFT, padx=4)
    ttk.Label(rc_row1, text="b:", width=4, anchor=tk.W).pack(side=tk.LEFT)
    rc_b_entry = ttk.Entry(rc_row1, width=6)
    rc_b_entry.insert(0, "10")
    rc_b_entry.pack(side=tk.LEFT, padx=2)
    ttk.Label(rc_row1, text="n:", width=4, anchor=tk.W).pack(side=tk.LEFT)
    rc_n_entry = ttk.Entry(rc_row1, width=6)
    rc_n_entry.insert(0, "0.03")
    rc_n_entry.pack(side=tk.LEFT, padx=2)
    ttk.Label(rc_row1, text="s:", width=4, anchor=tk.W).pack(side=tk.LEFT)
    rc_s_entry = ttk.Entry(rc_row1, width=6)
    rc_s_entry.insert(0, "0.001")
    rc_s_entry.pack(side=tk.LEFT, padx=2)
    ttk.Label(rc_row1, text="z:", width=4, anchor=tk.W).pack(side=tk.LEFT)
    rc_z_entry = ttk.Entry(rc_row1, width=6)
    rc_z_entry.insert(0, "2")
    rc_z_entry.pack(side=tk.LEFT, padx=2)
    ttk.Label(rc_row1, text="h_max:", width=6, anchor=tk.W).pack(side=tk.LEFT)
    rc_hmax_entry = ttk.Entry(rc_row1, width=6)
    rc_hmax_entry.insert(0, "5")
    rc_hmax_entry.pack(side=tk.LEFT, padx=2)

    def _toggle_stage_mode():
        use_rc = stage_mode_var.get() == "rating_curve"
        if use_rc:
            stage_row.pack_forget()
            rc_frame.pack(fill=tk.X, pady=2)
        else:
            rc_frame.pack_forget()
            stage_row.pack(fill=tk.X, pady=2)

    stage_mode_var.trace_add("write", lambda *_: _toggle_stage_mode())
    _toggle_stage_mode()

    # SCS Type (rainfall temporal distribution)
    scs_row = ttk.Frame(input_frame)
    scs_row.pack(fill=tk.X, pady=2)
    ttk.Label(scs_row, text="SCS Type:", width=18, anchor=tk.W).pack(side=tk.LEFT)
    scs_type_var = tk.StringVar(value="type2")
    scs_combo = ttk.Combobox(
        scs_row,
        textvariable=scs_type_var,
        values=["type1", "type1a", "type2", "type3", "uniform"],
        state="readonly",
        width=12,
    )
    scs_combo.pack(side=tk.LEFT, padx=4)

    def browse_dem():
        p = filedialog.askopenfilename(filetypes=[("GeoTIFF", "*.tif *.tiff")])
        if p:
            dem_entry.delete(0, tk.END)
            dem_entry.insert(0, p)

    def browse_cn():
        p = filedialog.askopenfilename(filetypes=[("GeoTIFF", "*.tif *.tiff")])
        if p:
            cn_entry.delete(0, tk.END)
            cn_entry.insert(0, p)

    btn_row = ttk.Frame(input_frame)
    btn_row.pack(fill=tk.X, pady=4)
    ttk.Button(btn_row, text="Browse DEM", command=browse_dem).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_row, text="Browse CN", command=browse_cn).pack(side=tk.LEFT, padx=2)

    # Visibility checkboxes for map layers
    vis_frame = ttk.LabelFrame(root, text="Map layers", padding=6)
    vis_frame.pack(fill=tk.X, padx=8, pady=4)
    show_dem = tk.BooleanVar(value=True)
    show_watershed = tk.BooleanVar(value=True)
    show_stream = tk.BooleanVar(value=True)
    show_inundation = tk.BooleanVar(value=True)
    ttk.Checkbutton(vis_frame, text="DEM", variable=show_dem, command=lambda: root.after_idle(update_plots)).pack(side=tk.LEFT, padx=8)
    ttk.Checkbutton(vis_frame, text="Watershed", variable=show_watershed, command=lambda: root.after_idle(update_plots)).pack(side=tk.LEFT, padx=8)
    ttk.Checkbutton(vis_frame, text="Stream network", variable=show_stream, command=lambda: root.after_idle(update_plots)).pack(side=tk.LEFT, padx=8)
    ttk.Checkbutton(vis_frame, text="Inundation", variable=show_inundation, command=lambda: root.after_idle(update_plots)).pack(side=tk.LEFT, padx=8)

    # Progress bar (determinate: 0–100%)
    progress_frame = ttk.Frame(root)
    progress_frame.pack(fill=tk.X, padx=8, pady=2)
    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(
        progress_frame, variable=progress_var, maximum=100, mode="determinate"
    )
    progress_bar.pack(fill=tk.X)

    # Plot container
    plot_frame = ttk.Frame(root, padding=8)
    plot_frame.pack(fill=tk.BOTH, expand=True)

    # Matplotlib figure: left = layered map, right = hydrograph
    fig = Figure(figsize=(12, 5), dpi=100)
    ax_map = fig.add_subplot(1, 2, 1)
    ax_rain = fig.add_subplot(2, 2, 2)
    ax_flow = fig.add_subplot(2, 2, 4)
    fig.subplots_adjust(left=0.06, right=0.96, bottom=0.12, top=0.92, wspace=0.3, hspace=0.4)

    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    toolbar = NavigationToolbar2Tk(canvas, plot_frame)
    toolbar.update()

    status_var = tk.StringVar(value="Ready. Set paths and click Run.")

    def update_plots():
        """Update map and hydrograph from results."""
        df = df_result[0]
        flood_raster = flood_raster_result[0]
        ws = watershed_result[0]
        if df is None or ws is None:
            return

        ax_map.clear()
        ax_rain.clear()
        ax_flow.clear()
        # Remove colorbar axes from previous draw
        for ax in list(fig.axes):
            if ax not in (ax_map, ax_rain, ax_flow):
                ax.remove()

        transform = ws.transform
        rows, cols = ws.dem.shape
        extent = _get_extent_from_transform(transform, rows, cols)

        # Reserve fixed space for colorbar so map width stays constant when toggling layers
        divider = make_axes_locatable(ax_map)
        cax = divider.append_axes("right", size="5%", pad=0.1)

        # Set extent so layers align when DEM is hidden
        ax_map.set_xlim(extent[0], extent[1])
        ax_map.set_ylim(extent[2], extent[3])
        ax_map.set_aspect("auto")

        # 1. DEM (base layer)
        if show_dem.get():
            dem_display = np.where(np.isfinite(ws.dem), ws.dem, np.nan)
            ax_map.imshow(
                dem_display,
                extent=extent,
                origin="upper",
                cmap="terrain",
                aspect="auto",
            )

        # 2. Watershed boundary (contour of mask)
        if show_watershed.get():
            x = np.linspace(extent[0], extent[1], cols)
            y = np.linspace(extent[3], extent[2], rows)  # top to bottom
            mask_float = ws.mask.astype(float)
            ax_map.contour(x, y, mask_float, levels=[0.5], colors="darkgreen", linewidths=1.5)

        # 3. Stream network
        if show_stream.get():
            _plot_stream_network(ax_map, ws.stream_network, color="#1565C0", linewidth=1.2)

        # 4. Inundation overlay
        if show_inundation.get() and flood_raster is not None:
            inundation = np.where(
                np.isfinite(flood_raster) & (flood_raster > 0),
                flood_raster,
                np.nan,
            )
            if np.any(np.isfinite(inundation)):
                im = ax_map.imshow(
                    inundation,
                    extent=extent,
                    origin="upper",
                    cmap="Blues",
                    vmin=0,
                    vmax=np.nanmax(inundation),
                    alpha=0.6,
                    aspect="auto",
                )
                plt.colorbar(im, cax=cax, label="Inundation depth (m)")
                cax.set_visible(True)
        else:
            cax.set_visible(False)

        ax_map.set_title("DEM, watershed, stream network & inundation")
        ax_map.set_xlabel("X")
        ax_map.set_ylabel("Y")

        # Hydrograph
        t = np.asarray(df["time_min"])
        flow = np.asarray(df["flow_m3s"])
        rainfall = np.asarray(df["rainfall_mm"])
        excess = np.asarray(df["excess_mm"])
        timestep = int(round(t[1] - t[0])) if len(t) > 1 else 15
        width = timestep * 0.85

        ax_rain.bar(t, rainfall, width=width, color="#4A90D9", alpha=0.8, label="Rainfall (mm)")
        ax_rain.bar(t, excess, width=width * 0.7, color="#2E7D32", alpha=0.85, label="Excess (mm)")
        ax_rain.set_ylabel("Depth (mm)")
        ax_rain.legend(loc="upper right", fontsize=8)
        ax_rain.grid(True, alpha=0.3)
        ax_rain.set_title("Rainfall & Excess")

        ax_flow.plot(t, flow, color="#C62828", linewidth=2, label="Flow")
        ax_flow.fill_between(t, 0, flow, color="#C62828", alpha=0.2)
        ax_flow.set_xlabel("Time (min)")
        ax_flow.set_ylabel("Flow (m³/s)")
        ax_flow.legend(loc="upper right", fontsize=8)
        ax_flow.grid(True, alpha=0.3)
        ax_flow.set_title("Hydrograph")

        canvas.draw()
        peak = float(df["flow_m3s"].max())
        status_var.set(f"Done. Peak flow: {peak:.2f} m³/s")

    def run_pipeline():
        dem_path = dem_entry.get().strip()
        cn_path = cn_entry.get().strip()
        if not dem_path or not cn_path:
            messagebox.showerror("Error", "DEM and CN paths are required.")
            return
        if not Path(dem_path).exists():
            messagebox.showerror("Error", f"DEM not found: {dem_path}")
            return
        if not Path(cn_path).exists():
            messagebox.showerror("Error", f"CN not found: {cn_path}")
            return

        try:
            outlet_x = float(outlet_x_entry.get())
            outlet_y = float(outlet_y_entry.get())
            design_depth = float(depth_entry.get())
            duration_hr = float(duration_entry.get())
            base_flow_val = float(base_flow_entry.get() or "0")
            recession_k_str = recession_k_entry.get().strip()
            base_flow_recession_k = float(recession_k_str) if recession_k_str else None
            use_rating_curve = stage_mode_var.get() == "rating_curve"
            if use_rating_curve:
                b = float(rc_b_entry.get())
                n = float(rc_n_entry.get())
                s = float(rc_s_entry.get())
                z = float(rc_z_entry.get())
                h_max = float(rc_hmax_entry.get())
            else:
                stage_m = float(stage_entry.get())
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid number: {e}")
            return

        def on_progress(pct: float, msg: str) -> None:
            root.after(0, lambda: _update_progress(pct, msg))

        def _update_progress(pct: float, msg: str) -> None:
            progress_var.set(pct)
            status_var.set(msg)

        def do_run():
            logging.getLogger("src").setLevel(logging.WARNING)
            kwargs = dict(
                dem_path=dem_path,
                cn_path=cn_path,
                outlet_x=outlet_x,
                outlet_y=outlet_y,
                design_depth_mm=design_depth,
                duration_hr=duration_hr,
                pattern=scs_type_var.get(),
                p2_24hr_mm=50,
                timestep_min=15,
                output_path=None,
                progress_callback=on_progress,
                base_flow_m3s=base_flow_val if base_flow_val > 0 else None,
                base_flow_recession_k_min=base_flow_recession_k if base_flow_val > 0 else None,
            )
            if use_rating_curve:
                if rc_channel_var.get() == "rectangular":
                    rating_curve = rating_curve_rectangular(b=b, n=n, s=s, h_max=h_max)
                else:
                    rating_curve = rating_curve_trapezoidal(b=b, z=z, n=n, s=s, h_max=h_max)
                kwargs["rating_curve"] = rating_curve
            else:
                kwargs["stage_m"] = stage_m
            return compute_design_flood_map(**kwargs)

        def run_in_thread():
            progress_var.set(0)
            status_var.set("Starting...")
            try:
                df, flood_raster, ws = do_run()
                df_result[0] = df
                flood_raster_result[0] = flood_raster
                watershed_result[0] = ws
                root.after(0, lambda: _finish_run(None))
            except Exception as e:
                root.after(0, lambda: _finish_run(e))

        def _finish_run(err):
            progress_var.set(100 if not err else 0)
            if err:
                status_var.set("Error")
                messagebox.showerror("Error", str(err))
                logger.exception("Pipeline failed")
                return
            status_var.set("Updating plots...")
            root.update()
            update_plots()

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

    ttk.Button(input_frame, text="Run", command=run_pipeline).pack(side=tk.LEFT, padx=4)
    ttk.Label(input_frame, textvariable=status_var, foreground="gray").pack(side=tk.LEFT, padx=8)

    # Bring to front again after all widgets are packed (helps when launched from IDE)
    root.update_idletasks()
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.after(100, lambda: root.attributes("-topmost", False))
    root.focus_force()

    root.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_gui()
