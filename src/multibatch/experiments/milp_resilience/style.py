"""Shared publication style for the resilience-study figures. One source of truth for
rcParams, the colourblind-safe (Okabe-Ito) palette, and PNG+PDF saving so every plot
module (plots, plots_cost, plots_levers) renders consistently.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = Path(__file__).resolve().parent / "results"
FIG = RES / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def apply():
    """Apply the shared rcParams. Call once at module import."""
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
        "font.size": 10, "font.family": "serif", "mathtext.fontset": "cm",
        "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.fontsize": 8.5,
        "axes.titlesize": 10.5, "axes.labelsize": 10,
    })


# packing configuration (Okabe-Ito)
CFG_COLOR = {"baseline": "#999999", "hetero_w8": "#009E73",
             "conc_w8": "#0072B2", "full_w8_8": "#D55E00"}
CFG_LABEL = {"baseline": "baseline", "hetero_w8": "hetero",
             "conc_w8": "conc", "full_w8_8": "full"}
CFG_ORDER = ["baseline", "hetero_w8", "conc_w8", "full_w8_8"]

# flow solvers
SOLVER_COLOR = {"milp": "#0072B2", "asp": "#E69F00"}

# generic accent sequence (Okabe-Ito) for ad-hoc series
ACCENT = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442"]


def short(name):
    """Compact instance label."""
    return ("industry" if name.startswith("industry")
            else name.replace("layered_", "").replace("_seed", " s"))


def inst_order(insts):
    """Industry first, then layered alphabetically."""
    return sorted(insts, key=lambda s: (not s.startswith("industry"), s))


def save(fig, stem):
    """Write both a PNG (slides) and a vector PDF (paper)."""
    fig.savefig(FIG / f"{stem}.png")
    fig.savefig(FIG / f"{stem}.pdf")
    plt.close(fig)
