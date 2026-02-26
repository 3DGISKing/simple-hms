"""Plot flow, rainfall, and excess over time."""

from pathlib import Path
from typing import Optional, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_hydrograph(
    df: pd.DataFrame,
    output_path: Optional[Union[str, Path]] = None,
    timestep_min: Optional[int] = None,
    figsize: tuple = (10, 6),
    dpi: int = 100,
) -> plt.Figure:
    """
    Plot flow, rainfall, and excess rainfall over time.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: time_min, flow_m3s, rainfall_mm, excess_mm
        (e.g. from compute_design_hydrograph).
    output_path : str or Path, optional
        Path to save figure. If None, figure is not saved.
    timestep_min : int, optional
        Timestep (minutes) for bar width. If None, inferred from time_min diff.
    figsize : tuple
        Figure size (width, height) in inches.
    dpi : int
        Resolution for saved figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    required = ["time_min", "flow_m3s", "rainfall_mm", "excess_mm"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"DataFrame must have column '{col}'")

    t = np.asarray(df["time_min"])
    flow = np.asarray(df["flow_m3s"])
    rainfall = np.asarray(df["rainfall_mm"])
    excess = np.asarray(df["excess_mm"])

    if timestep_min is None and len(t) > 1:
        timestep_min = int(round(t[1] - t[0]))
    if timestep_min is None:
        timestep_min = 15

    fig, axes = plt.subplots(2, 1, figsize=figsize, sharex=True, height_ratios=[1, 1.2])
    ax_rain, ax_flow = axes

    # Bar width: slightly less than timestep for clarity
    width = timestep_min * 0.85

    # Top: rainfall and excess (bars)
    ax_rain.bar(t, rainfall, width=width, color="#4A90D9", alpha=0.8, label="Rainfall (mm)")
    ax_rain.bar(t, excess, width=width * 0.7, color="#2E7D32", alpha=0.85, label="Excess (mm)")

    ax_rain.set_ylabel("Depth (mm)")
    ax_rain.legend(loc="upper right", fontsize=9)
    ax_rain.grid(True, alpha=0.3)
    ax_rain.set_title("Rainfall & Excess Rainfall")

    # Bottom: flow (line)
    ax_flow.plot(t, flow, color="#C62828", linewidth=2, label="Flow")
    ax_flow.fill_between(t, 0, flow, color="#C62828", alpha=0.2)

    ax_flow.set_xlabel("Time (min)")
    ax_flow.set_ylabel("Flow (m³/s)")
    ax_flow.legend(loc="upper right", fontsize=9)
    ax_flow.grid(True, alpha=0.3)
    ax_flow.set_title("Hydrograph")

    plt.tight_layout()

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")

    return fig
