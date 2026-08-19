# SPDX-License-Identifier: Apache-2.0
"""Render the truth-bound CeliumNeUR v1 technical poster.

All plots and the architecture panel are generated artifacts. The script
refuses to run if any required evidence image is absent.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "render" / "architecture_block.png"
RASTER = ROOT / "golden" / "demo_raster_compare.png"
LEARNING = ROOT / "render" / "plasticity_trajectory.png"
OUTPUTS = (
    ROOT / "render" / "poster_celiumneur_soc_v2.png",
    ROOT / "render" / "poster_celiumneur_soc.png",
)

BG = "#07131f"
PANEL = "#0d2233"
INK = "#e8f1f5"
MUTED = "#91a9b7"
CYAN = "#41d6c3"
BLUE = "#4aa8ff"
ORANGE = "#ff9f5a"
MAGENTA = "#dc7cff"
RED = "#ff6577"
GRID = "#244457"


def panel(fig, rect, title, subtitle=""):
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch(
        (0.5, 0.5), 99, 99,
        boxstyle="round,pad=0.0,rounding_size=1.6",
        facecolor=PANEL, edgecolor=GRID, linewidth=1.4,
    ))
    ax.text(3, 94, title, color=CYAN, fontsize=13, fontweight="bold",
            ha="left", va="center")
    if subtitle:
        ax.text(97, 94, subtitle, color=MUTED, fontsize=7.5,
                ha="right", va="center")
    return ax


def place_image(fig, rect, path, *, edge=GRID):
    ax = fig.add_axes(rect)
    ax.imshow(mpimg.imread(path))
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(edge)
        spine.set_linewidth(1.0)
    return ax


def draw_protocol(ax):
    fields = (
        ("type\n[31:28]", 4, MAGENTA),
        ("reserved=0\n[27:24]", 4, "#526777"),
        ("destination mask\n[23:20]", 4, ORANGE),
        ("type-specific body\n[19:0]", 20, BLUE),
    )
    x = 4
    scale = 92 / 32
    for label, bits, color in fields:
        width = bits * scale
        ax.add_patch(Rectangle((x, 60), width, 18, facecolor=color,
                               edgecolor=BG, linewidth=1.0))
        ax.text(x + width / 2, 69, label,
                color=BG if color in (ORANGE, BLUE) else INK,
                fontsize=7.2, fontweight="bold", ha="center", va="center")
        x += width

    ax.text(4, 47, "SPIKE", color=CYAN, fontsize=9, fontweight="bold")
    ax.text(17, 47, "parity[19] • zero[18:10] • source_gid[9:0]",
            color=MUTED, fontsize=8)
    ax.text(4, 34, "CONFIG", color=MAGENTA, fontsize=9, fontweight="bold")
    ax.text(17, 34, "ordered header + 4 × 16-bit fragments",
            color=MUTED, fontsize=8)
    ax.text(4, 21, "spaces", color=ORANGE, fontsize=9, fontweight="bold")
    ax.text(17, 21, "0 dendrite • 1 soma • 2 axon • 3 invalid",
            color=MUTED, fontsize=8)
    ax.text(4, 8,
            "Malformed or out-of-order traffic sets a sticky witness and never commits.",
            color=RED, fontsize=7.6)


def draw_verification(ax):
    rows = (
        ("GOLDEN", "55 / 55", "pytest + published learning demo"),
        ("RTL", "32 / 32", "9 cocotb groups, including default SoC"),
        ("RAW", "8 / 8", "self-checking Icarus/vvp probes"),
        ("MUTANTS", "17 / 17", "targeted faults killed"),
        ("FORMAL", "BMC 60", "FIFO + corner router safety"),
        ("LINT", "0 warnings", "Verilator -Wall, default 4×256 SoC"),
    )
    for index, (gate, result, detail) in enumerate(rows):
        y = 80 - index * 12.5
        ax.text(4, y, gate, color=MUTED, fontsize=8, fontweight="bold",
                ha="left", va="center")
        ax.text(35, y, result, color=CYAN, fontsize=10, fontweight="bold",
                ha="left", va="center")
        ax.text(58, y, detail, color=INK, fontsize=7.2,
                ha="left", va="center")
        if index < len(rows) - 1:
            ax.plot([4, 96], [y - 6.3, y - 6.3], color=GRID, linewidth=0.7)

    ax.text(4, 5,
            "Bounded, contract-scoped evidence — not timing closure, PnR or silicon.",
            color=ORANGE, fontsize=7.4, fontweight="bold")


def main():
    missing = [path for path in (ARCH, RASTER, LEARNING) if not path.is_file()]
    if missing:
        raise SystemExit("missing generated evidence: " + ", ".join(map(str, missing)))

    plt.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "font.family": "DejaVu Sans",
        "text.color": INK,
    })
    fig = plt.figure(figsize=(16.5, 20.5), facecolor=BG)

    fig.text(0.055, 0.972, "CELIUMNEUR v1", color=INK, fontsize=34,
             fontweight="bold", ha="left", va="center")
    fig.text(0.055, 0.948,
             "TRANSPARENT, BACKPRESSURED, LEARNING NEUROMORPHIC RTL",
             color=CYAN, fontsize=13, fontweight="bold", ha="left")
    fig.text(0.945, 0.971, "4 TILES × 256 NEURONS  /  GID 0–1023",
             color=BLUE, fontsize=11, fontweight="bold", ha="right")
    fig.text(0.945, 0.949, "SYNTHESIZABLE RTL • NOT PnR / NOT SILICON",
             color=ORANGE, fontsize=9, ha="right")

    panel(fig, (0.045, 0.555, 0.91, 0.365),
          "A — Default SoC architecture",
          "one diagram, one implemented contract")
    place_image(fig, (0.065, 0.575, 0.87, 0.315), ARCH)

    protocol = panel(fig, (0.045, 0.375, 0.445, 0.16),
                     "B — Routed protocol")
    draw_protocol(protocol)
    verification = panel(fig, (0.51, 0.375, 0.445, 0.16),
                         "C — Verification gates")
    draw_verification(verification)

    panel(fig, (0.045, 0.175, 0.445, 0.18), "D — Golden / RTL raster",
          "same firing multiset; bounded phase latency")
    place_image(fig, (0.065, 0.19, 0.405, 0.14), RASTER)

    panel(fig, (0.51, 0.175, 0.445, 0.18), "E — CWR executable trajectory",
          "paired 120→127 • control 120→90")
    place_image(fig, (0.53, 0.19, 0.405, 0.14), LEARNING)

    synthesis = panel(fig, (0.045, 0.055, 0.91, 0.10),
                      "F — Reproducible synthesis snapshot",
                      "Yosys 0.68+50 • GF180 MCU 7t5v0 TT/25°C/5V")
    columns = (
        (4, "CONFIG ENDPOINT", "271 cells", "10,025.48 µm² mapped"),
        (36, "HYPHA ROUTER", "2,535 cells", "91,076.65 µm² mapped"),
        (68, "DEFAULT SOC", "55,130 cells", "coarse lowering; memories retained"),
    )
    for x, name, value, note in columns:
        synthesis.text(x, 61, name, color=MUTED, fontsize=8,
                       fontweight="bold", ha="left")
        synthesis.text(x, 39, value, color=CYAN, fontsize=13,
                       fontweight="bold", ha="left")
        synthesis.text(x, 21, note, color=INK, fontsize=7.5, ha="left")
    synthesis.text(4, 6,
                   "Receipts bind base commit, working diff, source manifest, toolchain and SHA-256 outputs.",
                   color=ORANGE, fontsize=7.4, ha="left")

    fig.text(0.5, 0.025,
             "Celiums Solutions LLC  •  Apache-2.0  •  DOI 10.5281/zenodo.21925426",
             color=MUTED, fontsize=8.5, ha="center")

    for output in OUTPUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=130, facecolor=BG)
        print(f"wrote {output}")
    plt.close(fig)


if __name__ == "__main__":
    main()
