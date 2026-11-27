"""Plot the eight per-date IC-gap means with +/- 2 x SE_NW(5) error bars.

Reads <dir>/<factor>_series.json for the four fundamental factors and writes
one PNG. Statistics come from check_vintage_series.gap_stats, so the plot and
the check outputs share one computation. Needs matplotlib.

    python -I scripts/research_note/plot_ic_gaps.py
        examples/outputs/research_note_20261125 docs/research_note_ic_gaps.png
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from check_vintage_series import MAIN_LAG, T_LAYERS, gap_stats  # noqa: E402

FACTORS = ("bm_ratio", "ep_ratio", "roe", "asset_growth")
STYLE = {  # reference palette slots 1-2, light surface; marker shape as second cue
    "original-process": ("#2a78d6", "o"),
    "common-observation": ("#eb6834", "s"),
}
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []  # (y, factor, layer, stats), top to bottom
    y = 0.0
    for f in FACTORS:
        series = json.load(open(src / f"{f}_series.json", encoding="utf-8"))["series"]
        for layer in T_LAYERS:
            rows.append((y, f, layer, gap_stats(series, layer)))
            y -= 1
        y -= 0.8

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axvline(0, color=MUTED, lw=1, zorder=1)
    for layer, (color, marker) in STYLE.items():
        pts = [(yy, s) for yy, _, lay, s in rows if lay == layer]
        ax.errorbar([s["mean"] for _, s in pts], [yy for yy, _ in pts],
                    xerr=[2 * s["se_nw"] for _, s in pts], fmt=marker, ms=6,
                    color=color, ecolor=color, elinewidth=2, capsize=3,
                    label=layer, zorder=3)
    ax.set_yticks([yy for yy, *_ in rows])
    ax.set_yticklabels([f"{f}  {'OP' if lay == 'original-process' else 'CO'}"
                        for _, f, lay, _ in rows], color=INK, fontsize=9)
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e4e3df", lw=0.6, zorder=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.set_xlabel(f"mean of d_t = restated IC − PIT IC (183 dates); "
                  f"bars ±2 × SE_NW({MAIN_LAG})", color=INK, fontsize=9)
    ax.set_title("Per-date IC gap by factor and layer", color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE, metadata={"Software": None})
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
