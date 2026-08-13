# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the CeliumNeUR SoC v1 technical poster (dark technical-diagram style).

Usage:  .venv/Scripts/python.exe tools/render_poster.py
Output: render/poster_celiumneur_soc.png  (16x20 in @ 200 dpi)

Every number/label is sourced from SPEC.md and rtl/ — nothing invented.
Layout is hand-placed in figure-fraction coordinates; each panel owns a
normalized 0..100 local space so text can never leak across panels.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "golden" / "demo_raster_compare.png"
OUT = ROOT / "render" / "poster_celiumneur_soc.png"

BG = "#0b1020"      # poster background
PANEL = "#0e1628"   # panel fill
DIE = "#0d1424"     # die fill
EDGE = "#2b3d63"    # structural borders
CYAN = "#35d6ea"
CYAN_FILL = "#10303f"
SALMON = "#ff8f6b"
SALMON_FILL = "#37231a"
TEXT = "#dce7f7"
MUTED = "#93a7c4"
MONO = "DejaVu Sans Mono"

FIG_W, FIG_H, DPI = 16.0, 20.0, 200


def make_panel(fig, rect):
    """Add a bordered panel axes with a normalized 0..100 local space."""
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.8, 0.8), 98.4, 98.4,
            boxstyle="round,pad=0,rounding_size=1.2",
            edgecolor=EDGE, facecolor=PANEL, linewidth=1.4, zorder=0,
        )
    )
    return ax


def panel_title(ax, s, size=15):
    ax.text(3.0, 94.5, s, fontsize=size, fontweight="bold", color=CYAN,
            ha="left", va="center", zorder=6)


def rbox(ax, x, y, w, h, ec, fc, lw=1.3, r=1.0, z=2):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            edgecolor=ec, facecolor=fc, linewidth=lw, zorder=z,
        )
    )


def link(ax, p0, p1, color=CYAN, lw=1.3, ms=13, z=4):
    ax.add_patch(
        FancyArrowPatch(
            p0, p1, arrowstyle="<->", mutation_scale=ms,
            linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=z,
        )
    )


def draw_header(fig):
    fig.text(0.5, 0.9665, "CELIUMNEUR — the chip that has no secrets",
             fontsize=38, fontweight="bold", color=CYAN,
             ha="center", va="center")
    fig.text(0.5, 0.9425,
             "Transparent (I5)  ·  Cannot drop a spike (I1)  ·  "
             "Learns without stopping (I4)",
             fontsize=16.5, color=TEXT, ha="center", va="center")
    fig.text(0.982, 0.9890, "CeliumNeUR SoC v1", fontsize=10,
             fontfamily=MONO, color=MUTED, ha="right", va="center")
    fig.add_artist(Line2D([0.06, 0.94], [0.9290, 0.9290],
                          color=SALMON, linewidth=1.3, alpha=0.75,
                          transform=fig.transFigure))


