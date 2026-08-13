# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: hypha_router (corner core (0,0)) vs golden RouterModel.

Bench architecture (third and final): SYNCHRONOUS CYCLE LEDGER. Exactly one
coroutine may wait on clock edges — everything else speaks through
`FabricProbe.step(drives)`, which performs one full, deterministic cycle:

    1. apply testbench drives (input valids/data) + credit-return pulses
    2. RisingEdge   — the DUT consumes pushes/returns/credits at this posedge
    3. deassert one-cycle strobes
    4. FallingEdge  — capture registered egress (always inside the pulse
                      window), legality witnesses, shadow pops, tick++

The flaky first two attempts both broke this rule (capture cadence offset
by one; two coroutines sharing edge domain with scheduler-dependent
interleaving). A bench race is not a DUT proof: that is written plainly here
so the next reader has no chance to relearn it by accident.

Parity vs golden RouterModel is end-state transactional (ideal-sink drains).
Legality witnesses run every cycle inside step(); the overflow witness is
asserted where the architecture allows it to appear at all.
"""

import os
import random
import sys
from collections import defaultdict, deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "golden"))
from hyphae import (  # noqa: E402
    FULL_MASK,
    LINK_FIFO_DEPTH,
    Packet,
    RouterModel,
    TYPE_SPIKE,
)

CREDIT_BIT = {"E": 0, "N": 2}  # indices in credit_ret_i = {S,N,W,E}
BOUND_PORTS = ("E", "N")
INPUT_SIG = {
    "PE": ("in_pe_data", "in_pe_valid"),
    "E": ("in_e_data", "in_e_valid"),
    "N": ("in_n_data", "in_n_valid"),
}


def packet_word(type_code, dst_mask, body):
    return (type_code << 28) | (dst_mask << 20) | body


class FabricProbe:
    """Sole owner of clock cadence: drives inputs + credits, captures all
    outputs, keeps the shadow link books (I1 witness + out-credit returns)."""

    def __init__(self, dut, pop_every_n: int = 1):
        self.dut = dut
        self.shadow = {p: deque() for p in BOUND_PORTS}
        self.egress = defaultdict(list)       # port -> [words]
        self.timeline = []                    # (tick, port, word)
        self.delivered_pe = []
        self.tick = 0
        self.pop_every_n = pop_every_n        # >1 emulates a slow neighbor

    async def step(self, drives=None):
        """One deterministic cycle. drives: {port: word} for this cycle."""
        drives = drives or {}
        dut = self.dut

        ret = 0
        for port in BOUND_PORTS:
            if self.shadow[port] and (self.tick % self.pop_every_n) == 0:
                self.shadow[port].popleft()
                ret |= 1 << CREDIT_BIT[port]
        dut.credit_ret_i.value = ret

        for port, word in drives.items():
            data_sig, valid_sig = INPUT_SIG[port]
            getattr(dut, data_sig).value = word
            getattr(dut, valid_sig).value = 1

        await RisingEdge(dut.clk)
        for port in drives:
            getattr(dut, INPUT_SIG[port][1]).value = 0
        await FallingEdge(dut.clk)
        dut.credit_ret_i.value = 0

        self._capture()
        self.tick += 1

    def _capture(self):
        dut = self.dut
        if int(dut.out_pe_valid.value):
            word = int(dut.out_pe_data.value)
            self.delivered_pe.append(word)
            self.egress["PE"].append(word)
            self.timeline.append((self.tick, "PE", word))
        for port in BOUND_PORTS:
            valid = getattr(dut, f"out_{port.lower()}_valid")
            data = getattr(dut, f"out_{port.lower()}_data")
            if int(valid.value):
                if len(self.shadow[port]) >= LINK_FIFO_DEPTH:
                    raise AssertionError(f"I1 violated: push into full shadow {port}")
                word = int(data.value)
                self.shadow[port].append(word)
                self.egress[port].append(word)
                self.timeline.append((self.tick, port, word))
                if os.environ.get("ROUTER_PROBE_EGRESS") == "1":
                    print(f"    cap tick={self.tick} port={port} word=0x{word & 0xFFF:03x}")
        self._witness_legality()

    def _witness_legality(self):
        dut = self.dut
        if int(dut.out_n_valid.value):
            n_mask = (int(dut.out_n_data.value) >> 20) & 0xF
            assert n_mask & ~0b0101 == 0, f"N off-column mask {n_mask:#06b}"
        assert int(dut.out_s_valid.value) == 0, "S egress at corner (0,0)"
        if int(dut.out_e_valid.value):
            e_mask = (int(dut.out_e_data.value) >> 20) & 0xF
            assert e_mask & ~0b1010 == 0, f"E wrong-x mask {e_mask:#06b}"


async def reset_dut(dut):
    dut.rst_n.value = 0
    for _d, v in INPUT_SIG.values():
        getattr(dut, v).value = 0
    dut.credit_ret_i.value = 0
    if hasattr(dut, "pe_out_ready"):
        dut.pe_out_ready.value = 1   # bench sinks accept immediately (pulses)
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def drain_golden_ideal_sink(router):
    for _ in range(10_000):
        if all(not queue for queue in router.input_queues.values()):
            return
        for port in router.credits:
            router.credits[port] = LINK_FIFO_DEPTH
        router.service_one()
    raise AssertionError("golden router did not drain")


@cocotb.test()
async def router_corner_matches_golden(dut):
    random.seed(77)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    probe = FabricProbe(dut)
    golden = RouterModel(core=0, port_neighbors={"E": 1, "N": 2})
    await reset_dut(dut)

    packets = [
        ("PE", packet_word(TYPE_SPIKE, 0b0001, 0x111)),
        ("PE", packet_word(TYPE_SPIKE, 0b0010, 0x222)),
        ("PE", packet_word(TYPE_SPIKE, 0b0100, 0x333)),
        ("PE", packet_word(TYPE_SPIKE, FULL_MASK, 0x444)),
        ("E", packet_word(TYPE_SPIKE, 0b0001, 0x555)),
        ("E", packet_word(TYPE_SPIKE, 0b0100, 0x666)),
    ]
    packets += [("PE", packet_word(TYPE_SPIKE, random.randint(1, FULL_MASK), i))
                for i in range(40)]

    for port, word in packets:
        mask, body = (word >> 20) & 0xF, word & 0xFFFFF
        if port == "E":
            golden.receive_from_link("E", Packet(TYPE_SPIKE, mask, body))
        else:
            golden.inject(Packet(TYPE_SPIKE, mask, body))
        await probe.step({port: word})
        await probe.step()

    for _ in range(300):
        await probe.step()

    assert int(dut.overflow_any.value) == 0
    drain_golden_ideal_sink(golden)
    golden_words = sorted((p.type_code << 28) | (p.dst_mask << 20) | p.body
                          for p in golden.delivered)
    assert sorted(probe.delivered_pe) == golden_words


@cocotb.test()
async def router_arbiter_rotation_witness(dut):
    """rr kill test, white-box by design (documented: control-plane witness):

    Both input channels are kept pregnant. Every cycle ends by peeking
    `rr_ptr`. With the rotate-past-winner arbiter, consecutive services must
    come from alternating pointers. With the follow-winner mutant the
    pointer FREEZES on the winner while it stays serviceable; the series
    here then contains a run of equal rr_ptr values longer than the number
    of FIFO service-empty windows, which the assertion bounds."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    probe = FabricProbe(dut)   # fast pops: credits always available
    await reset_dut(dut)

    per_class = 12
    stock = {"PE": deque(packet_word(TYPE_SPIKE, 0b0001, i) for i in range(per_class)),
             "E": deque(packet_word(TYPE_SPIKE, 0b0010, i) for i in range(per_class))}
    drive_sig = {"PE": ("in_pe_data", "in_pe_valid"), "E": ("in_e_data", "in_e_valid")}
    fifo_full_at = {"PE": lambda: int(dut.g_in_fifos[0].fifo.full.value),
                    "E": lambda: int(dut.g_in_fifos[1].fifo.full.value)}

    rr_series = []
    while (stock["PE"] or stock["E"]) and len(rr_series) < 200:
        drives = {}
        for port in ("PE", "E"):
            if stock[port] and not fifo_full_at[port]():
                drives[port] = stock[port].popleft()
        rr_now = int(dut.rr_ptr.value)
        await probe.step(drives)
        # service evidence this cycle = any egress just captured
        if probe.timeline and probe.timeline[-1][0] == probe.tick - 1:
            rr_series.append(rr_now)

    for _ in range(400):
        await probe.step()

    assert int(dut.overflow_any.value) == 0
    assert len(probe.delivered_pe) == per_class
    assert len(probe.egress["E"]) == per_class

    # the witness: no two consecutive services from the same rr value
    # while both channels were pregnant across them
    violations = sum(1 for a, b in zip(rr_series, rr_series[1:]) if a == b)
    if os.environ.get("ROUTER_FAIR_DEBUG") == "1":
        print("DEBUG rr_series:", rr_series)
    assert violations == 0, f"arbiter pointer repeated across {violations} consecutive services"


@cocotb.test()
async def router_fairness_delivery_completeness(dut):
    """Load-level sanity: 24 packets per class at protocol pace all arrive —
    completeness only (order policies live in the contention test)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    probe = FabricProbe(dut)
    await reset_dut(dut)
    per_class = 24
    stock_pe = deque(packet_word(TYPE_SPIKE, 0b0001, i) for i in range(per_class))
    stock_e = deque(packet_word(TYPE_SPIKE, 0b0010, 0x100 + i) for i in range(per_class))
    cycles = 0
    while (stock_pe or stock_e) and cycles < 1500:
        drives = {}
        if cycles % 3 == 0:
            if stock_pe:
                drives["PE"] = stock_pe.popleft()
            if stock_e:
                drives["E"] = stock_e.popleft()
        await probe.step(drives)
        cycles += 1
    for _ in range(500):
        await probe.step()
    assert len(probe.delivered_pe) == per_class
    assert len(probe.egress["E"]) == per_class
    assert int(dut.overflow_any.value) == 0
