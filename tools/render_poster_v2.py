# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the CeliumNeUR SoC v1 technical poster, v2 (dark technical style).

Usage:  .venv/Scripts/python.exe tools/render_poster_v2.py
Output: render/poster_celiumneur_soc_v2.png  (16.5x20.5 in @ 100 dpi)

v2 changes vs v1:
- Panel A is a strict left->right dataflow (5 stations, arrows in/out at
  box mid-height, explanations and RTL file labels stacked BELOW the boxes
  so nothing overlaps).
- Panel B packet anatomy: every label sits below the bar in two alternating
  rows with dotted guides (widths stay proportional to bit count).
- Panel C keeps the raster compare, note keeps its tilde.
- Panel D same hard data + flip-flop note + verification line.
- Panel E is new: CWR learning trajectories (real A->8 / C->8 data from
  golden/demo_plasticity.py — no hardcoded points).

Every number/label is sourced from SPEC.md and rtl/ — nothing invented.
Panels own a normalized 0..100 local space; text is budget-checked against
box widths (DejaVu Sans Mono advance ~= 0.602 em) so nothing leaks.
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
OUT = ROOT / "render" / "poster_celiumneur_soc_v2.png"

BG = "#0b1020"      # poster background
PANEL = "#0e1628"   # panel fill
EDGE = "#2b3d63"    # structural borders
CYAN = "#35d6ea"
CYAN_FILL = "#10303f"
SALMON = "#ff8f6b"
SALMON_FILL = "#37231a"
TEXT = "#dce7f7"
MUTED = "#93a7c4"
GRAY = "#6f86b8"    # RTL file labels
MONO = "DejaVu Sans Mono"

FIG_W, FIG_H, DPI = 16.5, 20.5, 100


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


def fwd_arrow(ax, p0, p1, color=CYAN, lw=2.0, ms=16, z=4):
    """Single-headed arrow: dataflow direction is explicit, never implied."""
    ax.add_patch(
        FancyArrowPatch(
            p0, p1, arrowstyle="-|>", mutation_scale=ms,
            linewidth=lw, color=color, shrinkA=0, shrinkB=0, zorder=z,
        )
    )


def draw_header(fig):
    fig.text(0.5, 0.9720, "CELIUMNEUR — the chip that has no secrets",
             fontsize=36, fontweight="bold", color=CYAN,
             ha="center", va="center")
    fig.text(0.5, 0.9500,
             "Transparent (I5)  ·  Cannot drop a spike (I1)  ·  "
             "Learns without stopping (I4)",
             fontsize=15.5, color=TEXT, ha="center", va="center")
    fig.text(0.982, 0.9895, "CeliumNeUR SoC v1 — poster v2", fontsize=10,
             fontfamily=MONO, color=MUTED, ha="right", va="center")
    fig.add_artist(Line2D([0.06, 0.94], [0.9375, 0.9375],
                          color=SALMON, linewidth=1.3, alpha=0.75,
                          transform=fig.transFigure))


# --- Panel A mini-diagram icons (drawn fully inside each station box) -----

def icon_pulse(ax, cx, cy, s=1.0):
    """Electrode injecting a spike: flat - rise - undershoot - flat."""
    xs = [cx - 5.6 * s, cx - 2.4 * s, cx - 0.9 * s, cx + 0.4 * s,
          cx + 1.8 * s, cx + 5.6 * s]
    ys = [cy, cy, cy + 6.5 * s, cy - 5.0 * s, cy, cy]
    ax.add_line(Line2D(xs, ys, color=CYAN, linewidth=1.8, zorder=5,
                       solid_capstyle="round"))
    ax.plot([cx - 5.6 * s], [cy], marker="o", ms=5, color=SALMON, zorder=6)


