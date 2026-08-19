# SPDX-License-Identifier: Apache-2.0
"""cocotb: hypha_sync_fifo (Cummings-style CDC cell, Invariant I3) with two
independent clocks vs a Python deque oracle.

Dynamics-first + CDC reality: push clock 10 ns, pop clock 7 ns (incommensurate
on purpose so pointer crossings land on every phase relation). Every item
popped must equal the oracle head in exact order; the transfer count at the
end must equal everything ever pushed minus what the queue still holds.
"""

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

TOTAL_ITEMS = 200


@cocotb.test()
async def sync_fifo_dual_clock_no_loss_no_reorder(dut):
    random.seed(4242)
    cocotb.start_soon(Clock(dut.push_clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.pop_clk, 7, unit="ns").start())

    dut.push_rst_n.value = 0
    dut.pop_rst_n.value = 0
    dut.push.value = 0
    dut.pop.value = 0
    dut.push_data.value = 0
    for _ in range(4):
        await FallingEdge(dut.push_clk)
        await FallingEdge(dut.pop_clk)
    dut.push_rst_n.value = 1
    dut.pop_rst_n.value = 1
    for _ in range(2):
        await FallingEdge(dut.push_clk)
        await FallingEdge(dut.pop_clk)

    oracle = deque()
    popped_log = []

    async def producer():
        for value in range(TOTAL_ITEMS):
            while int(dut.full.value) == 1:
                await FallingEdge(dut.push_clk)
            dut.push_data.value = value
            dut.push.value = 1
            await FallingEdge(dut.push_clk)
            dut.push.value = 0
            oracle.append(value)

    async def consumer():
        # FWFT discipline: the head is valid the whole !empty window, so log
        # it BEFORE strobing pop, then let one rising edge apply the pointer
        # advance. Logging after the strobe edges would read the NEXT item.
        while len(popped_log) < TOTAL_ITEMS:
            await FallingEdge(dut.pop_clk)
            if int(dut.empty.value) == 0:
                popped_log.append(int(dut.pop_data.value))
                dut.pop.value = 1
                await RisingEdge(dut.pop_clk)
                dut.pop.value = 0
            if random.random() < 0.2:  # bursty consumer: idle stretches
                for _ in range(random.randint(1, 4)):
                    await FallingEdge(dut.pop_clk)

    producer_task = cocotb.start_soon(producer())
    consumer_task = cocotb.start_soon(consumer())

    await cocotb.triggers.with_timeout(consumer_task, 3, "ms")

    assert len(popped_log) == TOTAL_ITEMS, \
        f"loss: {len(popped_log)}/{TOTAL_ITEMS} delivered"
    assert popped_log == list(range(TOTAL_ITEMS)), "reordering across the CDC cell"
