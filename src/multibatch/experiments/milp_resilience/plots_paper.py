"""Rebuild revised SACAIR Figures 2 and 3 without changing experimental data.

From the repository root: make paper-figures

Alternatively:
    PYTHONPATH=src .venv/bin/python -m multibatch.experiments.milp_resilience.plots_paper
No source manuscript, original figure, or result file is overwritten.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, MultipleLocator, FormatStrFormatter

RESULTS = Path(__file__).resolve().parent / "results"
SOURCE = RESULTS / "suite_consolidated.csv"
DEFAULT_OUTPUT = RESULTS / "figures/sacair2026"
CONFIGS = ["baseline", "hetero_w8", "conc_w8", "full_w8_8"]
LABELS = ["baseline", "hetero_pack", "equal_distr", "combined"]
COLORS = ["#333333", "#00845F", "#0072B2", "#D55E00"]
MARKERS = ["o", "s", "D", "^"]
STYLES = ["-", (0, (4, 3)), (0, (1.2, 2)), (0, (5, 2, 1, 2))]

# Independent checkpoints from the original plotted data, in CONFIGS order.
# These validate saved-result aggregation, not reproduction of solver runs.
EXPECTED = {
    "medium": {
        0: {"cost": [4097.4, 4105.4, 4542.4, 4394.8],
            "single": [.93116, .93314, .92782, .93120],
            "global": [.56002, .58890, .53556, .55110]},
        4: {"cost": [4521.6, 4521.6, 4866.0, 4887.2],
            "single": [.93614, .93732, .93786, .93796],
            "global": [.48890, .50222, .49556, .49112]},
    },
    "industry": {
        0: {"cost": [2767853, 2769429, 2830857, 3104737],
            "single": [.95700, .95690, .95760, .95750],
            "global": [.01330, .00930, .02450, .02190]},
        4: {"cost": [4141569, 4141569, 4653305, 4419889],
            "single": [.98090, .98100, .98080, .98080],
            "global": [.02720, .03510, .02060, .02390]},
    },
}

PLOT_STYLE = {
    "font.family": "DejaVu Serif", "mathtext.fontset": "dejavuserif",
    "font.size": 9.5, "axes.labelsize": 9.5, "axes.titlesize": 10,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9,
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .7, "savefig.facecolor": "white",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@plt.rc_context(PLOT_STYLE)
def build_figures(output_dir=DEFAULT_OUTPUT):
    """Plot the audited paper results, returning their data/provenance manifest."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    original_hash = file_hash(SOURCE)
    with SOURCE.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    manifest = {"source": "src/multibatch/experiments/milp_resilience/results/suite_consolidated.csv",
                "source_sha256": original_hash,
                "flow_solver": "milp", "lambda_flow": 0,
                "aggregation": "Arithmetic mean per config and lambda_net; cost increase is ratio of means, not mean of individual percentages.",
                "y_formula": "100 * (mean(s2_dispatch_cost) - reference_cost) / reference_cost",
                "x_formula": "100 * mean(nri_alpha_SCOPE_ALPHA)",
                "endpoint_labels": "lambda_net=0 at lower-cost endpoint; lambda_net=4 at higher-cost endpoint",
                "figures": []}
    for number, size, alpha, sample_count in [(2, "medium", .8, 5), (3, "industry", .2, 1)]:
        relevant = [r for r in rows if r["flow_solver"] == "milp"
                    and float(r["lambda_flow"]) == 0
                    and float(r["lambda_net"]) in (0, 4)
                    and (r["instance"].startswith("layered_medium_") if size == "medium"
                         else r["instance"] == "industry_test_1")]
        require(len(relevant) == sample_count * 8, f"{size}: unexpected row count")
        require(len({r["instance"] for r in relevant}) == sample_count,
                f"{size}: unexpected instance count")
        ref = statistics.mean(float(r["s2_dispatch_cost"]) for r in relevant
                              if r["config"] == "baseline" and float(r["lambda_net"]) == 0)
        figdata = {"figure": number, "size": size, "alpha": alpha,
                   "instances": sorted({r["instance"] for r in relevant}),
                   "reference_cost": ref, "points": []}
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.2), sharey=True)
        fig.subplots_adjust(left=.105, right=.98, bottom=.31, top=.78, wspace=.18)
        instance_label = "Medium instances" if size == "medium" else "Industrial instance"
        fig.suptitle(f"Cost versus partial-loss resilience: {instance_label}",
                     x=.54, y=.985, fontsize=12, fontweight="bold")
        for panel, scope, ax in zip("ab", ["single", "global"], axes):
            for i, cfg in enumerate(CONFIGS):
                x, y = [], []
                for weight in [0, 4]:
                    selected = [r for r in relevant if r["config"] == cfg
                                and float(r["lambda_net"]) == weight]
                    require(len(selected) == sample_count, f"{size}/{cfg}/{weight}: missing or extra rows")
                    require({r["instance"] for r in selected} == set(figdata["instances"]),
                            f"{size}/{cfg}/{weight}: mismatched or duplicate instances")
                    metric = statistics.mean(float(r[f"nri_alpha_{scope}_{alpha}"]) for r in selected)
                    cost = statistics.mean(float(r["s2_dispatch_cost"]) for r in selected)
                    require(math.isclose(metric, EXPECTED[size][weight][scope][i], rel_tol=0, abs_tol=1e-12),
                            f"{size}/{cfg}/{weight}/{scope}: resilience differs from audited paper data")
                    require(math.isclose(cost, EXPECTED[size][weight]["cost"][i], rel_tol=0, abs_tol=1e-9),
                            f"{size}/{cfg}/{weight}: cost differs from audited paper data")
                    x.append(metric * 100)
                    y.append((cost - ref) / ref * 100)
                    figdata["points"].append({"scope": scope, "config": cfg,
                        "display_label": LABELS[i], "lambda_net": weight,
                        "n_instances": len(selected), "mean_resilience": metric,
                        "mean_dispatch_cost": cost, "x_percent": x[-1],
                        "y_cost_increase_percent": y[-1]})
                require(y[1] > y[0], "Endpoint key assumes increasing cost.")
                # Draw the baseline as a wider solid line under the dashed green line.
                # Hollow baseline circles are drawn above all series, so both symbols
                # remain visible for almost-coincident results. No point is jittered.
                line, = ax.plot(x, y, color=COLORS[i], linestyle=STYLES[i],
                               linewidth=2 if i == 0 else 1.35, zorder=2 + i)
                points, = ax.plot(x, y, linestyle="none", color=COLORS[i], marker=MARKERS[i],
                                 markersize=9 if i == 0 else 4.7,
                                 markerfacecolor="none" if i == 0 else COLORS[i],
                                 markeredgewidth=1.2 if i == 0 else .8,
                                 zorder=10 if i == 0 else 6 + i)
                require(list(line.get_xdata()) == x == list(points.get_xdata()), "Plotted x values changed")
                require(list(line.get_ydata()) == y == list(points.get_ydata()), "Plotted y values changed")
            title = "Single-route" if scope == "single" else "Global"
            ax.set_title(f"({panel}) {title}\npartial loss ($\\alpha={alpha}$)", loc="left", pad=7)
            ax.set_xlabel(r"$\mathrm{NRI}_{\alpha}$ (%)", labelpad=4)
            if scope == "single":
                ax.set_ylabel("Dispatch-cost increase\nvs baseline (%)", labelpad=7)
            ax.grid(axis="both", color="#DEDEDE", linewidth=.5, linestyle=":", zorder=0)
            ax.set_axisbelow(True)
            ax.axhline(0, color="#A0A0A0", linewidth=.55, zorder=1)
            ax.tick_params(length=3, width=.6)
            if size == "medium":
                ax.set_ylim(-2, 23)
                ax.yaxis.set_major_locator(MultipleLocator(5))
                ax.set_xlim((92.65, 94.0) if scope == "single" else (47.4, 60.1))
                ax.xaxis.set_major_locator(FixedLocator([92.7, 93.3, 93.9] if scope == "single" else [48, 54, 60]))
                ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f" if scope == "single" else "%.0f"))
            else:
                ax.set_ylim(-6, 76)
                ax.yaxis.set_major_locator(MultipleLocator(20))
                ax.set_xlim((95.45, 98.36) if scope == "single" else (.65, 3.8))
                ax.xaxis.set_major_locator(FixedLocator([96, 97, 98] if scope == "single" else [1, 2, 3]))
                ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
        handles = [Line2D([], [], color=COLORS[i], marker=MARKERS[i], linestyle=STYLES[i],
                          linewidth=2 if i == 0 else 1.35, markersize=8 if i == 0 else 4.7,
                          markerfacecolor="none" if i == 0 else COLORS[i],
                          markeredgewidth=1.2 if i == 0 else .8,
                          label=LABELS[i]) for i in range(4)]
        fig.legend(handles=handles, loc="lower right", bbox_to_anchor=(.98, .025),
                   ncol=2, frameon=False, handlelength=2.8, columnspacing=2,
                   handletextpad=.7, labelspacing=.65)
        fig.text(.105, .067,
                 "Lower endpoints: $\\lambda_{\\mathrm{net}}=0$\n"
                 "Upper endpoints: $\\lambda_{\\mathrm{net}}=4$",
                 ha="left", va="center", fontsize=8.5, linespacing=1.7)
        stem = f"figure_{number}_{size}_revised"
        fig.savefig(output_dir / f"{stem}.pdf", metadata={"Title": f"Figure {number}: {size} partial-loss resilience",
                    "Subject": f"MILP; alpha={alpha}; lambda_flow=0; unmodified saved-result values"})
        fig.savefig(output_dir / f"{stem}.png", dpi=600)
        plt.close(fig)
        manifest["figures"].append(figdata)
    require(file_hash(SOURCE) == original_hash, "Source CSV changed during the build")
    require(sum(len(f["points"]) for f in manifest["figures"]) == 32, "Expected 32 plotted points")
    (output_dir / "figure_data_audit.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Validated all 32 plotted points; source hash unchanged.")
    print("Created two vector PDFs and two 600-dpi PNGs in", output_dir)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="Destination for both PDF/PNG figures and the JSON data audit")
    args = parser.parse_args()
    try:
        build_figures(args.output_dir)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Paper figure build failed: {exc}\n")


if __name__ == "__main__":
    main()