def icon_mesh_xy(ax, cx, cy, s=1.0):
    """2x2 router mini-grid with an X-first-then-Y highlighted path."""
    cell, gap = 3.0 * s, 0.8 * s
    gx, gy = cx - 3.4 * s, cy - 3.4 * s
    for ix in range(2):
        for iy in range(2):
            ax.add_patch(Rectangle(
                (gx + ix * (cell + gap), gy + iy * (cell + gap)),
                cell, cell, facecolor="#12303f", edgecolor="#7ee7f4",
                linewidth=1.0, zorder=4))
    c00 = (gx + cell / 2, gy + cell + gap + cell / 2)     # top-left
    c01 = (gx + cell + gap + cell / 2, c00[1])            # top-right
    c11 = (c01[0], gy + cell / 2)                         # bottom-right
    fwd_arrow(ax, (c00[0] - 0.4 * s, c00[1]), (c01[0] + 0.4 * s, c01[1]),
              color=SALMON, lw=1.2, ms=7, z=5)
    fwd_arrow(ax, (c01[0], c01[1] - 0.2 * s), (c11[0], c11[1]),
              color=SALMON, lw=1.2, ms=7, z=5)
    ax.text(cx + 4.2 * s, c00[1], "X", fontsize=7, fontfamily=MONO,
            color=MUTED, ha="left", va="center", zorder=5)
    ax.text(cx - 4.2 * s, c11[1], "Y", fontsize=7, fontfamily=MONO,
            color=MUTED, ha="right", va="center", zorder=5)


def icon_table(ax, cx, cy, s=1.0):
    """Routing table: header row + grid of entries."""
    w, h = 11.0 * s, 9.5 * s
    x0, y0 = cx - w / 2, cy - h / 2
    ax.add_patch(Rectangle((x0, y0), w, h, facecolor=SALMON_FILL,
                           edgecolor=SALMON, linewidth=1.2, zorder=4))
    ax.add_patch(Rectangle((x0, y0 + h - 2.4 * s), w, 2.4 * s,
                           facecolor="#4a2e1f", edgecolor=SALMON,
                           linewidth=0.9, zorder=5))
    for k in (1, 2):
        y = y0 + k * (h - 2.4 * s) / 3
        ax.plot([x0, x0 + w], [y, y], color=SALMON, lw=0.7, alpha=0.55,
                zorder=5)
    ax.plot([cx, cx], [y0, y0 + h - 2.4 * s], color=SALMON, lw=0.7,
            alpha=0.55, zorder=5)


def icon_threshold(ax, cx, cy, s=1.0):
    """Membrane ramp crossing the firing threshold."""
    ax.plot([cx - 6.0 * s, cx + 6.0 * s], [cy + 3.4 * s, cy + 3.4 * s],
            color=SALMON, lw=1.1, ls=(0, (4, 2.5)), zorder=4)
    xs, ys = [], []
    x, y = cx - 6.0 * s, cy - 4.2 * s
    step = 2.4 * s
    rise = 1.9 * s
    for k in range(4):
        xs += [x, x + step]
        ys += [y, y]
        x += step
        y += rise
    xs.append(x - step + 0.9 * s)
    ys.append(cy + 3.4 * s)
    ax.add_line(Line2D(xs, ys, color=CYAN, linewidth=1.8, zorder=5))
    ax.plot([xs[-1]], [ys[-1]], marker="*", ms=11, color=SALMON, zorder=6)
    ax.text(cx + 5.9 * s, cy + 5.1 * s, "Vth", fontsize=6.5,
            fontfamily=MONO, color=MUTED, ha="right", va="bottom", zorder=5)


def icon_exit(ax, cx, cy, s=1.0):
    """32-bit packet leaving the chip: packet square + outgoing arrow."""
    ax.add_patch(Rectangle((cx - 6.2 * s, cy - 2.9 * s), 4.2 * s, 5.8 * s,
                           facecolor=CYAN_FILL, edgecolor=CYAN,
                           linewidth=1.2, zorder=4))
    ax.text(cx - 4.1 * s, cy, "32b", fontsize=6, fontfamily=MONO,
            color=TEXT, ha="center", va="center", zorder=6)
    fwd_arrow(ax, (cx - 1.4 * s, cy), (cx + 6.2 * s, cy),
              color=CYAN, lw=1.8, ms=12, z=5)


