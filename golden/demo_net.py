# SPDX-License-Identifier: AGPL-3.0-or-later
"""demo_net.py — the CeliumNeUR sandbox demo network.

A two-input temporal coincidence detector (an AND gate built from leak +
threshold + refractory — the "look, a chip" moment, with dynamics you can
SEE on the raster):

    electrode n0   (core0) ──120──┐
                                    ├── n512 (core2, theta=200, leak fast)
    electrode n256 (core1) ──120──┘             │
                                       150   ▼
                                     n768 (core3, theta=100, refractory=4)

- Electrodes are dumb relays: theta=100, a 120 jolt fires them once.
- The detector needs BOTH inputs within a short window: a lone 120 leaks below theta
  before a second can arrive (visible on the raster as decay toward zero).
- When the detector fires, the output integrates 120 > 100 and fires; its 4-tick refractory
  then visibly blocks the immediate re-pair's echo.

Hand-derived schedule (asserted by the test; derived from the golden
advance_time semantics, which come from Gerstner Ch.1.3 arithmetic):
  pair at phase P   -> detector fires at P (two x 120 = 240)
  detector fire     -> output fires next tick (120 > 100)
  immediate re-pair -> detector fires again; output refractory blocks it.

No novelty claimed: mechanism-level demo of published LIF arithmetic.
"""

from soma import NeuronParams
from golden_net import GLOBAL_NEURONS, NEURONS_PER_CORE, NeuroSandbox

ELECTRODE_A = 0
ELECTRODE_B = NEURONS_PER_CORE
DETECTOR = 2 * NEURONS_PER_CORE
OUTPUT = 3 * NEURONS_PER_CORE
PAIR_WEIGHT = 120
OUT_WEIGHT = 120   # synaptic weights are 8-bit signed by SPEC: 150 is illegal

BASE_PARAMS = [NeuronParams(theta=100, leak_shift=1, refractory_ticks=0,
                            subtractive_reset=True)
               for _ in range(GLOBAL_NEURONS)]


def demo_params() -> list[NeuronParams]:
    params = list(BASE_PARAMS)
    params[DETECTOR] = NeuronParams(theta=200, leak_shift=1, refractory_ticks=0,
                                    subtractive_reset=True)
    params[OUTPUT] = NeuronParams(theta=100, leak_shift=1, refractory_ticks=4,
                                  subtractive_reset=True)
    return params


def build_demo() -> NeuroSandbox:
    box = NeuroSandbox(demo_params())
    box.wire(ELECTRODE_A, DETECTOR, PAIR_WEIGHT)
    box.wire(ELECTRODE_B, DETECTOR, PAIR_WEIGHT)
    box.wire(DETECTOR, OUTPUT, OUT_WEIGHT)
    return box


def run_demo_script(box: NeuroSandbox) -> None:
    """Staged stimulus: lone, lone, pair, then a refractory-collision pair."""
    box.stimulate(ELECTRODE_A, PAIR_WEIGHT)     # lone a
    box.tick()                                  # t0: detector integrates 120
    box.tick()                                  # t1: leak decays it
    box.stimulate(ELECTRODE_B, PAIR_WEIGHT)     # lone b
    box.tick()                                  # t2: integrates, decays
    box.tick()                                  # t3
    box.stimulate(ELECTRODE_A, PAIR_WEIGHT)     # pair in one phase
    box.stimulate(ELECTRODE_B, PAIR_WEIGHT)
    box.tick()                                  # t4: detector fires; output staged
    box.tick()                                  # t5: output fires, refractory loads
    box.stimulate(ELECTRODE_A, PAIR_WEIGHT)     # immediate re-pair
    box.stimulate(ELECTRODE_B, PAIR_WEIGHT)
    box.tick()                                  # t6: detector fires; output still refractory
    box.tick()                                  # t7: 120 lands on gated output — blocked
    box.tick()                                  # t8: refractory winds down
