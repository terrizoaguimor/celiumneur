# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adversarial I1 tests (written from the first review). These exist to fail
on the reviewed v1 RTL; the structural fix must turn them green on the SAME
stimulus. Red-then-green is the discipline.

Three seams:
  1. skid burst — eight spikes into one tile, one per cycle.
  2. dual fire during a dendrite scan — two potentiation candidates must pay.
  3. axon out burst — three rapid fires must emit three packets.
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

NOMEM = NeuronParams(theta=32767, leak_shift=15, refractory_ticks=0)


async def reset_tile(dut):
    dut.rst_n.value = 0
    for s in ("spk_valid", "tick", "cfg_en", "rb_soma_req"):
        getattr(dut, s).value = 0
    if hasattr(dut, "integrate_open"):
        dut.integrate_open.value = 1
    if hasattr(dut, "out_spk_ready"):
        dut.out_spk_ready.value = 1
    if hasattr(dut, "axon_masks"):
        # undriven axon map makes every egress mask X; the packet then fails
        # resolvability and the watcher records nothing. drive all-routes.
        dut.axon_masks.value = 0xFFFF
    if hasattr(dut, "spk_parity"):
        # head parity must differ from the tile's initial tick parity (0),
        # otherwise the fence gate holds every arrival (correct behavior
        # for a mid-phase packet; for the unit test we just want delivery).
        dut.spk_parity.value = 1
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    # post-reset S_INIT sweep must finish before bench programs (otherwise
    # wipes eat the parameters mid-write)
    for _ in range(200):
        if int(dut.soma.state.value) == 0:   # S_IDLE reached
            break
        await FallingEdge(dut.clk)
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def drive_spike(dut, gid):
    dut.spk_gid.value = gid
    dut.spk_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.spk_valid.value = 0


async def read_dend(dut, addr) -> int:
    dut.rb_dend_addr.value = addr
    await FallingEdge(dut.clk)
    return int(dut.rb_dend_rdata.value) & 0xFF


@cocotb.test()
async def adversarial_skid_burst_never_drops(dut):
    """Eight spikes, one per cycle. Count dendrite-busy rises: each completed
    pass is the only honest evidence a spike landed."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_tile(dut)

    for e, gid in enumerate((1, 2, 3, 4, 5, 6, 7, 8)):
        dut.cfg_addr.value = e
        dut.cfg_wdata.value = (1 << 20) | (gid << 10) | (0 << 8) | 120
        dut.cfg_en.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    dut.cfg_en.value = 0

    for gid in (1, 2, 3, 4, 5, 6, 7, 8):
        await drive_spike(dut, gid)

    # dendrite passes mark dend_busy high; count rises over the drain window
    passes = 0
    prev = 0
    for _ in range(1600):
        await FallingEdge(dut.clk)
        busy = int(dut.dend_busy.value)
        if busy == 1 and prev == 0:
            passes += 1
        prev = busy
    assert passes == 8, f"I1 adversarial: {passes}/8 spikes got a dendrite pass"


@cocotb.test()
async def adversarial_dual_fire_never_overwrites(dut):
    """Two postsynaptic fires during one scan paid by two potentiation
    candidates, with delivery/fire counts observed inline (no blind spots)."""
    deliveries = [0]
    fires = []

    async def watch():
        while True:
            await FallingEdge(dut.clk)
            if int(dut.dendrite.ev_valid.value) if hasattr(dut, "dendrite") else 0:
                deliveries[0] += 1
            if int(dut.soma_fire_valid.value) if hasattr(dut, "soma_fire_valid") else False:
                fires.append(int(dut.soma_fire_neuron.value))

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(watch())
    await reset_tile(dut)

    dut.soma.nram[0].value = pack_word(NeuronParams(theta=200, leak_shift=15, refractory_ticks=0))
    dut.soma.nram[1].value = pack_word(NeuronParams(theta=200, leak_shift=15, refractory_ticks=0))
    dut.soma.nram[2].value = pack_word(NOMEM)
    dut.soma.nram[3].value = pack_word(NOMEM)
    # carriers + payment candidates on two posts
    for e, (gid, post, w) in enumerate(((1, 0, 120), (2, 1, 120),
                                        (3, 0, 10), (4, 1, 10))):
        dut.cfg_addr.value = e
        dut.cfg_wdata.value = (1 << 20) | (gid << 10) | (post << 8) | w
        dut.cfg_en.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    dut.cfg_en.value = 0

    # two carriers per post; both candidates register arrivals
    await drive_spike(dut, 1)
    await drive_spike(dut, 2)
    await drive_spike(dut, 3)
    await drive_spike(dut, 4)
    await drive_spike(dut, 1)
    await drive_spike(dut, 2)
    for _ in range(900):
        await FallingEdge(dut.clk)

    if os.environ.get("ADV_DEBUG") == "1":
        print(
            f"DEBUG dual: deliveries={deliveries[0]} fires={fires} "
            f"ledger2tick={int(dut.dendrite.ledger_tick[2].value)} "
            f"ledger3tick={int(dut.dendrite.ledger_tick[3].value)} "
            f"tick_cnt={int(dut.dendrite.tick_cnt.value)}")
    w3 = await read_dend(dut, 2)
    w4 = await read_dend(dut, 3)
    if os.environ.get("ADV_DEBUG") == "1":
        print(f"DEBUG dual: w3={w3} w4={w4}")
    assert (w3, w4) == (11, 11), f"dual-fire overwrite: paid {(w3, w4)}, expected (11, 11)"


@cocotb.test()
async def adversarial_axon_burst_never_drops_neurons(dut):
    """Three rapid fires; three axon packets out. Single register overwrite
    drops mid-flight fires."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_tile(dut)

    for n in range(4):
        dut.soma.nram[n].value = pack_word(NeuronParams(theta=10, leak_shift=15, refractory_ticks=0))

    seen = []

    async def axon_watch():
        """Capture every packet presentation on the RISING edge — the falling
        edge proved blind for the middle packet."""
        while True:
            await RisingEdge(dut.clk)
            if int(dut.soma.fire_valid.value):
                if os.environ.get("ADV_DEBUG") == "1":
                    print(f"  watch fire n={int(dut.soma.fire_neuron.value)}")
            if int(dut.out_spk_valid.value):
                pkt_arr = dut.out_spk_pkt.value
                if pkt_arr.is_resolvable:
                    gid = int(pkt_arr) & 0x3FF
                    if gid not in seen:
                        seen.append(gid)
    cocotb.start_soon(axon_watch())

    # strobe pacing: a soma event costs ~3 fabric cycles (S_IDLE->EV_RD->
    # EV_AP); a strobe arriving mid-event is silently dropped by design, and
    # this test targets the axon burst path, not stim backpressure — so space
    # the strobes. The fires still overlap in the flight window (takes are
    # scan-latency away), which is the burst this test exists to protect.
    for n in (0, 1, 2):
        dut.stim_neuron.value = n
        dut.stim_weight.value = 60
        dut.stim_valid.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.stim_valid.value = 0
        for _ in range(3):
            await FallingEdge(dut.clk)   # let the soma finish the event
    for _ in range(400):             # drain window (same as probe)
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if int(dut.out_spk_valid.value):
            pkt_arr = dut.out_spk_pkt.value
            if pkt_arr.is_resolvable:
                g = int(pkt_arr) & 0x3FF
                if g not in seen:
                    seen.append(g)

    if os.environ.get("ADV_DEBUG") == "1":
        print("DEBUG axon seen:", seen)
    assert sorted(seen) == [0, 1, 2], f"axon burst: seen {seen}"
