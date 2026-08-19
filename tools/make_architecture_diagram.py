# SPDX-License-Identifier: Apache-2.0
"""Render the current CeliumNeUR SoC contract as PNG and SVG.

The diagram mirrors the default 4x256 top-level and its public transaction
boundaries. It intentionally distinguishes routed traffic, queued control and
non-invasive observation instead of presenting implementation-free artwork.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = (
    ROOT / "render" / "architecture_block.png",
    ROOT / "render" / "architecture_block.svg",
    ROOT / "render" / "celiumneur_soc_map.png",
    ROOT / "render" / "celiumneur_soc_map.svg",
)

BG = "#07131f"
PANEL = "#0d2233"
PANEL_2 = "#102b3e"
INK = "#e8f1f5"
MUTED = "#91a9b7"
CYAN = "#41d6c3"
BLUE = "#4aa8ff"
ORANGE = "#ff9f5a"
MAGENTA = "#dc7cff"
RED = "#ff6577"
GRID = "#244457"


fig, ax = plt.subplots(figsize=(16, 10.5), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 160)
ax.set_ylim(0, 105)
ax.axis("off")


def box(x, y, width, height, label="", subtitle="", *, face=PANEL,
        edge=GRID, text=INK, linewidth=1.2, radius=0.7, label_size=9,
        subtitle_size=7.2, zorder=2):
    patch = FancyBboxPatch(
        (x, y), width, height,
        boxstyle=f"round,pad=0.35,rounding_size={radius}",
        facecolor=face, edgecolor=edge, linewidth=linewidth, zorder=zorder,
    )
    ax.add_patch(patch)
    if label:
        label_y = y + height / 2 + (height * 0.15 if subtitle else 0)
        ax.text(x + width / 2, label_y, label, ha="center", va="center",
                color=text, fontsize=label_size, fontweight="bold",
                zorder=zorder + 1)
    if subtitle:
        ax.text(x + width / 2, y + height / 2 - height * 0.19, subtitle,
                ha="center", va="center", color=MUTED,
                fontsize=subtitle_size, zorder=zorder + 1)
    return patch


def arrow(start, end, *, color=CYAN, label="", width=1.7,
          style="-|>", curve=0.0, label_offset=(0, 0), zorder=5):
    patch = FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=12,
        connectionstyle=f"arc3,rad={curve}", color=color,
        linewidth=width, zorder=zorder,
    )
    ax.add_patch(patch)
    if label:
        mx = (start[0] + end[0]) / 2 + label_offset[0]
        my = (start[1] + end[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, color=color, fontsize=7.3,
                ha="center", va="center", zorder=zorder + 1,
                bbox={"facecolor": BG, "edgecolor": "none", "pad": 1.0})


def tile(x, y, tile_id, gid_range, default_route):
    box(x, y, 42, 27, face=PANEL_2, edge=BLUE, linewidth=1.5, radius=1.2)
    ax.text(x + 2, y + 24.4, f"TILE {tile_id}", color=INK, fontsize=10.2,
            fontweight="bold", va="center", zorder=5)
    ax.text(x + 40, y + 24.4, f"GID {gid_range}", color=BLUE, fontsize=8,
            ha="right", va="center", zorder=5)

    box(x + 1.7, y + 12.2, 18.3, 9.1, "SomaCore", "256 x 64-bit LIF state",
        face="#123c45", edge=CYAN, label_size=8.4, subtitle_size=6.6, zorder=3)
    box(x + 22, y + 12.2, 18.3, 9.1, "Dendrite + CWR",
        "256 x 27-bit synapses", face="#3c2731", edge=ORANGE,
        label_size=8.2, subtitle_size=6.6, zorder=3)
    box(x + 1.7, y + 6.1, 13.2, 4.2, "CONFIG endpoint", "5-flit assembler",
        face="#292342", edge=MAGENTA, label_size=7.1, subtitle_size=5.8, zorder=3)
    box(x + 16.2, y + 6.1, 11.4, 4.2, "Queues", "stim / fire / pkt",
        face="#1b3343", edge=GRID, label_size=7.1, subtitle_size=5.8, zorder=3)
    box(x + 28.9, y + 6.1, 11.4, 4.2, "Axon table", "256 x dst_mask[3:0]",
        face="#1b3343", edge=GRID, label_size=7.1, subtitle_size=5.8, zorder=3)

    ax.text(x + 2, y + 2.6, "independent live readback", color=CYAN,
            fontsize=6.8, va="center", zorder=5)
    ax.text(x + 40, y + 2.6, f"reset route: {default_route}", color=MUTED,
            fontsize=6.8, ha="right", va="center", zorder=5)


# Title and truth boundary.
ax.text(4, 100, "CELIUMNEUR v1", color=INK, fontsize=22,
        fontweight="bold", va="center")
ax.text(4, 95.7, "DEFAULT RTL ARCHITECTURE  /  4 TILES × 256 NEURONS",
        color=CYAN, fontsize=9.5, fontweight="bold", va="center")
ax.text(156, 99.4, "SYNTHESIZABLE RTL • NOT PnR / NOT SILICON",
        color=ORANGE, fontsize=8.2, ha="right", va="center")

# SoC frame.
box(27.5, 10, 128.5, 82, face="#091b28", edge="#3b6479",
    linewidth=1.8, radius=1.5, zorder=1)
ax.text(30, 88.8, "celiumneur_soc", color=INK, fontsize=10,
        fontweight="bold", zorder=5)
ax.text(153.5, 88.8, "single clock domain", color=MUTED, fontsize=7.5,
        ha="right", zorder=5)

# External transaction surfaces.
box(2.5, 69, 21.5, 14.5, "HOST INGRESS", "valid / packet[31:0] / ready",
    face="#171d35", edge=MAGENTA, label_size=8.5)
box(2.5, 50.5, 21.5, 13.5, "GLOBAL TICK", "8-token FIFO • atomic fanout",
    face="#122c38", edge=CYAN, label_size=8.5)
box(2.5, 33.5, 21.5, 12, "STIMULUS", "tile / neuron / weight / ready",
    face="#2d261b", edge=ORANGE, label_size=8.5)
box(2.5, 16.5, 21.5, 12, "READBACK", "tile / address → soma + dendrite",
    face="#12323a", edge=CYAN, label_size=8.5)

ax.plot([24.2, 28, 28, 92, 92], [76, 76, 86, 86, 77], color=MAGENTA,
        linewidth=1.7, zorder=5)
arrow((92, 77), (92, 76.4), color=MAGENTA)
ax.text(61, 87.3, "routed CONFIG or SPIKE", color=MAGENTA, fontsize=7.3,
        ha="center", va="center", zorder=6,
        bbox={"facecolor": BG, "edgecolor": "none", "pad": 1.0})
arrow((24.2, 57), (31, 57), color=CYAN, label="queued token",
      label_offset=(1.2, 2.0))
arrow((24.2, 39.5), (31, 39.5), color=ORANGE)
arrow((31, 22.5), (24.2, 22.5), color=CYAN, label="non-invasive",
      label_offset=(0.3, 2.0))

# Four physical tile instances.
tile(31, 57, 0, "0–255", "T2")
tile(31, 17, 1, "256–511", "T2")
tile(111, 57, 2, "512–767", "T3")
tile(111, 17, 3, "768–1023", "none")

# Central 2x2 fabric.
box(77, 27.5, 30, 49, face="#0b2635", edge=CYAN,
    linewidth=1.6, radius=1.2, zorder=2)
ax.text(92, 72.6, "HYPHAE 2×2", color=INK, fontsize=10,
        fontweight="bold", ha="center", zorder=5)
ax.text(92, 69.9, "X-first • multicast • credits", color=CYAN,
        fontsize=7.1, ha="center", zorder=5)

router_positions = ((80, 55, "R0"), (95, 55, "R2"),
                    (80, 39, "R1"), (95, 39, "R3"))
for rx, ry, name in router_positions:
    box(rx, ry, 9.5, 9.5, name, "5× FIFO(4)", face="#164359",
        edge=BLUE, label_size=8.2, subtitle_size=6.0, zorder=4)

arrow((89.7, 59.7), (94.8, 59.7), color=BLUE, style="<|-|>", width=1.3)
arrow((89.7, 43.7), (94.8, 43.7), color=BLUE, style="<|-|>", width=1.3)
arrow((84.7, 49), (84.7, 54.8), color=BLUE, style="<|-|>", width=1.3)
arrow((99.7, 49), (99.7, 54.8), color=BLUE, style="<|-|>", width=1.3)
box(79.5, 30, 25, 5.3, "PE delivery", "valid/ready • held under stall",
    face="#102f3f", edge=GRID, label_size=7.2, subtitle_size=5.8, zorder=4)

# Tile/fabric duplex links. Slight curves keep crossings legible.
arrow((73.2, 70), (79.2, 62), color=BLUE, style="<|-|>", curve=-0.12)
arrow((73.2, 31), (79.2, 42), color=BLUE, style="<|-|>", curve=0.12)
arrow((110.8, 70), (104.8, 62), color=BLUE, style="<|-|>", curve=0.12)
arrow((110.8, 31), (104.8, 42), color=BLUE, style="<|-|>", curve=-0.12)

# Public pressure/witness strip.
box(80, 12.8, 24, 10, "PRESSURE + WITNESSES",
    "overflow • busy • stall count\nprotocol error • unsupported packet",
    face="#321e29", edge=RED, label_size=7.6, subtitle_size=6.1, zorder=3)
arrow((92, 27.3), (92, 22.9), color=RED, style="-|>", width=1.4)

# Packet legend, visually distinct from physical modules.
ax.text(28.5, 5.4, "HYPHAE FLIT 32b", color=MUTED, fontsize=7.2,
        fontweight="bold", va="center")
segments = (
    ("type [31:28]", 19, MAGENTA),
    ("reserved=0 [27:24]", 25, "#526777"),
    ("dst mask [23:20]", 23, ORANGE),
    ("type-specific body [19:0]", 38, BLUE),
)
x = 48
for label, width, color in segments:
    box(x, 3.1, width, 4.8, label, face=color, edge=color,
        text=BG if color in (ORANGE, BLUE) else INK, label_size=7.1,
        linewidth=0.7, radius=0.35, zorder=3)
    x += width + 0.8

ax.text(156, 1.2,
        "CONFIG = ordered header + 4×16-bit fragments  •  SPIKE = parity + GID[9:0]",
        color=MUTED, fontsize=6.8, ha="right", va="bottom")

fig.subplots_adjust(left=0.015, right=0.985, top=0.985, bottom=0.02)
for output in OUTPUTS:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180 if output.suffix == ".png" else None,
                facecolor=BG, bbox_inches="tight")
    if output.suffix == ".svg":
        lines = output.read_text(encoding="utf-8").splitlines()
        output.write_text("\n".join(line.rstrip() for line in lines) + "\n",
                          encoding="utf-8", newline="\n")
    print(f"wrote {output}")


def render_tile_map():
    """Render the queue/ownership contract inside one default tile."""
    tile_fig, tile_ax = plt.subplots(figsize=(16, 8.8), facecolor=BG)
    tile_ax.set_facecolor(BG)
    tile_ax.set_xlim(0, 160)
    tile_ax.set_ylim(0, 88)
    tile_ax.axis("off")

    def tile_box(x, y, width, height, label, subtitle="", *, face=PANEL,
                 edge=GRID, label_size=9):
        patch = FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.35,rounding_size=0.8",
            facecolor=face, edgecolor=edge, linewidth=1.4,
        )
        tile_ax.add_patch(patch)
        tile_ax.text(x + width / 2, y + height / 2 + (1.8 if subtitle else 0),
                     label, color=INK, fontsize=label_size, fontweight="bold",
                     ha="center", va="center")
        if subtitle:
            tile_ax.text(x + width / 2, y + height / 2 - 2.2,
                         subtitle, color=MUTED, fontsize=6.7,
                         ha="center", va="center")

    def tile_arrow(start, end, color=CYAN, label="", curve=0.0):
        tile_ax.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=13,
            connectionstyle=f"arc3,rad={curve}", color=color,
            linewidth=1.7, zorder=5,
        ))
        if label:
            tile_ax.text((start[0] + end[0]) / 2,
                         (start[1] + end[1]) / 2 + 2.0,
                         label, color=color, fontsize=7, ha="center",
                         bbox={"facecolor": BG, "edgecolor": "none", "pad": 1})

    tile_ax.text(4, 83, "NEURO_TILE — TRANSACTION OWNERSHIP MAP",
                 color=INK, fontsize=20, fontweight="bold")
    tile_ax.text(4, 78.6,
                 "default instance: 256 neurons • 256 synapses • held valid/ready seams",
                 color=CYAN, fontsize=9, fontweight="bold")

    tile_box(3, 54, 22, 13, "MESH DELIVERY", "SPIKE or CONFIG", face="#17243c",
             edge=BLUE)
    tile_box(3, 33, 22, 13, "STIMULUS", "local neuron + weight", face="#34281c",
             edge=ORANGE)
    tile_box(3, 12, 22, 13, "READBACK", "address → live state", face="#12323a",
             edge=CYAN)

    tile_box(33, 56, 25, 11, "TYPE / PHASE GATE", "one-hot mask • reserved=0",
             face="#192b3d", edge=BLUE)
    tile_box(33, 37, 25, 11, "STIM FIFO", "16-bit × 8", face="#1b3343")
    tile_box(33, 18, 25, 11, "CONFIG ENDPOINT", "header + four fragments",
             face="#292342", edge=MAGENTA)

    tile_box(67, 48, 27, 20, "DENDRITE", "256 × 27-bit table\nintegration walker",
             face="#3c2731", edge=ORANGE, label_size=10)
    tile_box(67, 20, 27, 17, "LEARNING WALKER", "CWR latest-arrival ledger",
             face="#33243b", edge=MAGENTA, label_size=9)
    tile_box(103, 48, 27, 20, "SOMA CORE", "256 × 64-bit state\nheld fire channel",
             face="#123c45", edge=CYAN, label_size=10)
    tile_box(103, 20, 27, 17, "FIRE RECORD", "physical tick + neuron + packet",
             face="#1b3343", edge=GRID, label_size=9)
    tile_box(138, 48, 19, 20, "AXON TABLE", "256 ×\ndst_mask[3:0]",
             face="#17243c", edge=BLUE, label_size=8.5)
    tile_box(138, 20, 19, 17, "OUTQ + EGRESS", "valid held until ready",
             face="#17243c", edge=BLUE, label_size=8.5)

    tile_arrow((25, 60.5), (33, 61.5), BLUE)
    tile_arrow((58, 61.5), (67, 58), BLUE, "accepted spike")
    tile_arrow((25, 39.5), (33, 42.5), ORANGE)
    tile_arrow((58, 42.5), (67, 53), ORANGE, "queued event")
    tile_arrow((94, 58), (103, 58), ORANGE, "soma event")
    tile_arrow((116.5, 48), (116.5, 37), CYAN, "held fire")
    tile_arrow((138, 54), (130, 34), BLUE, "route mask", curve=-0.12)
    tile_arrow((130, 28.5), (138, 28.5), BLUE)
    tile_arrow((103, 28.5), (94, 28.5), MAGENTA, "learning fire")
    tile_arrow((80.5, 37), (80.5, 48), MAGENTA)
    tile_arrow((58, 23.5), (67, 53), MAGENTA, "space 0", curve=0.16)
    tile_arrow((58, 23.5), (103, 55), MAGENTA, "space 1", curve=0.18)
    tile_arrow((58, 23.5), (138, 55), MAGENTA, "space 2", curve=0.20)
    tile_arrow((67, 55), (25, 18.5), CYAN, "dendrite read", curve=-0.25)
    tile_arrow((103, 55), (25, 18.5), CYAN, "soma read", curve=-0.16)

    tile_ax.text(80, 7,
                 "A physical fire is captured once. Learning and egress consume that record independently; stalling cannot rewrite it.",
                 color=ORANGE, fontsize=8.5, ha="center", fontweight="bold")
    tile_ax.text(157, 83, "rtl/soma/neuro_tile.v", color=MUTED,
                 fontsize=7.5, ha="right")

    tile_fig.subplots_adjust(left=0.015, right=0.985, top=0.98, bottom=0.025)
    for suffix in ("png", "svg"):
        output = ROOT / "render" / f"neuro_tile_map.{suffix}"
        tile_fig.savefig(output, dpi=180 if suffix == "png" else None,
                         facecolor=BG, bbox_inches="tight")
        if suffix == "svg":
            lines = output.read_text(encoding="utf-8").splitlines()
            output.write_text("\n".join(line.rstrip() for line in lines) + "\n",
                              encoding="utf-8", newline="\n")
        print(f"wrote {output}")
    plt.close(tile_fig)


render_tile_map()
