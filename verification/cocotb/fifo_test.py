# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: hypha_link_fifo vs Python deque oracle.

Timing discipline (applies to all CeliumNeUR benches): stimulus is driven on
the falling edge and DUT state is sampled after it, so reads race neither
the NBA update region nor the next setup. Never sample registered outputs
straight after RisingEdge.

Dynamics-first: the FIFO is filled to full, drained to empty, wrapped many
times, and hit with simultaneous push+pop; head/flags are compared against
the oracle every cycle. The overflow witness must never assert.
"""

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

DEPTH = 4
WIDTH_MASK = (1 << 32) - 1


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.push.value = 0
    dut.pop.value = 0
    dut.din.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def assert_flags(dut, oracle):
    assert int(dut.empty.value) == (1 if not oracle else 0), "empty mismatch"
    assert int(dut.full.value) == (1 if len(oracle) == DEPTH else 0), "full mismatch"
    assert int(dut.overflow.value) == 0, "overflow witness asserted"


@cocotb.test()
async def fifo_directed_boundaries(dut):
    """Fill-to-full, guarded push-at-full, drain-to-empty, head tracks FWFT."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    oracle = deque()
    await reset_dut(dut)

    for value in (0x11, 0x22, 0x33, 0x44):
        dut.push.value = 1
        dut.din.value = value
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        oracle.append(value)
        assert_flags(dut, oracle)
    dut.push.value = 0
    assert int(dut.full.value) == 1

    # hostile: push while full must be gated by the guard
    before = int(dut.dout.value)
    dut.push.value = 1
    dut.din.value = 0xEE
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.push.value = 0
    assert int(dut.dout.value) == before, "guarded push corrupted the head"
    assert int(dut.overflow.value) == 1, "guard breach must raise the witness"
    # witness is sticky by design; reset to re-arm for what follows
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    oracle.clear()

    for _ in range(DEPTH * 3):  # wrap pointers several times over
        value = (0xA5 << 8) | len(oracle)
        dut.push.value = 1
        dut.din.value = value
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        oracle.append(value)
        dut.push.value = 0
        assert int(dut.dout.value) == oracle[0]
        dut.pop.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        oracle.popleft()
        dut.pop.value = 0
        assert_flags(dut, oracle)


@cocotb.test()
async def fifo_random_stress(dut):
    """Random push/pop traffic, 2000 cycles, guard-respecting stimulus."""
    random.seed(20260812)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    oracle = deque()
    await reset_dut(dut)

    for cycle in range(2000):
        value = random.randint(0, WIDTH_MASK)
        pushing = random.random() < 0.6 and len(oracle) < DEPTH
        popping = random.random() < 0.5 and bool(oracle)
        dut.push.value = 1 if pushing else 0
        dut.pop.value = 1 if popping else 0
        dut.din.value = value
        if oracle:
            assert int(dut.dout.value) == oracle[0], f"head mismatch @cycle {cycle}"
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if pushing:
            oracle.append(value)
        if popping:
            oracle.popleft()
        assert_flags(dut, oracle)
