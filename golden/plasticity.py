# SPDX-License-Identifier: AGPL-3.0-or-later
"""plasticity.py — the CeliumNeUR plasticity rule, named CWR (causal-window
rule), not STDP. (Review-driven naming change: Song-Miller-Abbott's STDP
watches the pre/post interval; CWR pays arrivals whose causal window closed
with a fire and depresses expirations. The reference comparison to STDP
remains future work — registered, not performed v1.)

Behavior (saturating, 1-LSB steps):
    LTP (post neuron j fires at tick t):
        every ledger entry (pre arrival on j) with t_arr in [t-W, t]: w <- w+1, consumed
    LTD (tick accounting):
        every ledger entry whose window closed unpaid: w <- w-1, removed

That shape mirrors only the *scheduling* mylane of pair-STDP (Song, Miller &
Abbott, Nat. Neurosci. 3:919-926, 2000) using fabric-visible facts only.
v1.0's trap (first-arrival-pays-then-fire-refunds = order artifact) is
documented below; expiry is the only LTD path in CWR.
"""

WEIGHT_RAIL_HI = 127
WEIGHT_RAIL_LO = -128
WINDOW_TICKS_DEFAULT = 3

WEIGHT_RAIL_HI = 127
WEIGHT_RAIL_LO = -128
WINDOW_TICKS_DEFAULT = 3


def clamp_weight(w: int) -> int:
    return max(WEIGHT_RAIL_LO, min(WEIGHT_RAIL_HI, w))


class PairSTDP:
    def __init__(self, window_ticks: int = WINDOW_TICKS_DEFAULT) -> None:
        self.window = window_ticks
        self.last_fire_tick: dict[int, int] = {}   # post gid -> tick

    def note_fire(self, gid: int, tick: int) -> None:
        self.last_fire_tick[gid] = tick

    def on_expiry(self, w: int) -> int:
        """LTD at window expiry: an arrival that never paid a fire is
        anti-causal by definition; nothing about 'post was cold then' is
        consulted (that order artifact is what v1.0 got wrong)."""
        return clamp_weight(w - 1)

    def recent_arrivals_filter(self, now_tick: int, arrival_tick: int) -> bool:
        """True iff an arrival at arrival_tick counts as causal to a fire at now."""
        return 0 <= (now_tick - arrival_tick) <= self.window

    def expired(self, now_tick: int, arrival_tick: int) -> bool:
        return (now_tick - arrival_tick) > self.window

    def potentiate(self, w: int) -> int:
        return clamp_weight(w + 1)
