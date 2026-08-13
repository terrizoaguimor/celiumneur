# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dynamics-first tests for the Soma golden model (Invariant I8:
tests must fire neurons, never certify silence).

Regression anchors name the audited flaw each test guards against.
"""

from soma import (
    VMEM_MAX,
    VMEM_MIN,
    WEIGHT_MAX,
    WEIGHT_MIN,
    NeuronParams,
    Soma,
    ceiling_leak_amount,
    saturate_vmem,
)

FAST_LEAK = 1        # |v| halves (ceil) every tick
NO_LEAK = 15         # decays by exactly 1 per tick
NO_REFRACTORY = 0


def default_soma(v0: int = 0, **param_overrides) -> Soma:
    config = {"theta": 100, "leak_shift": FAST_LEAK, "refractory_ticks": NO_REFRACTORY}
    config.update(param_overrides)
    return Soma(NeuronParams(**config), v0=v0)


# --- Integration & saturation (I6) -----------------------------------------

def test_excitatory_input_integrates_exactly():
    soma = default_soma()
    soma.apply_synaptic_input(30)
    assert soma.v == 30


def test_input_saturates_at_positive_rail_without_wrapping():
    # Regression: lif-tt-asic wraps 100 + 100 to -68 (lif_components.v:9).
    # Note: the apply path never decrements refractory, so after the first
    # spike the membrane can be driven to the rail without further resets.
    soma = default_soma(refractory_ticks=3, v0=VMEM_MAX - 10)
    soma.apply_synaptic_input(WEIGHT_MAX)  # fires; v := VMEM_MAX - 100, cd := 3
    for _ in range(300):
        soma.apply_synaptic_input(WEIGHT_MAX)
    assert soma.v == VMEM_MAX


def test_input_saturates_at_negative_rail_without_wrapping():
    # Deeply negative membrane never approaches theta: no spike, no reset,
    # so the pure accumulation path is what reaches the rail.
    soma = default_soma(v0=-32000)
    for _ in range(300):
        soma.apply_synaptic_input(WEIGHT_MIN)
    assert soma.v == VMEM_MIN


def test_saturate_vmem_clamps_both_ends():
    assert saturate_vmem(VMEM_MAX + 10_000) == VMEM_MAX
    assert saturate_vmem(VMEM_MIN - 10_000) == VMEM_MIN
    assert saturate_vmem(0) == 0


# --- Leak convergence (kills sticky residue) --------------------------------

def test_leak_converges_to_zero_from_small_positive():
    # Regression: lif-tt >>> leak leaves v in {1..7} forever.
    soma = default_soma(v0=5, leak_shift=3, theta=VMEM_MAX)
    ticks = 0
    while soma.v != 0:
        soma.advance_time()
        ticks += 1
        assert ticks < 100, "leak must reach exactly zero, not asymptote"
    assert soma.v == 0


def test_leak_converges_to_zero_from_small_negative():
    soma = default_soma(v0=-5, leak_shift=3, theta=VMEM_MAX)
    for _ in range(100):
        soma.advance_time()
    assert soma.v == 0


def test_leak_is_monotone_decay_toward_zero():
    soma = default_soma(v0=200, theta=VMEM_MAX)
    deltas: list[int] = []
    while soma.v != 0:
        previous = abs(soma.v)
        soma.advance_time()
        deltas.append(previous - abs(soma.v))
    assert all(delta > 0 for delta in deltas)
    assert deltas == sorted(deltas, reverse=True)  # geometric, not linear


def test_max_leak_shift_decays_by_one_per_tick():
    assert ceiling_leak_amount(10_000, NO_LEAK) == 1
    assert ceiling_leak_amount(-10_000, NO_LEAK) == -1
    assert ceiling_leak_amount(0, FAST_LEAK) == 0


# --- Firing & reset ----------------------------------------------------------

def test_threshold_crossing_fires_spike():
    soma = default_soma()
    fired = soma.apply_synaptic_input(100)
    assert fired is True


def test_subtractive_reset_keeps_residue():
    # Default mode: post-spike residue v - theta is preserved (less lossy,
    # snnTorch convention; ODIN's reset-to-zero drops it, lif_neuron_state.v:46).
    soma = default_soma()
    soma.apply_synaptic_input(120)
    assert soma.v == 20


def test_reset_to_zero_mode_drops_residue():
    soma = default_soma(subtractive_reset=False)
    soma.apply_synaptic_input(120)
    assert soma.v == 0


def test_subthreshold_input_never_fires():
    soma = default_soma()
    fired = soma.apply_synaptic_input(99)
    assert fired is False


# --- Refractory -----------------------------------------------------------

def test_refractory_blocks_spiking_but_still_integrates():
    soma = default_soma(refractory_ticks=3)
    assert soma.apply_synaptic_input(120) is True   # fires, v := 120-100 = 20
    assert soma.apply_synaptic_input(127) is False  # refractory: integrates, no fire
    assert soma.v == 147


def test_refractory_enforces_minimum_interspike_interval():
    soma = default_soma(refractory_ticks=3, leak_shift=NO_LEAK)
    fire_ticks = []
    for tick in range(200):
        fired = soma.apply_synaptic_input(100) or soma.advance_time()
        if fired:
            fire_ticks.append(tick)
        if len(fire_ticks) == 4:
            break
    assert len(fire_ticks) == 4
    intervals = [b - a for a, b in zip(fire_ticks, fire_ticks[1:])]
    assert all(interval >= 3 for interval in intervals)


def test_superthreshold_survives_refractory_then_fires_on_tick():
    # Refractoriness masks spikes; the membrane keeps charge and the neuron
    # fires on the first tick after the countdown ends (no new input needed).
    soma = default_soma(refractory_ticks=2, leak_shift=NO_LEAK, theta=50)
    assert soma.apply_synaptic_input(127) is True   # fires, v := 77
    assert soma.advance_time() is False             # 77-1=76 >= 50 but refractory
    assert soma.advance_time() is False
    assert soma.advance_time() is True              # countdown spent -> fires


# --- Per-neuron independence (I7; ReckOn paired packing regression) ---------

def test_minimum_signed_weight_integrates_exactly():
    soma = default_soma()
    soma.apply_synaptic_input(WEIGHT_MIN)
    assert soma.v == WEIGHT_MIN


def test_neurons_with_distinct_params_evolve_independently():
    fast = default_soma(leak_shift=1, theta=80)
    slow = default_soma(leak_shift=NO_LEAK, theta=90)
    assert fast.apply_synaptic_input(127) is True
    assert slow.apply_synaptic_input(127) is True
    assert fast.v == 127 - 80   # subtractive residue, fast threshold
    assert slow.v == 127 - 90   # subtractive residue, slow threshold
    assert _ticks_until_silent(fast) < _ticks_until_silent(slow)


def _ticks_until_silent(soma: Soma, cap: int = 100_000) -> int:
    ticks = 0
    while soma.v != 0 or soma.refractory_countdown != 0:
        soma.advance_time()
        ticks += 1
        assert ticks < cap
    return ticks


# --- Boundary sanity ----------------------------------------------------------

def test_resting_neuron_is_silent_without_input():
    soma = default_soma()
    assert all(soma.advance_time() is False for _ in range(50))
    assert soma.v == 0


def test_repeated_stimulation_produces_periodic_firing():
    soma = default_soma(leak_shift=NO_LEAK)
    fires = 0
    for _ in range(20):
        if soma.apply_synaptic_input(25):
            fires += 1
    assert fires >= 3  # 25 x 4 = 100 = theta -> period 4 → 5 fires in 20
