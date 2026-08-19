# SPDX-License-Identifier: Apache-2.0
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
from demo_net import (  # noqa: E402
    DETECTOR,
    ELECTRODE_A,
    ELECTRODE_B,
    OUTPUT,
    build_demo,
    run_demo_script,
)
from golden_net import NEURONS_PER_CORE  # noqa: E402

ELECTRODE_P = NeuronParams(theta=100, leak_shift=1, refractory_ticks=0)
DETECTOR_P = NeuronParams(theta=200, leak_shift=1, refractory_ticks=0)
OUTPUT_P = NeuronParams(theta=100, leak_shift=1, refractory_ticks=4)
TYPE_CONFIG = 0x2


def config_packets(dst_mask: int, space: int, addr: int, data: int) -> list[int]:
    """Encode one ordered five-flit Hyphae configuration transaction."""
    header = ((space & 0x3) << 15) | ((addr & 0xFF) << 7)
    bodies = [header]
    for fragment in range(4):
        chunk = (data >> (16 * fragment)) & 0xFFFF
        bodies.append(((fragment + 1) << 17) | (chunk << 1))
    return [
        (TYPE_CONFIG << 28) | ((dst_mask & 0xF) << 20) | body
        for body in bodies
    ]


async def send_host_packet(dut, packet: int) -> None:
    dut.host_packet.value = packet
    dut.host_valid.value = 1
    while not int(dut.host_ready.value):
        await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.host_valid.value = 0


async def configure_tiles(dut, dst_mask: int, space: int,
                          addr: int, data: int) -> None:
    for packet in config_packets(dst_mask, space, addr, data):
        await send_host_packet(dut, packet)


async def reset_soc(dut):
    dut.rst_n.value = 0
    for s in ("tick", "stim_valid", "host_valid", "rb_req"):
        getattr(dut, s).value = 0
    dut.host_packet.value = 0
    dut.stim_tile.value = 0
    dut.stim_neuron.value = 0
    dut.stim_weight.value = 0
    dut.rb_tile.value = 0
    dut.rb_addr.value = 0
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
                    if int(tile.soma.fire_ready.value):
                        chip_fires.append(
                            (tick_box[0], core * NEURONS_PER_CORE
                             + int(tile.soma.fire_neuron.value))
                        )
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
        2: (DETECTOR_P, [(ELECTRODE_A, 0, 120),
                         (ELECTRODE_B, 0, 120)]),
        3: (OUTPUT_P, [(DETECTOR, 0, 120)]),
    }
    for tile_id, (params, entries) in specs.items():
        tile = getattr(dut, f"t{tile_id}")
        tile.soma.nram[0].value = pack_word(params)
        for addr, (pre, post, w) in enumerate(entries):
            data = (1 << 26) | ((pre & 0x3FF) << 16) | \
                   ((post & 0xFF) << 8) | (w & 0xFF)
            await configure_tiles(dut, 1 << tile_id, 0, addr, data)

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
        while not int(dut.tick_ready.value):
            await FallingEdge(dut.clk)
        dut.tick.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.tick.value = 0
        tick_box[0] += 1
        # Keep the phase open until every queued tick and tile transaction is
        # physically quiescent. At the real 256-neuron scale a sweep itself
        # takes hundreds of clocks, so fixed four-neuron delays are invalid.
        dut.integrate_open.value = 1
        for _ in range(6000):
            await FallingEdge(dut.clk)
            engines_quiet = all(
                int(getattr(dut, f"t{i}").dend_busy.value) == 0
                and int(getattr(dut, f"t{i}").soma_busy.value) == 0
                and int(getattr(dut, f"t{i}").soma_sweep_active.value) == 0
                and int(getattr(dut, f"t{i}").stimq_empty.value) == 1
                and int(getattr(dut, f"t{i}").fireq_empty.value) == 1
                and int(getattr(dut, f"t{i}").outq_empty.value) == 1
                and (
                    int(getattr(dut, f"t{i}").inq_empty.value) == 1
                    or int(getattr(dut, f"t{i}").head_parity.value)
                    == int(getattr(dut, f"t{i}").tick_parity.value)
                )
                for i in range(4)
            )
            if (int(dut.tickq_empty.value) == 1 and engines_quiet
                    and int(dut.pe_out_valid.value) == 0):
                break
        else:
            raise AssertionError("SoC did not quiesce after tick")
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
    assert chip_gids_only.count(DETECTOR) == gold_seq.count(DETECTOR) == 2, \
        "detector must fire twice"
    assert chip_gids_only.count(OUTPUT) >= 1, "output must fire at least once"
    for gid in (ELECTRODE_A, ELECTRODE_B):
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


