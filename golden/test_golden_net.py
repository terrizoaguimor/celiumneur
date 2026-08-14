# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whole-network golden regressions that pin RTL-visible semantics."""

from golden_net import GLOBAL_NEURONS, NeuroSandbox
from plasticity import CausalWindowRule
from soma import NeuronParams


def test_repeated_arrival_overwrites_single_slot_ledger() -> None:
    """One physical synapse owns one latest-arrival ledger slot."""
    quiet = NeuronParams(theta=32767, leak_shift=15, refractory_ticks=0)
    box = NeuroSandbox([quiet for _ in range(GLOBAL_NEURONS)])
    box.wire(pre_global=4, post_global=0, weight=50)
    box.enable_plasticity(CausalWindowRule(window_ticks=3))

    # Exercise the actual mesh→dendrite composition twice before the same
    # postsynaptic neuron fires. The second arrival replaces the first slot.
    for _ in range(2):
        box._stage_spike(4)
        box._drain_and_integrate()
    box._fire(0)

    assert box.table.expand(0, 4)[0][1] == 51
