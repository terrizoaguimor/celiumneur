# SPDX-License-Identifier: Apache-2.0
"""Bit-exact golden model of the CeliumNeUR SomaCore neuron (SPEC.md §6.1).

This module is the referee: RTL is verified cycle-by-cycle against it.
Discrete-time fixed-point LIF per Gerstner & Kistler (Neuronal Dynamics,
Ch. 1.3) and the forward-Euler form used by snnTorch (Eshraghian et al.,
Proc. IEEE 2023).

Every arithmetic rule here exists because an audited design failed there:
  - saturating accumulator        -> kills lif-tt-asic wrap (lif_components.v:9)
  - ceiling leak toward zero      -> kills lif-tt-asic sticky residue
  - refractory in real ticks      -> kills ed-snn-fpga sweep-counted refractory
  - per-neuron independent params -> kills ReckOn paired packing (srnn.v:1063)
"""

from dataclasses import dataclass

VMEM_BITS = 16
VMEM_MAX = (1 << (VMEM_BITS - 1)) - 1   # +32767
VMEM_MIN = -(1 << (VMEM_BITS - 1))      # -32768

WEIGHT_BITS = 8
WEIGHT_MAX = (1 << (WEIGHT_BITS - 1)) - 1  # +127 (excitatory ceiling)
WEIGHT_MIN = -(1 << (WEIGHT_BITS - 1))     # -128 (inhibitory floor)


def saturate_vmem(raw: int) -> int:
    """Clamp an unbounded accumulator into the signed 16-bit membrane range.

    Invariant I6: overflow clamps; it never wraps.
    """
    return max(VMEM_MIN, min(VMEM_MAX, raw))


def ceiling_leak_amount(v: int, leak_shift: int) -> int:
    """Magnitude to subtract from v so v decays toward exactly zero.

    Computes ceil(|v| / 2**leak_shift) with the sign of v. Truncating shift
    division (the v >>> k of lif-tt-asic) never clears v < 2**k; ceiling
    division costs one extra adder and guarantees convergence to zero.
    """
    if not 0 <= leak_shift < VMEM_BITS:
        raise ValueError(f"leak_shift must fit the membrane datapath, got {leak_shift}")
    magnitude = abs(v)
    if magnitude == 0:
        return 0
    ceiling_share = (magnitude + (1 << leak_shift) - 1) >> leak_shift
    return ceiling_share if v > 0 else -ceiling_share


@dataclass(frozen=True)
class NeuronParams:
    """Per-neuron configuration word (Invariant I7).

    theta:            firing threshold, 1..VMEM_MAX.
    leak_shift:       k in [0, VMEM_BITS); tick leak = ceil(|v| / 2**k).
                      k = 0 discharges to zero in one tick (maximum leak).
    refractory_ticks: minimum ticks between spikes; input integrates meanwhile.
    subtractive_reset: True keeps the post-spike residue v - theta (snnTorch
                      'subtract', less lossy); False forces v to zero.
    """

    theta: int
    leak_shift: int
    refractory_ticks: int
    subtractive_reset: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.theta <= VMEM_MAX:
            raise ValueError(f"theta must be in [1, {VMEM_MAX}], got {self.theta}")
        if self.refractory_ticks < 0:
            raise ValueError("refractory_ticks must be >= 0")


class Soma:
    """One improved-LIF neuron. Two entry points mirror the hardware split:

    apply_synaptic_input: the spike-event path (weight arrival).
    advance_time:         the time-tick path (leak + refractory countdown).
    """

    def __init__(self, params: NeuronParams, v0: int = 0) -> None:
        self.params = params
        self.v = saturate_vmem(v0)
        self.refractory_countdown = 0

    def apply_synaptic_input(self, weight: int) -> bool:
        """Integrate one spike event; returns True if the neuron fired."""
        if not WEIGHT_MIN <= weight <= WEIGHT_MAX:
            raise ValueError(f"weight must fit {WEIGHT_BITS}-bit signed, got {weight}")
        self.v = saturate_vmem(self.v + weight)
        return self._evaluate_spike()

    def advance_time(self) -> bool:
        """Apply one time tick; returns True if the neuron fired.

        Leak only shrinks |v|, so it can never cause a crossing by itself;
        evaluation here exists for a superthreshold membrane leaving
        refractory with no new input.
        """
        self.v = saturate_vmem(self.v - ceiling_leak_amount(self.v, self.params.leak_shift))
        fired = self._evaluate_spike()
        # Decrement after evaluation: an EVENT-path fire at tick t blocks
        # exactly refractory_ticks subsequent ticks. A TICK-path fire (the
        # `fired` above) has its fresh countdown decremented in this same
        # call and blocks refractory_ticks - 1: the asymmetry is contract,
        # SPEC §6.1, pinned by test_tick_path_fire_blocks_one_fewer_tick....
        if self.refractory_countdown > 0:
            self.refractory_countdown -= 1
        return fired

    def _evaluate_spike(self) -> bool:
        """Fire when superthreshold and not refractory; then reset."""
        if self.refractory_countdown > 0:
            return False
        if self.v < self.params.theta:
            return False
        self.v = self.v - self.params.theta if self.params.subtractive_reset else 0
        self.refractory_countdown = self.params.refractory_ticks
        return True
