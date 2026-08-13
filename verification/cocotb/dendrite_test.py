# SPDX-License-Identifier: AGPL-3.0-or-later
"""cocotb: neuro_tile (soma_dendrite + soma_core) vs CoreReferee (Python).

The referee implements rule v1.2 with the single-slot ledger constraint the
RTL documents (latest arrival overwrites). Same op order --- phase-mode
benches (one spike or tick, then quiescence). Contract: final weight table,
soma state words, and fire log must match bit-for-bit.

Demo workload (mirrors golden/demo_plasticity.py): paired A+B drives, control
C alone. Expectation: A,B potentiate to the rail; C depresses.
"""

import sys
from collections import deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "golden"))
from plasticity import PairSTDP, WEIGHT_RAIL_HI, WEIGHT_RAIL_LO  # noqa: E402
from soma import NeuronParams, Soma  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from soma_test import pack_word  # noqa: E402

ENTRIES = 16
WINDOW = 3
# tile-local mapping: detector = local neuron 0
DETECTOR_LOCAL = 0
DETECTOR_PARAMS = NeuronParams(theta=200, leak_shift=1, refractory_ticks=0,
                               subtractive_reset=True)
GPIO_PARAMS = NeuronParams(theta=32767, leak_shift=15, refractory_ticks=0)


class CoreReferee:
    """Authoritative Python twin of soma_dendrite (single-slot ledger)."""

    def __init__(self):
        self.somas = [Soma(DETECTOR_PARAMS)] + [Soma(GPIO_PARAMS) for _ in range(3)]
        # entry: [valid, pre_gid, post_local, weight]; ledger [tick | None]
        self.table = [[0, 0, 0, 0] for _ in range(ENTRIES)]
        self.ledger = [None] * ENTRIES
        self.tick_cnt = 0
        self.rule = PairSTDP(window_ticks=WINDOW)
        self.fire_log = []

    def load(self, addr, valid, pre_gid, post_local, weight):
        self.table[addr] = [valid, pre_gid, post_local, weight]

    def _pot_pass(self, local):
        for i, (v, _pg, post, _w) in enumerate(self.table):
            if v and post == local and self.ledger[i] is not None \
                    and (self.tick_cnt - self.ledger[i]) <= WINDOW:
                w = self.table[i][3]
                self.table[i][3] = min(WEIGHT_RAIL_HI, w + 1)
                self.ledger[i] = None
        self._expiry_pass()  # RTL chains EXP after POT; harmless + mirrored

    def _expiry_pass(self):
        for i, (v, _pg, _post, w) in enumerate(self.table):
            if v and self.ledger[i] is not None \
                    and (self.tick_cnt - self.ledger[i]) > WINDOW:
                self.table[i][3] = max(WEIGHT_RAIL_LO, w - 1)
                self.ledger[i] = None

    def feed_spike(self, gid):
        fires = deque()
        for i, (v, pre, post, w) in enumerate(self.table):
            if not (v and pre == gid):
                continue
            fired = self.somas[post].apply_synaptic_input(w)
            self.ledger[i] = self.tick_cnt
            if fired:
                fires.append(post)
        while fires:
            local = fires.popleft()
            self.fire_log.append(local)
            self._pot_pass(local)

    def tick(self):
        self.tick_cnt += 1
        for i, soma in enumerate(self.somas):
            if soma.advance_time():
                self.fire_log.append(i)
                self._pot_pass(i)
        self._expiry_pass()


async def reset_tile(dut):
    dut.rst_n.value = 0
    for sig in ("spk_valid", "tick", "cfg_en", "rb_soma_req"):
        getattr(dut, sig).value = 0
    if hasattr(dut, "integrate_open"):
        dut.integrate_open.value = 1   # tile unit: integration always open
    if hasattr(dut, "spk_parity"):
        dut.spk_parity.value = 1       # != initial tick_parity(0) -> deliverable
    if hasattr(dut, "out_spk_ready"):
        dut.out_spk_ready.value = 1    # sinks are always ready at unit level
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def wait_quiet(dut, cap=400):
    for _ in range(cap):
        if int(dut.tile_busy.value) == 0:
            return
        await FallingEdge(dut.clk)
    import os
    if os.environ.get("DEND_DEBUG") == "1":
        print(f"DEBUG stuck: tile_busy={int(dut.tile_busy.value)} "
              f"dend={int(dut.dend_busy.value)} inq_empty={int(dut.inq_empty.value)} "
              f"outq_empty={int(dut.outq_empty.value)} fire_req={int(dut.fire_req.value)} "
              f"fire_taken={int(dut.fire_taken.value)} fireq_empty={int(dut.fireq_empty.value)} "
              f"dend_state={int(dut.dendrite.state.value)}")
    raise AssertionError("tile never went quiet")


async def bench_spike(dut, gid):
    dut.spk_gid.value = gid
    dut.spk_valid.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.spk_valid.value = 0
    await wait_quiet(dut)


