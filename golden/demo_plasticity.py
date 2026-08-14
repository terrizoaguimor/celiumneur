# SPDX-License-Identifier: AGPL-3.0-or-later
"""demo_plasticity.py — golden proof that the network LEARNS:

drive A and B paired every ROUNDS ticks; A->detector should potentiate toward
the rail; an uncorrelated control wire (C, driven alone, never paired)
should depress toward the floor. The printed trajectory is the artifact the
RTL snooper must reproduce.
"""

from soma import NeuronParams
from plasticity import CausalWindowRule
from golden_net import NeuroSandbox
from demo_net import build_demo, DETECTOR, ELECTRODE_A, ELECTRODE_B

ROUNDS = 30
GAP_TICKS = 8


def run_plasticity_demo(box: NeuroSandbox) -> dict[str, list[int]]:
    rule = CausalWindowRule(window_ticks=3)
    box.enable_plasticity(rule)
    trajectory = {"paired": [120], "control": [120]}

    # control wire: C (neuron 3) -> detector, never paired with B
    box.wire(3, DETECTOR, 120)

    for rnd in range(ROUNDS):
        # paired A+B: detector fires on the arrival tick itself -> both wires
        # earn LTP (causal pair rule)
        box.stimulate(ELECTRODE_A, 120)
        box.stimulate(ELECTRODE_B, 120)
        for _ in range(3):
            box.tick()
        # lone control C, long after the detector's last fire (cold) -> LTD
        box.stimulate(3, 120)
        box.tick()
        # let things settle before next round
        for _ in range(GAP_TICKS - 4):
            box.tick()
        trajectory["paired"].append(
            box.table.expand(2, 0)[0][1])  # A lives on core0, detector core2
        trajectory["control"].append(box.table.expand(2, 3)[0][1])
    return trajectory


if __name__ == "__main__":
    from demo_net import PAIR_WEIGHT

    box = build_demo()
    traj = run_plasticity_demo(box)
    print("round: " + " ".join(f"{i:4d}" for i in range(len(traj["paired"]))))
    print("paired : " + " ".join(f"{w:4d}" for w in traj["paired"]))
    print("control: " + " ".join(f"{w:4d}" for w in traj["control"]))
    assert traj["paired"][-1] > traj["paired"][0], "paired wire must potentiate"
    assert traj["control"][-1] < traj["control"][0], "uncorrelated wire must depress"
    print("PLASTICITY DEMO OK")
