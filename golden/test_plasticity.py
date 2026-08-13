# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the golden plasticity rule (CWR, causal-window form):
every property here is contractual for the RTL snooper."""

from plasticity import PairSTDP, WEIGHT_RAIL_HI, WEIGHT_RAIL_LO


def fresh_rule(window=3):
    return PairSTDP(window_ticks=window)


def test_fire_pays_recent_arrival_ltp():
    rule = fresh_rule()
    assert rule.recent_arrivals_filter(now_tick=10, arrival_tick=7)
    assert rule.potentiate(50) == 51


def test_old_arrival_is_expired_not_caused():
    rule = fresh_rule()
    assert not rule.recent_arrivals_filter(now_tick=10, arrival_tick=6)
    assert rule.expired(now_tick=11, arrival_tick=7)
    assert not rule.expired(now_tick=10, arrival_tick=7)


def test_expiry_depresses_by_one():
    rule = fresh_rule()
    assert rule.on_expiry(50) == 49


def test_ltp_clamps_at_rail():
    rule = fresh_rule()
    assert rule.potentiate(WEIGHT_RAIL_HI) == WEIGHT_RAIL_HI


def test_ltd_clamps_at_floor():
    rule = fresh_rule()
    assert rule.on_expiry(WEIGHT_RAIL_LO) == WEIGHT_RAIL_LO


def test_boundary_inclusive_window():
    rule = fresh_rule()
    assert rule.recent_arrivals_filter(now_tick=13, arrival_tick=10)
    assert not rule.recent_arrivals_filter(now_tick=14, arrival_tick=10)


def test_storm_never_leaves_rails():
    rule = fresh_rule()
    w = 0
    for _ in range(2000):
        w = rule.potentiate(rule.on_expiry(w))
        assert WEIGHT_RAIL_LO <= w <= WEIGHT_RAIL_HI
