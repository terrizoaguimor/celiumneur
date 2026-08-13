# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dynamics-first tests for the Hyphae golden fabric (SPEC §2, Invariant I1).

Every test moves packets across the mesh; silence-only tests are forbidden
(I8). Invariant I1 means: no test may pass because something was dropped.
"""

import pytest

from hyphae import (
    BODY_MASK,
    FULL_MASK,
    LINK_FIFO_DEPTH,
    TYPE_CONFIG,
    TYPE_SPIKE,
    HyphaeMesh,
    Packet,
    branch_mask_for,
    core_id_at,
)


def spike_to(dst_mask: int, body: int) -> Packet:
    return Packet(TYPE_SPIKE, dst_mask, body)


# --- X-Y routing discipline --------------------------------------------------

def test_x_leg_runs_before_y_leg():
    # From (0,0) to (1,1): the eastward branch carries the destination,
    # the north branch must see nothing (X completes before Y).
    assert branch_mask_for("E", at_core=0, pending_mask=0b1000) == 0b1000
    assert branch_mask_for("N", at_core=0, pending_mask=0b1000) == 0


def test_vertical_branch_only_after_x_aligned():
    # At (1,0) x is aligned with dst (1,1): only N carries it now.
    assert branch_mask_for("N", at_core=1, pending_mask=0b1000) == 0b1000
    assert branch_mask_for("E", at_core=1, pending_mask=0b1000) == 0
    assert branch_mask_for("W", at_core=1, pending_mask=0b1000) == 0


def test_unicast_corners_deliver_payload():
    mesh = HyphaeMesh()
    mesh.inject(0, spike_to(0b1000, body=0xABCDE))
    mesh.run_until_idle(cycle_cap=200)
    delivered = mesh.deliveries_at(3)
    assert len(delivered) == 1
    assert delivered[0].body == 0xABCDE
    assert delivered[0].dst_mask == 0b1000


def test_same_core_delivery_stays_local():
    mesh = HyphaeMesh()
    mesh.inject(0, spike_to(0b0001, body=7))
    mesh.run_until_idle(cycle_cap=50)
    assert len(mesh.deliveries_at(0)) == 1
    assert all(len(mesh.deliveries_at(c)) == 0 for c in (1, 2, 3))


# --- Multicast: fanout without hardware caps ---------------------------------

def test_multicast_reaches_all_cores_exactly_once():
    mesh = HyphaeMesh()
    mesh.inject(0, spike_to(FULL_MASK, body=0x1))
    mesh.run_until_idle(cycle_cap=500)
    for core in range(4):
        delivered = mesh.deliveries_at(core)
        assert len(delivered) == 1
        assert delivered[0].dst_mask == (1 << core)


@pytest.mark.parametrize("mask", [m for m in range(1, 1 << 4)])
def test_every_nonempty_mask_delivers_exactly_to_its_set(mask):
    mesh = HyphaeMesh()
    mesh.inject(0, spike_to(mask, body=0x55))
    mesh.run_until_idle(cycle_cap=500)
    for core in range(4):
        expected = 1 if mask & (1 << core) else 0
        assert len(mesh.deliveries_at(core)) == expected


# --- Flow control: stall, storm, no loss (I1) ---------------------------------

def test_burst_fills_links_but_never_overflows():
    mesh = HyphaeMesh()
    burst = 32
    for body in range(burst):
        mesh.inject(0, spike_to(0b1000, body=body))
    mesh.run_until_idle(cycle_cap=2_000)
    assert len(mesh.deliveries_at(3)) == burst
    assert {p.body for p in mesh.deliveries_at(3)} == set(range(burst))
    assert mesh.max_occupancy_seen > 0  # buffers really stressed
    assert mesh.max_occupancy_seen <= LINK_FIFO_DEPTH


def test_full_mesh_multicast_storm_no_loss_no_deadlock():
    mesh = HyphaeMesh()
    per_source = 8
    for core in range(4):
        for seq in range(per_source):
            mesh.inject(core, spike_to(FULL_MASK, body=(core << 8) | seq))
    mesh.run_until_idle(cycle_cap=5_000)
    for core in range(4):
        assert len(mesh.deliveries_at(core)) == 4 * per_source
    assert mesh.quiescent()


def test_static_config_type_routes_identically():
    # Type is transport-agnostic: the fabric does not privilege packet kinds.
    mesh = HyphaeMesh()
    mesh.inject(3, Packet(TYPE_CONFIG, 0b0001, body=0x12345))
    mesh.run_until_idle(cycle_cap=200)
    assert mesh.deliveries_at(0)[0].body == 0x12345


# --- Boundaries & error handling ----------------------------------------------

def test_packet_rejects_empty_mask():
    with pytest.raises(ValueError):
        Packet(TYPE_SPIKE, 0, body=0)


def test_packet_rejects_mask_outside_mesh():
    with pytest.raises(ValueError):
        Packet(TYPE_SPIKE, 0b1_0000, body=0)


def test_packet_rejects_oversized_body():
    with pytest.raises(ValueError):
        Packet(TYPE_SPIKE, 0b0001, body=BODY_MASK + 1)


def test_core_id_roundtrip_covers_mesh():
    # Canonical id = y*MESH_W + x, so x = i % 2 and y = i // 2.
    assert [core_id_at(i % 2, i // 2) for i in range(4)] == [0, 1, 2, 3]
