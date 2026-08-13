# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: soma_core (4-neuron config) vs the golden Soma model.

Parity contract (SPEC §3 v1): phase-mode operation — the bench issues a tick,
waits for the sweep to finish, only then issues more events. The golden side
applies the same operation order. Verdicts:
  1. bit-exact final neuron words via readback (state + params intact);
  2. identical fire neuron-id sequences (order-sensitive dynamics, I8).

Timing discipline: stimulus on falling edges; one free-running monitor task
owns ALL fire-strobe capture (single source, zero duplicates).
"""

import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "golden"))
from soma import NeuronParams, Soma, saturate_vmem  # noqa: E402

NEURONS = 4

# Heterogeneous per-neuron configs (I7 exercised on purpose).
NEURON_CONFIGS = [
    NeuronParams(theta=100, leak_shift=1, refractory_ticks=3, subtractive_reset=True),
    NeuronParams(theta=64,  leak_shift=3, refractory_ticks=0, subtractive_reset=False),
    NeuronParams(theta=300, leak_shift=15, refractory_ticks=7, subtractive_reset=True),
    NeuronParams(theta=1,   leak_shift=1, refractory_ticks=1, subtractive_reset=True),
]


def pack_word(p: NeuronParams, v: int = 0, refr_cnt: int = 0) -> int:
    v = saturate_vmem(v)
    word = (p.theta & 0xFFFF) << 48
    word |= (1 if p.subtractive_reset else 0) << 47
    word |= (p.leak_shift & 0xF) << 43
    word |= (p.refractory_ticks & 0xFF) << 35
    word |= (refr_cnt & 0xFF) << 19
    word |= v & 0xFFFF
    return word


async def reset_and_program(dut):
    dut.rst_n.value = 0
    dut.ev_valid.value = 0
    dut.tick_req.value = 0
    dut.rb_req.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    # S_INIT walks all neurons to zero before the engine idles; the bench must
    # wait it out — programming then happens against defined memory.
    for _ in range(100):
        if int(dut.state.value) != 5:  # S_INIT
            break
        await FallingEdge(dut.clk)
    for idx, cfg in enumerate(NEURON_CONFIGS):
        dut.nram[idx].value = pack_word(cfg)
    await FallingEdge(dut.clk)


async def drive_event(dut, neuron, weight):
    dut.ev_neuron.value = neuron
    dut.ev_weight.value = weight & 0xFF
    dut.ev_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.ev_valid.value = 0
    while int(dut.ev_ready.value) == 0:
        await FallingEdge(dut.clk)


async def drive_tick(dut):
    dut.tick_req.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.tick_req.value = 0
    while int(dut.sweep_active.value) == 0:
        await FallingEdge(dut.clk)
    while int(dut.sweep_active.value) == 1:
        await FallingEdge(dut.clk)


async def readback_all(dut):
    words = []
    for idx in range(NEURONS):
        dut.rb_addr.value = idx
        dut.rb_req.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.rb_req.value = 0
        await FallingEdge(dut.clk)
        words.append(int(dut.rb_data.value))
    return words


@cocotb.test()
async def soma_matches_golden_under_mixed_traffic(dut):
    random.seed(316)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_and_program(dut)

    dut_fires = []

    async def fire_monitor():
        while True:
            await FallingEdge(dut.clk)
            if int(dut.fire_valid.value):
                dut_fires.append(int(dut.fire_neuron.value))

    monitor = cocotb.start_soon(fire_monitor())

    somas = [Soma(cfg) for cfg in NEURON_CONFIGS]
    golden_fires = []
    ops = []
    for _ in range(120):
        if random.random() < 0.7:
            ops.append(("ev", random.randrange(NEURONS), random.randint(-128, 127)))
        else:
            ops.append(("tick",))

    for op in ops:
        if op[0] == "ev":
            _, neuron, weight = op
            if somas[neuron].apply_synaptic_input(weight):
                golden_fires.append(neuron)
            await drive_event(dut, neuron, weight)
            for _ in range(2):  # let the event's strobe land
                await FallingEdge(dut.clk)
        else:
            for idx, soma in enumerate(somas):
                if soma.advance_time():
                    golden_fires.append(idx)
            await drive_tick(dut)

    monitor.cancel()
    assert dut_fires == golden_fires, \
        f"fire sequence diverges: dut={dut_fires} golden={golden_fires}"

    dut_words = await readback_all(dut)
    for idx, (word, soma) in enumerate(zip(dut_words, somas)):
        golden_word = pack_word(soma.params, soma.v, soma.refractory_countdown)
        assert word == golden_word, \
            f"neuron {idx}: final state diverges dut={word:016x} golden={golden_word:016x}"