def draw_panel_a(ax):
    panel_title(ax, "A — Linear dataflow: from electrode to output")

    box_w, box_h, box_y = 16.2, 28.0, 46.0
    gap = (97.0 - 5 * box_w) / 4.0          # 4 uniform gaps, 1.5 margins
    xs = [1.5 + i * (box_w + gap) for i in range(5)]

    stations = [
        dict(title="Electrode · tiles 0-1", accent=CYAN, fc=CYAN_FILL,
             icon=icon_pulse,
             lines=["An external electrode injects",
                    "spikes into tiles 0 and 1;",
                    "they pack into 32 bits."],
             file="rtl/top/celiumneur_soc.v"),
        dict(title="Hyphae mesh 2×2", accent=CYAN, fc="#0e2433",
             icon=icon_mesh_xy,
             lines=["Deterministic X-Y routing:",
                    "column first, then row.",
                    "No spike is ever lost (I1)."],
             file="rtl/top/hyphae_mesh_2x2.v"),
        dict(title="Dendrite/table · tile 2", accent=SALMON, fc=SALMON_FILL,
             icon=icon_table,
             lines=["The dendritic table resolves",
                    "which synaptic weights receive",
                    "the spike: 16 entries."],
             file="rtl/soma/soma_dendrite.v"),
        dict(title="SomaCore detector", accent=CYAN, fc=CYAN_FILL,
             icon=icon_threshold,
             lines=["Integrates membrane charge;",
                    "on threshold crossing it fires",
                    "and sets its phase tag."],
             file="rtl/soma/soma_core.v"),
        dict(title="Output · tile 3", accent=CYAN, fc=CYAN_FILL,
             icon=icon_exit,
             lines=["The fired spike travels to",
                    "tile 3 and exits the chip as",
                    "an observable event."],
             file="rtl/top/celiumneur_soc.v"),
    ]

    mid_y = box_y + box_h / 2.0
    for i, (x, st) in enumerate(zip(xs, stations)):
        cx = x + box_w / 2.0
        rbox(ax, x, box_y, box_w, box_h, ec=st["accent"], fc=st["fc"],
             lw=1.5, r=1.1, z=2)
        ax.text(cx, box_y + box_h - 4.0, st["title"], fontsize=9.0,
                fontweight="bold", color=st["accent"],
                ha="center", va="center", zorder=6)
        st["icon"](ax, cx, mid_y - 2.5)
        # Explanation block: 3 lines below the box, mono, small
        for k, s in enumerate(st["lines"]):
            ax.text(cx, 40.8 - 4.4 * k, s, fontsize=8.5, fontfamily=MONO,
                    color=MUTED, ha="center", va="center", zorder=6)
        # Real RTL file label, gray, below the explanation
        ax.text(cx, 27.4, st["file"], fontsize=7.5, fontfamily=MONO,
                color=GRAY, ha="center", va="center", zorder=6)
        # Clean horizontal arrow: exits right edge, enters next left edge
        if i < 4:
            fwd_arrow(ax, (x + box_w, mid_y), (xs[i + 1], mid_y),
                      color=CYAN, lw=2.0, ms=16)

    ax.text(50, 13.5, "data direction: left → right · "
            "no hidden loops · every spike auditable at every station",
            fontsize=8.5, family=MONO, color=GRAY,
            ha="center", va="center", zorder=6)


