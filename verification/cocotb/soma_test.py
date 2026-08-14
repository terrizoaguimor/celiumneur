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
    dut.cfg_en.value = 0
    dut.fire_ready.value = 1
    dut.phase_parity.value = 0
    dut.phase_tick.value = 0
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


async def submit_when_ready(dut, valid_name: str, ready_name: str) -> None:
    """Submit one transaction across legacy pulse or valid/ready interfaces."""
    valid = getattr(dut, valid_name)
    valid.value = 0
    await FallingEdge(dut.clk)
    valid.value = 1
    while True:
        ready = (int(getattr(dut, ready_name).value)
                 if hasattr(dut, ready_name) else 1)
        await RisingEdge(dut.clk)
        if ready:
            break
        await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    valid.value = 0


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


@cocotb.test()
async def soma_fire_channel_holds_payload_until_ready(dut):
    """A firing result is a valid/ready transaction, never a pulse."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_and_program(dut)

    dut.nram[0].value = pack_word(
        NeuronParams(theta=10, leak_shift=15, refractory_ticks=0,
                     subtractive_reset=True))
    dut.fire_ready.value = 0
    dut.phase_parity.value = 1

    dut.ev_neuron.value = 0
    dut.ev_weight.value = 60
    dut.ev_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.ev_valid.value = 0

    for _ in range(10):
        await FallingEdge(dut.clk)
        if int(dut.fire_valid.value):
            break

    assert int(dut.fire_valid.value) == 1, "fire transaction never appeared"
    expected_payload = (
        int(dut.fire_neuron.value), int(dut.fire_parity.value),
        int(dut.fire_tick.value))

    for _ in range(16):
        await FallingEdge(dut.clk)
        assert int(dut.fire_valid.value) == 1, "fire valid dropped before ready"
        assert (int(dut.fire_neuron.value), int(dut.fire_parity.value),
                int(dut.fire_tick.value)) == expected_payload
        assert int(dut.ev_ready.value) == 0, "soma accepted work with a pending fire"

    dut.fire_ready.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.fire_valid.value) == 0
    assert int(dut.ev_ready.value) == 1


@cocotb.test()
async def soma_tick_submitted_while_busy_is_not_lost(dut):
    """A tick requested during an event eventually performs exactly one sweep."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_and_program(dut)

    stable = NeuronParams(theta=32767, leak_shift=1, refractory_ticks=0)
    dut.nram[0].value = pack_word(stable, v=8)

    # Occupy the datapath with a zero-weight event, then submit the tick while
    # that event is still in flight. Legacy pulse-only RTL silently loses it.
    dut.ev_neuron.value = 0
    dut.ev_weight.value = 0
    dut.ev_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.ev_valid.value = 0

    await submit_when_ready(dut, "tick_req", "tick_ready")
    for _ in range(100):
        await FallingEdge(dut.clk)
        if int(dut.busy.value) == 0 if hasattr(dut, "busy") else int(dut.state.value) == 0:
            break

    final_v = int(dut.nram[0].value) & 0xFFFF
    assert final_v == 4, f"busy tick was lost: expected V=4, got V={final_v}"


@cocotb.test()
async def soma_configuration_submitted_while_busy_is_not_lost(dut):
    """Configuration has an observable acceptance boundary."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_and_program(dut)

    dut.ev_neuron.value = 0
    dut.ev_weight.value = 0
    dut.ev_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.ev_valid.value = 0

    replacement = pack_word(
        NeuronParams(theta=777, leak_shift=4, refractory_ticks=9,
                     subtractive_reset=True),
        v=123)
    dut.cfg_addr.value = 1
    dut.cfg_wdata.value = replacement
    await submit_when_ready(dut, "cfg_en", "cfg_ready")

    for _ in range(20):
        await FallingEdge(dut.clk)
        if int(dut.state.value) == 0:
            break
    assert int(dut.nram[1].value) == replacement, "busy config write was lost"


@cocotb.test()
async def soma_readback_remains_available_during_tick_sweep(dut):
    """Readback is an independent observation port, not an idle-only command."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_and_program(dut)

    params = NeuronParams(theta=32767, leak_shift=1, refractory_ticks=0)
    for neuron in range(NEURONS):
        dut.nram[neuron].value = pack_word(params, v=8)

    await submit_when_ready(dut, "tick_req", "tick_ready")
    for _ in range(20):
        await FallingEdge(dut.clk)
        if int(dut.sweep_active.value):
            break
    assert int(dut.sweep_active.value) == 1

    dut.rb_req.value = 1
    for address in range(NEURONS):
        dut.rb_addr.value = address
        await FallingEdge(dut.clk)
        assert int(dut.rb_ready.value) == 1, (
            f"readback rejected address {address} during sweep")
        assert int(dut.rb_valid.value) == 1
        assert dut.rb_data.value.is_resolvable
    dut.rb_req.value = 0

    for _ in range(100):
        await FallingEdge(dut.clk)
        if int(dut.sweep_active.value) == 0:
            break
    else:
        raise AssertionError("readback stalled the tick sweep")

    for neuron in range(NEURONS):
        assert (int(dut.nram[neuron].value) & 0xFFFF) == 4