def draw_panel_a(ax):
    panel_title(ax, "A — SoC Map")

    # Die boundary ---------------------------------------------------------
    rbox(ax, 2.5, 3.0, 95.0, 86.5, ec=EDGE, fc=DIE, lw=1.6, r=1.8, z=1)
    ax.text(5.5, 86.0, "celiumneur_soc", fontsize=11.5, fontweight="bold",
            color=SALMON, ha="left", va="center", zorder=6)
    ax.text(50, 5.0, "rtl/top/celiumneur_soc.v", fontsize=9,
            fontfamily=MONO, color=MUTED, ha="center", va="center", zorder=6)

    # Neuro tiles (t0..t3) --------------------------------------------------
    tiles = [(6, 52, "t0"), (68, 52, "t1"), (6, 12, "t2"), (68, 12, "t3")]
    for x, y, name in tiles:
        rbox(ax, x, y, 26, 30, ec="#5f7bb0", fc="#101a30", lw=1.4, r=1.2, z=2)
        ax.text(x + 13, y + 27, f"neuro_tile {name}", fontsize=9.5,
                fontweight="bold", color=TEXT, ha="center", va="center", zorder=6)
        # SomaCore
        rbox(ax, x + 2, y + 16.5, 22, 8, ec=CYAN, fc=CYAN_FILL, r=0.8, z=3)
        ax.text(x + 13, y + 22.6, "SomaCore", fontsize=9, fontweight="bold",
                color=CYAN, ha="center", va="center", zorder=6)
        ax.text(x + 13, y + 19.2, "4 neurons", fontsize=8, color=MUTED,
                ha="center", va="center", zorder=6)
        # Dendrite
        rbox(ax, x + 2, y + 8.2, 22, 8, ec=SALMON, fc=SALMON_FILL, r=0.8, z=3)
        ax.text(x + 13, y + 14.3, "Dendrite", fontsize=9, fontweight="bold",
                color=SALMON, ha="center", va="center", zorder=6)
        ax.text(x + 13, y + 10.9, "16 entries", fontsize=8, color=MUTED,
                ha="center", va="center", zorder=6)
        # Snooper
        rbox(ax, x + 2, y + 1.2, 22, 6.2, ec="#6f86b8", fc="#16203a", r=0.8, z=3)
        ax.text(x + 13, y + 4.3, "Snooper", fontsize=8.5, color=TEXT,
                ha="center", va="center", zorder=6)
        # Real RTL file names under each block
        ax.text(x + 13, y - 2.0, "rtl/soma/soma_core.v", fontsize=7.5,
                fontfamily=MONO, color=MUTED, ha="center", va="center", zorder=6)
        ax.text(x + 13, y - 3.9, "rtl/soma/soma_dendrite.v", fontsize=7.5,
                fontfamily=MONO, color=MUTED, ha="center", va="center", zorder=6)

    # Hyphae 2x2 mesh -------------------------------------------------------
    rbox(ax, 38, 35, 24, 32, ec=CYAN, fc="#0e2433", lw=1.6, r=1.4, z=2)
    ax.text(50, 63.0, "Hyphae 2×2 mesh", fontsize=11, fontweight="bold",
            color=CYAN, ha="center", va="center", zorder=6)
    ax.text(50, 31.8, "rtl/hyphae/hypha_router.v", fontsize=9,
            fontfamily=MONO, color=MUTED, ha="center", va="center", zorder=6)

    routers = [(40, 48.75, "r00"), (52, 48.75, "r01"),
               (40, 36.25, "r10"), (52, 36.25, "r11")]
    for x, y, name in routers:
        rbox(ax, x, y, 8, 6.5, ec="#7ee7f4", fc="#12303f", lw=1.1, r=0.7, z=3)
        ax.text(x + 4, y + 3.25, name, fontsize=8.5, fontfamily=MONO,
                color=TEXT, ha="center", va="center", zorder=6)

    # Inter-router links (horizontal + vertical, X-first mesh)
    link(ax, (48, 52.0), (52, 52.0), lw=1.2, ms=11)
    link(ax, (48, 39.5), (52, 39.5), lw=1.2, ms=11)
    link(ax, (44, 48.75), (44, 42.75), lw=1.2, ms=11)
    link(ax, (56, 48.75), (56, 42.75), lw=1.2, ms=11)

    # Tile <-> mesh injection links (to the mesh border, at router height)
    link(ax, (32, 52.5), (38, 52.0), lw=1.4, ms=13)
    link(ax, (68, 52.5), (62, 52.0), lw=1.4, ms=13)
    link(ax, (32, 40.0), (38, 39.5), lw=1.4, ms=13)
    link(ax, (68, 40.0), (62, 39.5), lw=1.4, ms=13)


def draw_panel_b(ax):
    panel_title(ax, "B — 32-bit packet anatomy")

    x0, y_top, y_bot = 3.0, 68.0, 42.0
    scale = 94.0 / 32.0

    fields = [
        # hi, lo, range label, description lines, side, fill, edge, desc color
        (31, 28, "[31:28]", ["type = SPIKE"], "up", "#123a4d", CYAN, CYAN),
        (27, 24, "[27:24]", ["reserved"], "down", "#141c33", "#4a5b85", MUTED),
        (23, 20, "[23:20]", ["dst mask · 4 cores"], "up", "#3a2318", SALMON, SALMON),
        (19, 19, "[19]", ["phase parity", "(source-tick parity)"], "down",
         SALMON, SALMON, SALMON),
        (18, 10, "[18:10]", ["zero"], "up", "#0f1526", "#3a4a6e", MUTED),
        (9, 0, "[9:0]", ["neuron gid"], "down", "#123a4d", CYAN, CYAN),
    ]

    for hi, lo, rng, lines, side, fc, ec, dc in fields:
        w = (hi - lo + 1) * scale
        x_l = x0 + (31 - hi) * scale
        cx = x_l + w / 2
        ax.add_patch(Rectangle((x_l, y_bot), w, y_top - y_bot,
                               facecolor=fc, edgecolor=ec, linewidth=1.3,
                               zorder=3))
        narrow = (hi - lo + 1) == 1
        ax.text(cx, (y_top + y_bot) / 2, rng, fontsize=9 if not narrow else 8,
                fontfamily=MONO, fontweight="bold",
                color="#20100a" if fc == SALMON else TEXT,
                ha="center", va="center",
                rotation=90 if narrow else 0, zorder=6)
        if side == "up":
            anchor_x, ha = (cx + 0.6, "left") if hi == 31 else (cx, "center")
            lx = anchor_x
            ax.plot([cx, cx], [y_top, y_top + 4.5], color=dc, lw=0.9,
                    alpha=0.7, zorder=4)
            ax.text(lx, y_top + 7.5, lines[0], fontsize=9.5, color=dc,
                    ha=ha, va="center", zorder=6)
        else:
            ax.plot([cx, cx], [y_bot, y_bot - 2.8], color=dc, lw=0.9,
                    alpha=0.7, zorder=4)
            for k, s in enumerate(lines):
                ax.text(cx, y_bot - 7.2 - 6.5 * k, s, fontsize=9.5, color=dc,
                        ha="center", va="center", zorder=6)

    ax.text(1.8, y_top + 3.0, "31", fontsize=8, fontfamily=MONO, color=MUTED,
            ha="left", va="center", zorder=6)
    ax.text(98.2, y_top + 3.0, "0", fontsize=8, fontfamily=MONO, color=MUTED,
            ha="right", va="center", zorder=6)