def draw_panel_b(ax):
    panel_title(ax, "B — 32-bit packet anatomy")

    x0, y_top, y_bot = 3.0, 72.0, 52.0
    scale = 94.0 / 32.0

    # hi, lo, range label, label lines (below bar), row, fill, edge, color
    fields = [
        (31, 28, "[31:28]", ["type = SPIKE"], 0, "#123a4d", CYAN, CYAN),
        (27, 24, "[27:24]", ["reserved"], 1, "#141c33", "#4a5b85", MUTED),
        (23, 20, "[23:20]", ["dst mask · 4 cores"], 0, "#3a2318",
         SALMON, SALMON),
        (19, 19, "[19]", ["phase parity", "(source-tick parity)"], 1,
         SALMON, SALMON, SALMON),
        (18, 10, "[18:10]", ["zero"], 0, "#0f1526", "#3a4a6e", MUTED),
        (9, 0, "[9:0]", ["neuron gid"], 1, "#123a4d", CYAN, CYAN),
    ]
    row_y = [38.0, 24.0]            # two alternating label rows below bar

    for hi, lo, rng, lines, row, fc, ec, dc in fields:
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
        ly = row_y[row]
        # dotted guide from segment bottom to its label row
        ax.plot([cx, cx], [y_bot, ly + 3.5], color=dc, lw=0.9,
                ls=(0, (1.2, 2.0)), alpha=0.75, zorder=4)
        for k, s in enumerate(lines):
            ax.text(cx, ly - 5.4 * k, s, fontsize=9.5, color=dc,
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
    avail_x, avail_y = 94.0, 76.0                       # local units
    avail_w_in = avail_x / 100.0 * panel_w_in
    img_h_in = avail_w_in * hp / wp
    h_local = img_h_in / panel_h_in * 100.0
    if h_local > avail_y:                               # extremely tall image
        h_local = avail_y
    y0 = 4.0 + (avail_y - h_local) / 2.0 + 4.0
    x0 = 3.0
    ax.imshow(img, extent=[x0, x0 + avail_x, y0, y0 + h_local],
              aspect="auto", zorder=3)
    ax.add_patch(Rectangle((x0, y0), avail_x, h_local, fill=False,
                           edgecolor="#3a4a6e", linewidth=1.2, zorder=4))


def draw_panel_d(ax):
    panel_title(ax, "D — Hard data · GF180 baseline (pre-PnR)", size=13)

    ax.text(4, 82, "Block", fontsize=10.5, fontfamily=MONO,
            fontweight="bold", color=MUTED, ha="left", va="center", zorder=6)
    ax.text(96, 82, "Area", fontsize=10.5, fontfamily=MONO,
            fontweight="bold", color=MUTED, ha="right", va="center", zorder=6)
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

    ax.text(4, 46, "Memory in flip-flops (no SRAM macros);",
            fontsize=10, color=SALMON, style="italic", ha="left",
            va="center", zorder=6)
    ax.text(4, 41.5, "real area with no hard memories, pessimistic by design.",
            fontsize=10, color=SALMON, style="italic", ha="left",
            va="center", zorder=6)

    ax.text(4, 30, "VERIFICATION", fontsize=10.5, fontfamily=MONO,
            fontweight="bold", color=CYAN, ha="left", va="center", zorder=6)
    vlines = [
        "cocotb suite 8/8 groups PASS (incl. SoC",
        "exact-equality vs golden). Golden 53/53.",
        "Mutant gate: fifo 3/3, CDC 2/2,",
        "router 3/3, soma 2/2, dendrite 1K+1J.",
    ]
    for k, s in enumerate(vlines):
        ax.text(4, 25.0 - 5 * k, s, fontsize=9.5, fontfamily=MONO,
                color=MUTED, ha="left", va="center", zorder=6)


def draw_panel_e(fig, rect):
    """Learning trajectories: real run of golden/demo_plasticity.py (no
    hardcoded points — the earlier 10-point hand line was retired)."""
    import sys
    sys.path.insert(0, str(ROOT / "golden"))
    from demo_net import build_demo
    from demo_plasticity import run_plasticity_demo

    traj = run_plasticity_demo(build_demo())

    bg = make_panel(fig, rect)
    panel_title(bg, "E — CWR (causal-window rule) learns in 30 rounds",
                size=13)

    x0, y0, w, h = rect
    ax = fig.add_axes((x0 + 0.045, y0 + 0.038, w - 0.075, h - 0.082))
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color(EDGE)
        spine.set_linewidth(1.1)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=EDGE, linestyle=":", linewidth=0.8, alpha=0.8)

    rondas = list(range(len(traj["A->8"])))
    a_to_8 = traj["A->8"]
    c_to_8 = traj["C->8"]
    ax.plot(rondas, a_to_8, color=CYAN, lw=2.2, marker="o", ms=3,
            label="weight A→8 (paired — potentiates to the +127 rail)")
    ax.plot(rondas, c_to_8, color=SALMON, lw=2.2, marker="s", ms=3,
            label="weight C→8 (never paired — depresses)")

    ax.set_xlim(-0.6, len(rondas) - 0.4)
    ax.set_ylim(85, 133)
    ax.set_xticks(list(range(0, len(rondas), 5)))
    ax.set_xlabel("round", fontsize=10, color=MUTED)
    ax.set_ylabel("weight", fontsize=10, color=MUTED)
    leg = ax.legend(loc="upper left", fontsize=9, facecolor=PANEL,
                    edgecolor=EDGE, framealpha=1.0)
    for t in leg.get_texts():
        t.set_color(TEXT)
    return ax


def main():
    plt.rcParams.update({
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "font.family": "DejaVu Sans",
        "text.color": TEXT,
    })
    fig = plt.figure(figsize=(FIG_W, FIG_H))

    draw_header(fig)
    draw_panel_a(make_panel(fig, (0.035, 0.6600, 0.930, 0.255)))
    draw_panel_b(make_panel(fig, (0.035, 0.5450, 0.930, 0.100)))
    draw_panel_c(make_panel(fig, (0.035, 0.2725, 0.450, 0.245)),
                 panel_w_in=0.450 * FIG_W, panel_h_in=0.245 * FIG_H)
    draw_panel_d(make_panel(fig, (0.515, 0.2725, 0.450, 0.245)))
    draw_panel_e(fig, (0.035, 0.0225, 0.930, 0.235))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
