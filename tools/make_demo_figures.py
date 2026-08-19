# SPDX-License-Identifier: Apache-2.0
"""make_demo_figures.py — regenerate the README evidence figures from REAL runs.

Nothing hardcoded: the chip panel comes from the actual cocotb SoC run's
chip_fires.json (written by soc_test.py into sim_build/celiumneur_soc/),
and the plasticity trajectory comes from the actual golden
demo_plasticity.run_plasticity_demo (30 rounds).

Outputs:
  golden/demo_raster_compare.png   (golden vs chip raster twins)
  render/plasticity_trajectory.png (CWR paired vs uncorrelated wire)

Usage (from repo root):  python tools/make_demo_figures.py
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "golden"))

from demo_net import (                                      # noqa: E402
    build_demo,
    run_demo_script,
    ELECTRODE_A,
    ELECTRODE_B,
    DETECTOR,
    OUTPUT,
)
from demo_plasticity import run_plasticity_demo           # noqa: E402

LABELS = [
    (ELECTRODE_A, f"n{ELECTRODE_A} electrode A"),
    (ELECTRODE_B, f"n{ELECTRODE_B} electrode B"),
    (DETECTOR, f"n{DETECTOR} detector"),
    (OUTPUT, f"n{OUTPUT} output"),
]


def raster_panel(ax, events, title):
    rows = {gid: [t for t, g in events if g == gid] for gid, _ in LABELS}
    for row, (gid, lab) in enumerate(LABELS):
        ax.eventplot(rows[gid], lineoffsets=row, linelengths=0.6,
                     linewidths=6, colors="black")
    ax.set_yticks(range(len(LABELS)))
    ax.set_yticklabels([lab for _, lab in LABELS])
    ax.set_title(title, fontsize=11)
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlim(-0.3, None)


def fig_raster_compare():
    box = build_demo()
    run_demo_script(box)
    golden_events = list(box.fire_log)
    chip_json = ROOT / "verification/cocotb/sim_build/celiumneur_soc/chip_fires.json"
    chip_events = None
    if chip_json.exists():
        chip_events = json.loads(chip_json.read_text())["chip"]
    else:
        # regenerable fallback: run `python verification/cocotb/run_tests.py
        # celiumneur_soc` first. Never ship an invented chip trace.
        raise SystemExit("chip_fires.json not found — run the soc bench first")

    golden_multiset = sorted(gid for _tick, gid in golden_events)
    chip_multiset = sorted(gid for _tick, gid in chip_events)
    print("golden multiset:", golden_multiset)
    print("chip   multiset:", chip_multiset)
    if golden_multiset != chip_multiset:
        raise SystemExit(
            "refusing to overwrite the raster: RTL and golden multisets differ"
        )

    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True)
    raster_panel(axes[0], golden_events, "GOLDEN sandbox fire_log")
    raster_panel(axes[1], chip_events, "CELIUMNEUR chip (RTL SoC) fire_log")
    axes[1].set_xlabel("tick")
    fig.tight_layout()
    out = ROOT / "golden" / "demo_raster_compare.png"
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")
    print("raster twin multisets EQUAL")


def fig_plasticity():
    box = build_demo()
    traj = run_plasticity_demo(box)
    rounds = range(len(traj["paired"]))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(rounds, traj["paired"], "-o", ms=3.5, lw=1.6, color="#0b8043",
            label="A→detector (paired every round) — LTP")
    ax.plot(rounds, traj["control"], "-s", ms=3.5, lw=1.6, color="#b3261e",
            label="C→detector (never paired) — LTD")
    ax.axhline(127, color="#0b8043", ls=":", lw=1, alpha=0.5)
    ax.axhline(-127, color="#b3261e", ls=":", lw=1, alpha=0.5)
    ax.text(len(rounds) - 1, 129, "rail +127 (saturating)", fontsize=8,
            color="#0b8043", ha="right")
    ax.text(len(rounds) - 1, -131, "floor −127", fontsize=8, color="#b3261e",
            ha="right", va="top")
    ax.set_xlabel("round (one paired-burst cycle each)")
    ax.set_ylabel("synaptic weight (8-bit signed)")
    ax.set_title("CWR learning on the golden referee (golden/demo_plasticity.py)")
    ax.legend(loc="center right", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = ROOT / "render" / "plasticity_trajectory.png"
    fig.savefig(out, dpi=140)
    print(f"wrote {out}  paired: {traj['paired'][0]}..{traj['paired'][-1]}  "
          f"control: {traj['control'][0]}..{traj['control'][-1]}")
    assert traj["paired"][-1] > traj["paired"][0]
    assert traj["control"][-1] < traj["control"][0]


if __name__ == "__main__":
    fig_raster_compare()
    fig_plasticity()
    print("DEMO FIGURES OK")
