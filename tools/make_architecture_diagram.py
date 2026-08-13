# SPDX-License-Identifier: AGPL-3.0-or-later
"""make_architecture_diagram.py — the readable block diagram of the SoC v1.

Every box and wire maps 1:1 to a Verilog module/port in rtl/. Drawn with
matplotlib so it stays regenerable; not a static art asset.

Output: render/architecture_block.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "render" / "architecture_block.png"

C_TILE = "#e8f4f8"   # tile face
C_SOMA = "#2a9d8f"   # soma
C_DEND = "#e76f51"   # dendrite table
C_Q = "#8d99ae"      # fifos
C_MESH = "#264653"   # mesh
C_RTR = "#3d6a80"
C_TXT = "#14213d"

fig, ax = plt.subplots(figsize=(15.5, 10))
ax.set_xlim(0, 155)
ax.set_ylim(0, 100)
ax.axis("off")


def box(x, y, w, h, fc, label, sub="", tc=C_TXT, fs=10, ec="#333333", lw=1.2,
        z=2, alpha=1.0):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.35",
                       fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2 + (h * 0.14 if sub else 0), label,
            ha="center", va="center", fontsize=fs, color=tc, zorder=z + 1,
            fontweight="bold")
    if sub:
        ax.text(x + w / 2, y + h / 2 - h * 0.22, sub, ha="center",
                va="center", fontsize=fs - 1.6, color=tc, zorder=z + 1)
    return p


def arrow(x1, y1, x2, y2, label="", fs=8.5, color="#333333", ls="-",
          lw=1.6, xo=0.5, yo=0.0, z=3):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                        mutation_scale=13, color=color, lw=lw, ls=ls,
                        zorder=z)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2) / 2 + xo, (y1 + y2) / 2 + yo, label, fontsize=fs,
                color=color, ha="center", zorder=z)


# ---------------- outer SoC frame ----------------
box(28, 8, 122, 84, "#fbfbf8", "", ec="#666666", lw=2.2, z=1)
ax.text(29.5, 89.2, "celiumneur_soc  (rtl/top/celiumneur_soc.v)",
        fontsize=11, fontweight="bold", color=C_TXT)

# ---------------- host pins (left of the chip) ----------------
pins = [
    ("clk / rst_n / tick / integrate_open", 74),
    ("stim: stim_tile·valid·neuron·weight", 64),
    ("cfg:  cfg_tile·en·addr·wdata·which·soma_data", 54),
    ("readback: rb_tile·addr·req → rb_dend/soma_rdata", 44),
    ("mesh_overflow_any[3:0] (witness)", 34),
]
for label, y in pins:
    box(0.5, y - 2.6, 25, 6.2, "#ffffff", label, fs=8.6, ec="#2a6f97", lw=1.4)
    arrow(26, y - 0.0, 28.4, y - 0.0, color="#2a6f97", lw=2.0)

# ---------------- tiles ----------------
def tile(x, y, name, gid, role):
    box(x, y, 40, 26, C_TILE, "", ec=C_TXT, lw=1.6, z=2)
    ax.text(x + 2, y + 23.1, name, fontsize=10.5, fontweight="bold",
            color=C_TXT, zorder=5)
    ax.text(x + 2, y + 20.7, gid, fontsize=8, color="#555555", zorder=5)
    box(x + 1.6, y + 12.4, 17.5, 7.4, C_SOMA, "soma_core", "4× LIF, nram 64b/neuron",
        tc="white", fs=8.4, z=3)
    box(x + 20.8, y + 12.4, 17.5, 7.4, C_DEND, "soma_dendrite",
        "synaptic table + fire arbiter", tc="white", fs=8.4, z=3)
    box(x + 1.6, y + 6.2, 17.5, 4.6, C_Q, "inq 11b×8 (phase fence)",
        tc="white", fs=7.8, z=3)
    box(x + 20.8, y + 6.2, 17.5, 4.6, C_Q, "fireq 8b×4 ∥ pktq 32b×4",
        tc="white", fs=7.8, z=3)
    box(x + 11.0, y + 1.4, 18.0, 3.6, C_Q, "outq 32b×4 → egress",
        tc="white", fs=7.8, z=3)
    ax.text(x + 20, y - 2.2, role, fontsize=8.2, color="#333333",
            ha="center", zorder=5)


tile(32, 56, "neuro_tile t0", "GID_BASE 0",  "electrode A (demo)")
tile(32, 14, "neuro_tile t1", "GID_BASE 4",  "electrode B (demo)")
tile(104, 56, "neuro_tile t2", "GID_BASE 8", "detector (demo)")
tile(104, 14, "neuro_tile t3", "GID_BASE 12", "output (demo)")

# ---------------- central mesh ----------------
box(74.5, 30, 27, 40, C_MESH, "", ec=C_TXT, lw=1.6, z=2)
ax.text(88, 67.4, "hyphae_mesh_2x2", fontsize=10, fontweight="bold",
        color="white", ha="center", zorder=5)
ax.text(88, 64.6, "4× hypha_router · X–Y · credits", fontsize=8,
        color="#cfe8ef", ha="center", zorder=5)
for i, (rx, ry) in enumerate([(76.5, 52), (89, 52), (76.5, 38), (89, 38)]):
    box(rx, ry, 11, 9, C_RTR, f"r{i}", "XY-prio FIFOs", tc="white", fs=8.4, z=4)
ax.plot([82, 89], [56.5, 56.5], color="#9fd8e0", lw=2, zorder=3)
ax.plot([82, 89], [42.5, 42.5], color="#9fd8e0", lw=2, zorder=3)
ax.plot([82, 82], [47, 52], color="#9fd8e0", lw=2, zorder=3)
ax.plot([94.5, 94.5], [47, 52], color="#9fd8e0", lw=2, zorder=3)
box(74.5, 31.5, 27, 4.8, "#1d3557",
    "per-core PE credit counters (room)", tc="white", fs=8.0, z=4)

# ---------------- tile <-> mesh wiring ----------------
# t0 / t2 = top row, t1 / t3 = bottom row (mirrors rtl/top wiring)
arrow(72, 78.5, 82, 61.5, "out_spk (credit-gated)", fs=8, yo=2.2)
arrow(80, 59.5, 72, 64.5, "spk out of mesh → inq", fs=8, yo=-2.8, xo=4)
arrow(72, 28.5, 82, 41.5, "", fs=8)
arrow(80, 44.5, 72, 35.5, "", fs=8)
arrow(104, 78.5, 94, 61.5, "", fs=8)
arrow(96, 59.5, 104, 66.5, "", fs=8)
arrow(104, 28.5, 94, 41.5, "", fs=8)
arrow(96, 44.5, 104, 35.5, "", fs=8)

# ---------------- packet format strip ----------------
ax.text(1, 3.3, "fabric packet (32b):", fontsize=9, fontweight="bold",
        color=C_TXT, va="center")
seg = [("[31:28] tag=1", 16, "#2a9d8f"), ("[27:24] rsvd", 14, "#8d99ae"),
       ("[23:20] dst mask", 21, "#e76f51"), ("[19] tick parity", 21, "#f4a261"),
       ("[18:10] rsvd", 16, "#8d99ae"), ("[9:0] source gid", 26, "#2a9d8f")]
x = 21
for label, w, color in seg:
    box(x, 1.2, w, 4.2, color, label, tc="white", fs=8.2, ec="#333333", z=3)
    x += w + 0.8

# ---------------- annotation: the fired demo net ----------------
ax.text(88, 95.5, "CeliumNeUR SoC v1 — block-level architecture (1:1 with rtl/)",
        fontsize=13, fontweight="bold", ha="center", color=C_TXT)
ax.text(88, 92.6,
        "4 neuro_tiles (4 LIF neurons each) on a 2×2 credit-based mesh; "
        "egress packets carry tick parity so deliveries are phase-gated",
        fontsize=9.5, ha="center", color="#333333")

plt.tight_layout()
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
print(f"wrote {OUT}")
