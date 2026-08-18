# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bit-exact golden model of the Hyphae fabric (SPEC.md §4).

Transaction-level referee for the RTL router/link verification. Models:

- 32-bit packets: type[31:28] | payload[27:0]. The fabric routes on a
  destination *mask* of cores; the body is opaque (I2: topology lives in
  tables downstream, not in wire geometry).
- X-Y dimension-ordered routing: X leg first, then Y. Deadlock freedom by
  the turn-model argument (Glass & Ni, ISCA 1992; Dally & Seitz, IEEE TC
  C-36(5), 1987): channel dependencies stay acyclic because no route ever
  turns back into the X dimension.
- Multicast by branch replication: a packet leaves on every output port that
  still holds destinations, carrying the sub-mask for that branch. Fanout is
  limited only by core count, without an independent per-source connection
  cap (the audited ed-snn-fpga pin defaults to 32 entries; ODIN uses a serial
  512-cycle dense population sweep).
- Credit-based flow control (Invariant I1): a link transmits only against
  an available credit; there is no drop path anywhere in the model. Credit
  returns happen when the downstream FIFO pops; the mesh audits every cycle
  that credits == free slots, instead of trusting either side.

Coordinates: id = y*MESH_W + x; x = id % MESH_W; y = id // MESH_W.
Directions: E if dst.x > x, W if dst.x < x, N if dst.y > y, S if dst.y < y.
"""

from dataclasses import dataclass, field

MESH_W = 2
MESH_H = 2
CORE_COUNT = MESH_W * MESH_H
LINK_FIFO_DEPTH = 4

# Packet field geometry (single 32-bit flit).
PAYLOAD_BITS = 28
BODY_BITS = 20
DST_MASK_SHIFT = BODY_BITS
BODY_MASK = (1 << BODY_BITS) - 1
FULL_MASK = (1 << CORE_COUNT) - 1

TYPE_SPIKE = 0x1
TYPE_CONFIG = 0x2
TYPE_LEARN = 0x3
TYPE_MONITOR = 0x4

PORTS = ("PE", "E", "W", "N", "S")

OPPOSITE_PORT = {"E": "W", "W": "E", "N": "S", "S": "N"}


def core_xy(core_id: int) -> tuple[int, int]:
    if not 0 <= core_id < CORE_COUNT:
        raise ValueError(f"core_id outside mesh: {core_id}")
    return core_id % MESH_W, core_id // MESH_W


def core_id_at(x: int, y: int) -> int:
    if not (0 <= x < MESH_W and 0 <= y < MESH_H):
        raise ValueError(f"mesh exit at ({x},{y})")
    return y * MESH_W + x


@dataclass(frozen=True)
class Packet:
    type_code: int
    dst_mask: int
    body: int

    def __post_init__(self) -> None:
        if not 0 < self.dst_mask <= FULL_MASK:
            raise ValueError(f"dst_mask must be non-zero subset of {FULL_MASK:#x}")
        if not 0 <= self.body <= BODY_MASK:
            raise ValueError(f"body must fit {BODY_BITS} bits")

    def with_submask(self, sub_mask: int) -> "Packet":
        return Packet(self.type_code, sub_mask, self.body)


def branch_mask_for(port: str, at_core: int, pending_mask: int) -> int:
    """Sub-mask of pending destinations routed out `port` from `at_core`.

    X-Y discipline: destinations off-column travel X first; on-column
    destinations take the vertical branch. Every branch preserves monotone
    progress in its dimension, which is what keeps the channel graph acyclic.
    """
    x, y = core_xy(at_core)
    sub_mask = 0
    pending = pending_mask
    while pending:
        dst = pending & -pending
        pending ^= dst
        dst_id = dst.bit_length() - 1
        dx, dy = core_xy(dst_id)
        if port == "PE":
            fits = (dx, dy) == (x, y)
        elif port == "E":
            fits = dx > x
        elif port == "W":
            fits = dx < x
        elif port == "N":
            fits = dx == x and dy > y
        else:  # "S"
            fits = dx == x and dy < y
        if fits:
            sub_mask |= dst
    return sub_mask


@dataclass
class RouterModel:
    """Input-queued router: FIFO per input port, credit counter per output
    link, atomic replication (an input head pops only when every branch
    port has credit), round-robin across input ports."""

    core: int
    port_neighbors: dict[str, int]  # mesh port -> neighbor core
    input_queues: dict[str, list[Packet]] = field(init=False)
    credits: dict[str, int] = field(init=False)
    delivered: list[Packet] = field(default_factory=list)
    credit_returns_pending: list[str] = field(default_factory=list)
    _rr_cursor: int = 0

    def __post_init__(self) -> None:
        self.input_queues = {port: [] for port in PORTS}
        self.credits = {port: LINK_FIFO_DEPTH for port in PORTS}

    def inject(self, packet: Packet) -> None:
        self.input_queues["PE"].append(packet)

    def receive_from_link(self, port: str, packet: Packet) -> None:
        queue = self.input_queues[port]
        if len(queue) >= LINK_FIFO_DEPTH:
            raise AssertionError(f"I1 violated: link overflow at core {self.core} port {port}")
        queue.append(packet)

    def needed_output_ports(self, head: Packet) -> list[str]:
        return [
            port for port in PORTS
            if (port == "PE" or port in self.port_neighbors)
            and branch_mask_for(port, self.core, head.dst_mask)
        ]

    def service_one(self) -> list[tuple[int, Packet]]:
        """Arbitrate one input pop this cycle. Returns (neighbor, packet)
        transmissions; PE copies are recorded locally as deliveries."""
        order = PORTS[self._rr_cursor:] + PORTS[: self._rr_cursor]
        for in_port in order:
            queue = self.input_queues[in_port]
            if not queue:
                continue
            head = queue[0]
            needed = self.needed_output_ports(head)
            if not all(self.credits[out] > 0 for out in needed):
                continue  # atomic replication: hold this head, try next input
            queue.pop(0)
            if in_port != "PE":
                self.credit_returns_pending.append(in_port)
            sent = []
            for out in needed:
                branched = head.with_submask(branch_mask_for(out, self.core, head.dst_mask))
                if out == "PE":
                    self.delivered.append(branched)
                else:
                    self.credits[out] -= 1
                    sent.append((self.port_neighbors[out], branched))
            self._rr_cursor = (self._rr_cursor + 1) % len(PORTS)
            return sent
        return []

    def return_credit_on(self, output_port: str) -> None:
        """Restore one credit on this output link (downstream popped)."""
        if self.credits[output_port] >= LINK_FIFO_DEPTH:
            raise AssertionError(f"credit overflow at core {self.core} port {output_port}")
        self.credits[output_port] += 1


class HyphaeMesh:
    """step() = one fabric cycle: each router arbitrates one pop, PE copies
    deliver instantly (local core always ready), link copies move one hop."""

    def __init__(self) -> None:
        self.routers = {core: self._build_router(core) for core in range(CORE_COUNT)}
        self.cycle = 0
        self.max_occupancy_seen = 0

    def _build_router(self, core: int) -> RouterModel:
        x, y = core_xy(core)
        neighbors = {}
        if x + 1 < MESH_W: neighbors["E"] = core_id_at(x + 1, y)
        if x - 1 >= 0:     neighbors["W"] = core_id_at(x - 1, y)
        if y + 1 < MESH_H: neighbors["N"] = core_id_at(x, y + 1)
        if y - 1 >= 0:     neighbors["S"] = core_id_at(x, y - 1)
        return RouterModel(core, neighbors)

    def step(self) -> None:
        self.cycle += 1
        hops: list[tuple[int, int, Packet]] = []  # (from_core, to_core, packet)
        for core, router in self.routers.items():
            for neighbor, packet in router.service_one():
                hops.append((core, neighbor, packet))
        for from_core, neighbor, packet in hops:
            port_in = self._input_port_for(from_core, neighbor)
            self.routers[neighbor].receive_from_link(port_in, packet)
        self._settle_credit_returns()
        self._audit_credit_integrity()

    @staticmethod
    def _input_port_for(from_core: int, to_core: int) -> str:
        fx, fy = core_xy(from_core)
        tx, ty = core_xy(to_core)
        if tx == fx + 1: return "W"  # neighbor is to my east, packet enters my west port
        if tx == fx - 1: return "E"
        if ty == fy + 1: return "S"
        if ty == fy - 1: return "N"
        raise AssertionError(f"non-adjacent hop {from_core}->{to_core}")

    def _settle_credit_returns(self) -> None:
        for router in self.routers.values():
            for input_port in router.credit_returns_pending:
                feeder_id = router.port_neighbors.get(input_port)
                if feeder_id is not None:
                    feeder = self.routers[feeder_id]
                    feeder.return_credit_on(OPPOSITE_PORT[input_port])
            router.credit_returns_pending.clear()

    def _audit_credit_integrity(self) -> None:
        for router in self.routers.values():
            for port, neighbor_id in router.port_neighbors.items():
                occupancy = len(self.routers[neighbor_id].input_queues[OPPOSITE_PORT[port]])
                self.max_occupancy_seen = max(self.max_occupancy_seen, occupancy)
                if router.credits[port] != LINK_FIFO_DEPTH - occupancy:
                    raise AssertionError(
                        f"credit accounting broke: core {router.core} port {port} "
                        f"holds {router.credits[port]}, neighbor occupancy {occupancy}"
                    )

    def quiescent(self) -> bool:
        return all(not queue for r in self.routers.values() for queue in r.input_queues.values())

    def run_until_idle(self, cycle_cap: int = 10_000) -> None:
        while not self.quiescent():
            self.step()
            if self.cycle >= cycle_cap:
                raise AssertionError("no quiescence within cap: deadlock suspected")

    def inject(self, core: int, packet: Packet) -> None:
        self.routers[core].inject(packet)

    def deliveries_at(self, core: int) -> list[Packet]:
        return self.routers[core].delivered