def draw_panel_c(ax, panel_w_in, panel_h_in):
    panel_title(ax, "C — Raster demo")
    ax.text(3.0, 88.0, "Golden sandbox vs RTL chip — identical modulo "
            "phase tag", fontsize=10.5, color=SALMON, style="italic",
            ha="left", va="center", zorder=6)

    img = mpimg.imread(GOLDEN)
    hp, wp = img.shape[0], img.shape[1]
    avail_x, avail_y = 94.0, 80.0                       # local units
    avail_w_in = avail_x / 100.0 * panel_w_in
    img_h_in = avail_w_in * hp / wp
    h_local = img_h_in / panel_h_in * 100.0
    if h_local > avail_y:                               # extremely tall image
        h_local = avail_y
    y0 = 4.0 + (avail_y - h_local) / 2.0 + 6.0
    x0 = 3.0
    ax.imshow(img, extent=[x0, x0 + avail_x, y0, y0 + h_local],
              aspect="auto", zorder=3)
    ax.add_patch(Rectangle((x0, y0), avail_x, h_local, fill=False,
                           edgecolor="#3a4a6e", linewidth=1.2, zorder=4))


def draw_panel_d(ax):
    panel_title(ax, "D — Hard data · GF180 baseline (pre-PnR)", size=13)

    ax.text(4, 82, "Block", fontsize=10.5, fontfamily=MONO, fontweight="bold",
            color=MUTED, ha="left", va="center", zorder=6)
    ax.text(96, 82, "Area", fontsize=10.5, fontfamily=MONO, fontweight="bold",
            color=MUTED, ha="right", va="center", zorder=6)
    ax.plot([4, 96], [78.5, 78.5], color=EDGE, lw=1.0, zorder=4)

    rows = [
        ("soma_core", "~64.7k µm²"),
        ("hypha_router (hierarchical)", "~91k µm²"),
        ("2×2 mesh (4 routers)", "~364k µm²"),
    ]
    for i, (name, area) in enumerate(rows):
        y = 72 - 9 * i
        ax.text(4, y, name, fontsize=10.5, fontfamily=MONO, color=TEXT,
                ha="left", va="center", zorder=6)
        ax.text(96, y, area, fontsize=10.5, fontfamily=MONO, color=CYAN,
                ha="right", va="center", zorder=6)

    ax.text(4, 45, "Memory in flip-flops (no SRAM macros);",
            fontsize=10, color=SALMON, style="italic", ha="left", va="center",
            zorder=6)
    ax.text(4, 40.5, "real area with no hard memories, pessimistic by design.",
            fontsize=10, color=SALMON, style="italic", ha="left", va="center",
            zorder=6)

    ax.text(4, 29, "VERIFICATION", fontsize=10.5, fontfamily=MONO,
            fontweight="bold", color=CYAN, ha="left", va="center", zorder=6)
    vlines = [
        "7 modules PASS on dedicated droplet.",
        "Mutant gate: fifo 3/3, CDC 2/2, router 3/3,",
        "soma 2/2, dendrite 1+1 justified.",
    ]
    for k, s in enumerate(vlines):
        ax.text(4, 24.0 - 5 * k, s, fontsize=9.5, fontfamily=MONO, color=MUTED,
                ha="left", va="center", zorder=6)


def main():
    plt.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "font.family": "DejaVu Sans",
        "text.color": TEXT,
    })
    fig = plt.figure(figsize=(FIG_W, FIG_H))

    draw_header(fig)
    draw_panel_a(make_panel(fig, (0.040, 0.585, 0.920, 0.330)))
    draw_panel_b(make_panel(fig, (0.040, 0.465, 0.920, 0.105)))
    draw_panel_c(make_panel(fig, (0.040, 0.045, 0.520, 0.405)),
                 panel_w_in=0.520 * FIG_W, panel_h_in=0.405 * FIG_H)
    draw_panel_d(make_panel(fig, (0.575, 0.045, 0.385, 0.405)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