@cocotb.test()
async def soc_tick_queue_preserves_back_to_back_ticks(dut):
    """Global ticks accepted during a sweep dispatch once to every tile."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_soc(dut)

    params = NeuronParams(theta=32767, leak_shift=1, refractory_ticks=0)
    for core in range(4):
        tile = getattr(dut, f"t{core}")
        tile.soma.nram[0].value = pack_word(params, v=8)

    # Three consecutive valid pulses are accepted by the global queue even
    # though the first dispatch immediately makes every SomaCore busy.
    for _ in range(3):
        await FallingEdge(dut.clk)
        assert int(dut.tick_ready.value) == 1
        dut.tick.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.tick.value = 0

    assert any(int(getattr(dut, f"t{i}").tile_busy.value) for i in range(4))
    dut.rb_tile.value = 0
    dut.rb_addr.value = 0
    dut.rb_req.value = 1
    await FallingEdge(dut.clk)
    assert int(dut.rb_ready.value) == 1
    assert int(dut.rb_valid.value) == 1
    assert dut.rb_soma_data.value.is_resolvable
    dut.rb_req.value = 0

    for _ in range(5000):
        await FallingEdge(dut.clk)
        if (int(dut.tickq_empty.value) == 1
                and all(int(getattr(dut, f"t{i}").tile_busy.value) == 0
                        for i in range(4))):
            break
    else:
        raise AssertionError("queued ticks did not drain")

    for core in range(4):
        final_v = int(getattr(dut, f"t{core}").soma.nram[0].value) & 0xFFFF
        assert final_v == 1, f"tile {core}: expected three leaks to V=1, got {final_v}"
    assert int(dut.tick_overflow_wit.value) == 0


@cocotb.test()
async def soc_exposes_all_1024_neurons_and_gid_1023(dut):
    """The published 4×256 scale is implemented, not merely documented."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_soc(dut)

    for core in range(4):
        assert int(getattr(dut, f"t{core}").soma.NEURONS.value) == 256

    # Configuration space 1 = Soma, 2 = axon route table.
    neuron_word = pack_word(
        NeuronParams(theta=10, leak_shift=15, refractory_ticks=0,
                     subtractive_reset=True))
    await configure_tiles(dut, 1 << 3, 1, 255, neuron_word)
    await configure_tiles(dut, 1 << 3, 2, 255, 1)

    # host_ready acknowledges mesh injection, not remote commit. Wait on the
    # endpoint-owned state before using the newly configured route.
    for _ in range(2000):
        await FallingEdge(dut.clk)
        if int(dut.t3.axon_table[255].value) == 1:
            break
    else:
        raise AssertionError("axon configuration never committed")

    dut.stim_tile.value = 3
    dut.stim_neuron.value = 255
    dut.stim_weight.value = 60
    dut.stim_valid.value = 1
    while not int(dut.stim_ready.value):
        await FallingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.stim_valid.value = 0

    for _ in range(2000):
        await FallingEdge(dut.clk)
        if int(dut.t3.out_spk_valid.value):
            packet = int(dut.t3.out_spk_pkt.value)
            assert (packet & 0x3FF) == 1023
            assert ((packet >> 20) & 0xF) == 1, \
                "configured axon mask was not applied to neuron 1023"
            break
    else:
        raise AssertionError("neuron 1023 never produced an axon packet")

    assert int(dut.config_protocol_error.value) == 0


@cocotb.test()
async def host_config_packet_multicast_reaches_every_tile(dut):
    """One Hyphae transaction is branch-replicated to all four endpoints."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_soc(dut)

    word = pack_word(
        NeuronParams(theta=1234, leak_shift=7, refractory_ticks=9,
                     subtractive_reset=False),
        v=-321,
    )
    await configure_tiles(dut, 0xF, 1, 200, word)

    for _ in range(2000):
        await FallingEdge(dut.clk)
        if all(int(getattr(dut, f"t{i}").soma.nram[200].value) == word
               for i in range(4)):
            break
    else:
        raise AssertionError("multicast configuration did not commit everywhere")

    assert int(dut.config_protocol_error.value) == 0
    assert int(dut.mesh_overflow_any.value) == 0
