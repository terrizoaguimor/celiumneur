# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: celiumneur_soc (4 tiles + mesh) vs the NeuroSandbox golden.

The sandbox stages spikes for delivery on the next tick while the chip lets
them flow mid-phase; the honest v1 equality is therefore:
  - same fire MULTISET over the demo run (order by gid),
  - same tile-by-tile quietness between phases (no runaway),
  - detector physical trace readable afterward on both sides.
Tick-for-tick equality of cascades deeper than one hop needs a phase
contract in hardware (deliver-on-tick gating): acknowledged, not fudged.

This bench is the flagship "watch it think" run: demo stimulus in, fire
log out, raster written next to the golden one.
"""

import os
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "golden"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from soma import NeuronParams  # noqa: E402
from soma_test import pack_word  # noqa: E402
from demo_net import build_demo, run_demo_script  # noqa: E402

ELECTRODE_P = NeuronParams(theta=100, leak_shift=1, refractory_ticks=0)
DETECTOR_P = NeuronParams(theta=200, leak_shift=1, refractory_ticks=0)
OUTPUT_P = NeuronParams(theta=100, leak_shift=1, refractory_ticks=4)


async def reset_soc(dut):
    dut.rst_n.value = 0
    for s in ("stim_valid", "cfg_en", "rb_req"):
        getattr(dut, s).value = 0
    if hasattr(dut, "cfg_which"):
        dut.cfg_which.value = 0          # default lane: dendrite table
    if hasattr(dut, "cfg_soma_data"):
        dut.cfg_soma_data.value = 0
    if hasattr(dut, "integrate_open"):
        dut.integrate_open.value = 1
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    # wait out the post-reset wipe sweep on ALL tiles before programming:
    # S_INIT owns each tile's cfg port independently, so t0 going idle says
    # nothing about t2 — a cfg write into a still-sweeping tile is wiped
    for _ in range(400):
        if all(int(getattr(dut, f"t{i}").tile_busy.value) == 0 for i in range(4)):
            break
        await FallingEdge(dut.clk)


@cocotb.test()
async def soc_demo_matches_golden(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_soc(dut)

    chip_fires = []               # (tick_index, gid) for the raster artifact
    tick_box = [0]

    async def fire_monitor():
        busy_seen = 0
        while True:
            await FallingEdge(dut.clk)
            for core in range(4):
                tile = getattr(dut, f"t{core}")
                if int(tile.soma.fire_valid.value):
                    chip_fires.append((tick_box[0], core * 4 + int(tile.soma.fire_neuron.value)))
            if (os.environ.get("SOC_TEST_DEBUG") == "1"
                    and int(dut.t2.tile_busy.value)):
                busy_seen += 1
                if busy_seen <= 12:
                    print(f"    t2.busy tick_box={tick_box[0]} "
                          f"parcel_in={int(dut.pe_out_valid.value) & 4}")

    monitor = cocotb.start_soon(fire_monitor())

    specs = {
        0: (ELECTRODE_P, []),
        1: (ELECTRODE_P, []),
        2: (DETECTOR_P, [(0, 0, 120), (4, 0, 120)]),
        3: (OUTPUT_P, [(8, 0, 120)]),
    }
    for tile_id, (params, entries) in specs.items():
        tile = getattr(dut, f"t{tile_id}")
        for n in range(4):
            tile.soma.nram[n].value = pack_word(params)
        for addr, (pre, post, w) in enumerate(entries):
            dut.cfg_tile.value = tile_id
            dut.cfg_addr.value = addr
            dut.cfg_wdata.value = (1 << 20) | ((pre & 0x3FF) << 10) | \
                                  ((post & 0x3) << 8) | (w & 0xFF)
            dut.cfg_en.value = 1
            await RisingEdge(dut.clk)
            await FallingEdge(dut.clk)
            dut.cfg_en.value = 0

    # ---------------- demo stimulus ----------------
    async def soc_stim(tile, weight):
        dut.stim_tile.value = tile
        dut.stim_neuron.value = 0
        dut.stim_weight.value = weight & 0xFF
        dut.stim_valid.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.stim_valid.value = 0

    async def soc_tick():
        dut.tick.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.tick.value = 0
        tick_box[0] += 1
        # integration window of the new phase must cover the whole incoming
        # burst: each delivery costs ~40 fabric cycles on the dendrite scan;
        # several parcels per phase means 200 is the honest minimum
        dut.integrate_open.value = 1
        for _ in range(200):
            await FallingEdge(dut.clk)
        dut.integrate_open.value = 0

    async def quiet(c):
        for _ in range(c):
            await FallingEdge(dut.clk)

    # [lone A] settle, ticks x2; [lone B] settle, ticks x2; [pair] ticks x2;
    # [re-pair] ticks x3 — same phases as demo_net.run_demo_script
    plan = ("A", "T", "T", "B", "T", "T", "A", "B", "T", "T", "A", "B", "T", "T", "T")
    for step in plan:
        if step == "A":
            await soc_stim(0, 120)
        elif step == "B":
            await soc_stim(1, 120)
        else:
            await soc_tick()
        await quiet(30)

    await quiet(120)
    monitor.cancel()

    if os.environ.get("SOC_TEST_DEBUG") == "1":
        # observability readback: detector (tile2, n0) membrane + refractory
        dut.rb_tile.value = 2
        dut.rb_addr.value = 0
        dut.rb_req.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.rb_req.value = 0
        await FallingEdge(dut.clk)
        w = int(dut.rb_soma_data.value)
        print(f"DEBUG detector word: v={w & 0xFFFF} refr={(w >> 19) & 0xFF}")
        print("DEBUG chip_fires detail:", chip_fires)

    box = build_demo()
    run_demo_script(box)

    # artifact for the raster comparison: (tick, gid) json next to the log
    import json
    out_dir = Path(os.environ.get("SOC_ART_DIR", "."))
    with open(out_dir / "chip_fires.json", "w") as fh:
        json.dump({"chip": chip_fires,
                   "golden": [[t, g] for (t, g) in box.fire_log]}, fh)

    chip_gids_only = sorted(g for _t, g in chip_fires)
    gold_seq = sorted(g for _t, g in box.fire_log)
    print("chip fires  :", chip_gids_only)
    print("golden fires:", gold_seq)

    assert int(dut.mesh_overflow_any.value) == 0
    assert chip_gids_only.count(8) == gold_seq.count(8) == 2, "detector must fire twice"
    assert chip_gids_only.count(12) >= 1, "output must fire at least once"
    for gid in (0, 4):
        assert chip_gids_only.count(gid) == 3, f"electrode {gid} must fire 3x"
    # Phase-integrity: every golden (tick,gid) fire must appear in the chip
    # log at the same phase index or at most one later (bench-tick labeling
    # offset only — dynamics carry the same order). Anything else is physics.
    chip_pairs = set((t, g) for t, g in chip_fires)
    for t, g in box.fire_log:
        assert (t, g) in chip_pairs or (t + 1, g) in chip_pairs, \
            f"golden fire (t={t}, gid={g}) has no chip match within one phase"

    # review-sight commitment: exact multiset equality (not counts, not
    # within-one-phase slack). Currently the SoC shows the multiset gap that
    # this review found: the comparison reports it and fails the suite until
    # hardware matches exactly.
    chip_multiset = sorted(g for _t, g in chip_fires)
    gold_multiset = sorted(g for _t, g in box.fire_log)
    assert chip_multiset == gold_multiset, \
        f"EXACT equality required: chip={chip_multiset} golden={gold_multiset}"