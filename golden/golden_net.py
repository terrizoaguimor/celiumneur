# SPDX-License-Identifier: AGPL-3.0-or-later
"""golden_net.py — end-to-end golden simulator of CeliumNeUR (SPEC §2+§3).

Composition of the two verified referees: HyphaeMesh moves spike packets,
Soma instances integrate events at the destination core. The dendrite maps
a global presynaptic spike to local (neuron, weight) deliveries — the
indirection of Invariant I2, modeled as an explicit table.

Time semantics (phase-mode, the same contract the RTL bench enforces):
  1. staged spikes drain through the fabric and integrate at the somas;
  2. every soma takes one tick (leak + refractory countdown);
  3. spikes fired anywhere are staged into the fabric for the NEXT phase.
Spikes during a phase never cascade within it — the ReckOn class of chips
defines this exact boundary (events are batched per timestep, srnn.v:
inp_events_next) because an unbounded intra-phase cascade is not a physical
assumption. We adopt it deliberately and document it here.

Sources: neuron dynamics per Gerstner (Ch.1.3) + snnTorch discrete LIF
(Eshraghian et al. 2023) as in golden/soma.py; fabric per golden/hyphae.py.
"""

from hyphae import CORE_COUNT, HyphaeMesh, Packet, TYPE_SPIKE
from soma import NeuronParams, Soma

NEURONS_PER_CORE = 4
GLOBAL_NEURONS = CORE_COUNT * NEURONS_PER_CORE


class DendriteTable:
    """(post_core, pre_global) -> [[post_local, weight], ...]; absent = silent.

    Weights are MUTABLE (plasticity): each entry is a two-slot record, and
    `adjust_weight` is the only legal way to change one (command/query kept
    apart so the snooper never edits by accident)."""

    def __init__(self) -> None:
        self._rows: dict[tuple[int, int], list[list[int]]] = {}

    def add(self, pre_global: int, post_core: int, post_local: int, weight: int) -> None:
        key = (post_core, pre_global)
        self._rows.setdefault(key, []).append([post_local, weight])

    def expand(self, post_core: int, pre_global: int) -> list[list[int]]:
        return self._rows.get((post_core, pre_global), [])

    def set_weight(self, post_core: int, pre_global: int, entry_index: int, new_weight: int) -> None:
        if not -128 <= new_weight <= 127:
            raise ValueError(f"weight outside the 8-bit rails: {new_weight}")
        self._rows[(post_core, pre_global)][entry_index][1] = new_weight


class NeuroSandbox:
    """Whole-chip golden: mesh + Somas + dendrite, phase-mode driver."""

    def __init__(self, params_by_neuron: list[NeuronParams]) -> None:
        if len(params_by_neuron) != GLOBAL_NEURONS:
            raise ValueError("must configure every global neuron")
        self.somas = [Soma(p) for p in params_by_neuron]
        self.mesh = HyphaeMesh()
        self.table = DendriteTable()
        self.tick_index = 0
        # observability: the sandbox exists to watch itself
        self.v_trace: list[list[int]] = [[] for _ in range(GLOBAL_NEURONS)]
        self.fire_log: list[tuple[int, int]] = []  # (tick, global neuron)
        self.plasticity = None  # PairSTDP when enabled (I4); None = frozen weights
        # arrival ledger: (post_core, pre_gid, entry_index, post_gid, tick)
        self._arrival_ledger: list[tuple[int, int, int, int, int]] = []

    def enable_plasticity(self, rule) -> None:
        self.plasticity = rule

    def wire(self, pre_global: int, post_global: int, weight: int) -> None:
        self.table.add(pre_global,
                       post_global // NEURONS_PER_CORE,
                       post_global % NEURONS_PER_CORE,
                       weight)

    def _fanout_mask(self, pre_global: int) -> int:
        mask = 0
        for core in range(CORE_COUNT):
            if self.table.expand(core, pre_global):
                mask |= 1 << core
        return mask

    def _stage_spike(self, pre_global: int) -> None:
        mask = self._fanout_mask(pre_global)
        if mask:
            src_core = pre_global // NEURONS_PER_CORE
            # body carries the presynaptic neuron id; routing reads the mask
            self.mesh.inject(src_core, Packet(TYPE_SPIKE, mask, pre_global))

    def _fire(self, gid: int) -> None:
        self.fire_log.append((self.tick_index, gid))
        if self.plasticity is not None:
            self.plasticity.note_fire(gid, self.tick_index)
            # LTP: recent arrivals on THIS neuron within the window get +1.
            # (The ledger entry is consumed so a fire can pay each arrival
            # exactly once; arrivals too old are left to LTD at their side.)
            t = self.tick_index
            to_potentiate = [
                rec for rec in self._arrival_ledger
                if rec[3] == gid and self.plasticity.recent_arrivals_filter(t, rec[4])
            ]
            for rec in to_potentiate:
                core_, pre_, idx_ = rec[0], rec[1], rec[2]
                self.table.set_weight(
                    core_, pre_, idx_,
                    self.plasticity.potentiate(self.table.expand(core_, pre_)[idx_][1]))
            self._arrival_ledger = [r for r in self._arrival_ledger if r not in to_potentiate]
        self._stage_spike(gid)

    def _drain_and_integrate(self) -> None:
        self.mesh.run_until_idle()
        for core in range(CORE_COUNT):
            for packet in self.mesh.deliveries_at(core):
                rows = self.table.expand(core, packet.body)
                for entry_index, (local, weight) in enumerate(rows):
                    gid = core * NEURONS_PER_CORE + local
                    # No weight math at arrival time (pair rule v1.2): the
                    # ledger record is all that happens now.
                    fired = self.somas[gid].apply_synaptic_input(weight)
                    if self.plasticity is not None:
                        self._arrival_ledger.append(
                            (core, packet.body, entry_index, gid, self.tick_index))
                    if fired:
                        self._fire(gid)
        for router in self.mesh.routers.values():
            router.delivered.clear()

    def stimulate(self, global_neuron: int, weight: int) -> None:
        """External electrode: immediate current into one neuron."""
        if self.somas[global_neuron].apply_synaptic_input(weight):
            self._fire(global_neuron)

    def tick(self) -> None:
        # phase contract: deliver spikes staged by previous phases, integrate,
        # then one tick per soma; fires anywhere stage into the fabric and
        # meet their targets on the NEXT tick. No intra-phase cascades.
        self._drain_and_integrate()
        for gid, soma in enumerate(self.somas):
            if soma.advance_time():
                self._fire(gid)
        for gid in range(GLOBAL_NEURONS):
            self.v_trace[gid].append(self.somas[gid].v)
        # LTD accounting: ledger entries whose causal window closed unpaid.
        if self.plasticity is not None:
            t = self.tick_index
            surviving = []
            for rec in self._arrival_ledger:
                core_, pre_, idx_, _post, t_arr = rec
                if self.plasticity.expired(t, t_arr):
                    self.table.set_weight(
                        core_, pre_, idx_,
                        self.plasticity.on_expiry(self.table.expand(core_, pre_)[idx_][1]))
                else:
                    surviving.append(rec)
            self._arrival_ledger = surviving
        self.tick_index += 1
