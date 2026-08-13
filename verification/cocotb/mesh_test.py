# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: hyphae_mesh_2x2 (full fabric) vs golden HyphaeMesh.

End-state transactional parity on every delivered packet, per core. The
bench injects only against PE credits (the two-party contract) and audits
overflow_any every cycle. Dynamics-first: real storms across the mesh, not
quiescent checks.

Drive mechanics: one injection per cycle at most, valid held for exactly one
rising edge; every cycle the bench honors credit returns and captures all
registered PE egress.
"""

import random
import sys
from collections import defaultdict, deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "golden"))
from hyphae import HyphaeMesh, LINK_FIFO_DEPTH, Packet, TYPE_SPIKE  # noqa: E402

CORES = 4


def pe_slice(vec: int, core: int) -> int:
    return (vec >> (core * 32)) & 0xFFFFFFFF


def encode(type_code: int, mask: int, body: int) -> int:
    return (type_code << 28) | (mask << 20) | body


async def reset_mesh(dut):
    dut.rst_n.value = 0
    dut.pe_in_valid.value = 0
    dut.pe_in_data.value = 0
    if hasattr(dut, "pe_out_ready"):
        dut.pe_out_ready.value = 0b1111   # all sinks ready: pulse semantics
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def mesh_cycle(dut, credits, collected, plan):
    """One disciplined cycle: returns honored, egress captured, I1 audited,
    then exactly one pending injection if its credit allows."""
    credits_now = int(dut.pe_feeder_ret.value)
    for core in range(CORES):
        if credits_now & (1 << core):
            credits[core] += 1

    out_valid = int(dut.pe_out_valid.value)
    out_data = int(dut.pe_out_data.value)
    for core in range(CORES):
        if out_valid & (1 << core):
            collected[core].append(pe_slice(out_data, core))

    assert int(dut.overflow_any.value) == 0, "I1 witness: link overflow in mesh"

    dut.pe_in_valid.value = 0
    if plan:
        core, word = plan[0]
        if credits[core] > 0:
            credits[core] -= 1
            plan.popleft()
            dut.pe_in_data.value = word << (core * 32)
            dut.pe_in_valid.value = 1 << core
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.pe_in_valid.value = 0


def golden_words_for(mesh, core):
    return sorted(encode(p.type_code, p.dst_mask, p.body)
                  for p in mesh.deliveries_at(core))


@cocotb.test()
async def mesh_directed_routes_match_golden(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_mesh(dut)
    golden = HyphaeMesh()
    collected = defaultdict(list)
    credits = [LINK_FIFO_DEPTH] * CORES

    plan = deque([
        (0, encode(TYPE_SPIKE, 0b1000, 0x11111)),   # corner to far core
        (3, encode(TYPE_SPIKE, 0b0001, 0x22222)),   # far core back
        (0, encode(TYPE_SPIKE, 0b1111, 0x33333)),   # corner to all
        (2, encode(TYPE_SPIKE, 0b0101, 0x44444)),   # col: {0,2} only
    ])
    for core, word in plan:
        golden.inject(core, Packet(TYPE_SPIKE, (word >> 20) & 0xF, word & 0xFFFFF))

    while plan:
        await mesh_cycle(dut, credits, collected, plan)
    for _ in range(300):
        await mesh_cycle(dut, credits, collected, plan)
    golden.run_until_idle(cycle_cap=2_000)

    for core in range(CORES):
        assert sorted(collected[core]) == golden_words_for(golden, core), \
            f"core {core}: fabric diverges from golden mesh"


@cocotb.test()
async def mesh_storm_random_traffic_matches_golden(dut):
    random.seed(90210)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_mesh(dut)
    golden = HyphaeMesh()
    collected = defaultdict(list)
    credits = [LINK_FIFO_DEPTH] * CORES

    plan = deque()
    for seq in range(64):
        core = random.randrange(CORES)
        mask = random.randint(1, 0xF)
        body = (seq << 12) | 0xABC
        plan.append((core, encode(TYPE_SPIKE, mask, body)))
        golden.inject(core, Packet(TYPE_SPIKE, mask, body))

    while plan:
        await mesh_cycle(dut, credits, collected, plan)
    for _ in range(400):
        await mesh_cycle(dut, credits, collected, plan)
    golden.run_until_idle(cycle_cap=5_000)

    for core in range(CORES):
        assert sorted(collected[core]) == golden_words_for(golden, core), \
            f"core {core}: storm deliveries diverge ({len(collected[core])} vs {len(golden_words_for(golden, core))})"