async def bench_tick(dut):
    dut.tick.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.tick.value = 0
    # the soma sweep runs in parallel: wait for both
    for _ in range(600):
        if int(dut.tile_busy.value) == 0:
            break
        await FallingEdge(dut.clk)
    else:
        raise AssertionError("tick pass never settled")
    # bench keeps its spk_parity opposite the tile's new tick parity
    # (unit-test contract: integration window is permanently open here)
    if hasattr(dut, "spk_parity"):
        dut.spk_parity.value = 1 - int(dut.tick_parity.value)


async def program_tile(dut, entries, ref):
    for addr, (valid, pre, post, weight) in enumerate(entries):
        ref.load(addr, valid, pre, post, weight)
        dut.cfg_addr.value = addr
        dut.cfg_wdata.value = ((valid & 1) << 20) | ((pre & 0x3FF) << 10) \
            | ((post & 0x3) << 8) | (weight & 0xFF)
        dut.cfg_en.value = 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
    dut.cfg_en.value = 0


async def read_dend_table(dut):
    words = []
    for addr in range(ENTRIES):
        dut.rb_dend_addr.value = addr
        await FallingEdge(dut.clk)
        words.append(int(dut.rb_dend_rdata.value))
    return words


@cocotb.test()
async def neuro_tile_plasticity_matches_referee(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    ref = CoreReferee()
    await reset_tile(dut)

    # soma programs: 0 = detector (theta 200); 1-3 = gpio never firing
    dut.soma.nram[0].value = pack_word(DETECTOR_PARAMS)
    for idx in (1, 2, 3):
        dut.soma.nram[idx].value = pack_word(GPIO_PARAMS)
    await FallingEdge(dut.clk)

    entries = [
        (1, 0, DETECTOR_LOCAL, 120),   # A -> detector
        (1, 4, DETECTOR_LOCAL, 120),   # B -> detector
        (1, 3, DETECTOR_LOCAL, 120),   # C -> detector (control)
    ]
    await program_tile(dut, entries, ref)

    trajectory = []
    for rnd in range(30):
        await bench_spike(dut, 0); ref.feed_spike(0)
        await bench_spike(dut, 4); ref.feed_spike(4)
        for _ in range(3):
            await bench_tick(dut); ref.tick()
        await bench_spike(dut, 3); ref.feed_spike(3)
        for _ in range(4):
            await bench_tick(dut); ref.tick()
        words = await read_dend_table(dut)
        got = [w & 0xFF for w in words[:3]]
        expected = [ref.table[i][3] & 0xFF for i in range(3)]
        trajectory.append(got)
        assert got == expected, \
            f"round {rnd}: RTL weights {got} != referee {expected}"

    a_final = trajectory[-1][0] if trajectory[-1][0] < 128 else trajectory[-1][0] - 256
    c_final = trajectory[-1][2] if trajectory[-1][2] < 128 else trajectory[-1][2] - 256
    assert a_final == 127, f"paired wire must reach rail, got {a_final}"
    assert c_final <= 90, f"control wire must depress, got {c_final}"


@cocotb.test()
async def dendrite_boundary_window_exact(dut):
    """Kills the expiry off-by-one mutant (>= WINDOW pays nothing):

    t0: an entry takes an arrival (window 3).
    t3: a tick boundary expires nothing real (3 - 0 > 3 is FALSE).
    t3+: a DIFFERENT entry fires the post neuron; POT pays entries with
    (tick - t_arr) <= 3 — the old arrival IS inside and must pay +1.
    The mutant expires it at t3, so its weight never moves."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    ref = CoreReferee()
    await reset_tile(dut)

    dut.soma.nram[0].value = pack_word(DETECTOR_PARAMS)
    for idx in (1, 2, 3):
        dut.soma.nram[idx].value = pack_word(GPIO_PARAMS)

    # two wires into the detector: gid 0 (the one we watch) and gid 4 (the
    # trigger, strong enough to fire alone after one delivery)
    entries = [(1, 0, DETECTOR_LOCAL, 120), (1, 4, DETECTOR_LOCAL, 120)]
    await program_tile(dut, entries, ref)

    await bench_spike(dut, 0);  ref.feed_spike(0)   # A arrives at t0
    for _ in range(3):
        await bench_tick(dut)                        # 3 boundary passes
        ref.tick()

    # the trigger pair delivers: fires the detector; POT pays at the edge
    await bench_spike(dut, 0);  ref.feed_spike(0)    # second half of the pair
    await bench_spike(dut, 4);  ref.feed_spike(4)    # crossing: post fires
    # then any later tick pays the ledger: mandatory Pot runs on the fire
    await bench_tick(dut);      ref.tick()

    words = await read_dend_table(dut)
    got_a = (words[0] & 0xFF)
    expected_a = ref.table[0][3] & 0xFF
    assert got_a == expected_a, \
        f"window-edge arrival: RTL weight {got_a:#x} != referee {expected_a:#x}"
    assert (got_a if got_a < 128 else got_a - 256) == 121, \
        "the boundary arrival must earn exactly +1"
