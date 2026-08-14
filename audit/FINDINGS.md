# Pinned external RTL findings

These findings describe only the exact revisions in
`source_snapshot.lock.json`. They are evidence for why CeliumNeUR adopted its
eight invariants, not claims of functional equivalence or blanket judgments on
the upstream projects.

## ODIN-CDC-001 — request-only AER synchronization

**Classification:** protocol-dependent boundary. **Influenced:** I3.

`src/controller.v:127-156` decodes the multi-bit `AERIN_ADDR` directly while
putting `AERIN_REQ` through two registers. A conforming four-phase AER sender
can make this safe by holding the address stable through acknowledgement; this
finding therefore does not assert an ODIN protocol failure. It records that
payload atomicity depends on an environmental timing contract instead of being
enforced by a multi-bit CDC primitive. CeliumNeUR confines multi-clock payloads
to `hypha_sync_fifo` and keeps its default SoC single-clock.

## ODIN-SCAN-002 — serialized dense population sweep

**Classification:** architectural tradeoff. **Influenced:** I2 and I4.

`src/controller.v:171-210` selects `POP_NEUR` and stays there until the 9-bit
control counter reaches its terminal value. `src/controller.v:431-455` couples
that phase to a sequential neuron counter and synaptic-array addresses. The
result is a 512-control-cycle dense population pass for a scheduled neuron
event. This is a coherent compact architecture, not a correctness defect;
CeliumNeUR instead makes connectivity addressable and lets integration and
learning walk independently.

## RECKON-CLK-001 — externally constrained clock OR

**Classification:** integration constraint. **Influenced:** I3.

`src/reckon.v:461-470` forms the core clock by OR-ing the external and internal
clocks. Correct operation therefore depends on clock-source sequencing and SDC
constraints outside this module. This audit does not claim those constraints
are absent in the intended chip flow. CeliumNeUR avoids clock combination in
the default top and isolates explicit CDC use behind an asynchronous FIFO.

## RECKON-PHASE-002 — propagation and e-prop are global FSM phases

**Classification:** architectural tradeoff. **Influenced:** I4.

`src/srnn.v:711-740` makes `PROP` and `EPROP` mutually exclusive states in one
global FSM. That organization is appropriate for a scheduled accelerator but
means learning occupies a global phase rather than progressing as an
independent walker. CeliumNeUR's I4 deliberately permits accepted fabric
traffic while its learning walker is active.

## RECKON-TOPO-003 — dense counter-derived weight addressing

**Classification:** architectural tradeoff. **Influenced:** I2.

`src/srnn.v:1001-1008` derives input and recurrent weight addresses from neuron
scan counters and a fixed slice of the paired-neuron counter. The topology is
therefore encoded in the dense memory geometry. CeliumNeUR stores explicit
pre-GID/post-local-address tuples in each tile's synapse table.

## RECKON-PARAM-004 — alpha and threshold are shared by a neuron pair

**Classification:** parameter granularity. **Influenced:** I7.

`src/srnn.v:1034-1066` stores two membrane/traces records in one 128-bit word,
then derives one `alpha` and one `thr` from the word addressed by the pair. This
is an efficient packing choice. CeliumNeUR chose independently addressable
threshold, leak, refractory period and reset mode for every neuron instead.

## EDSNN-NODROP-001 — recurrent connection skipped when the FIFO is full

**Classification:** loss path. **Influenced:** I1.

In `hardware/hdl/rtl/core/core_group.v:418-434`, a non-zero recurrent weight is
enqueued only while `fifo_full` is false, but the scan advances in either case.
There is no retry state for the skipped connection in this block. CeliumNeUR's
I1 instead requires held-valid or credit ownership until a transaction fires.

## EDSNN-TIME-002 — refractory time follows an idle leak sweep

**Classification:** time-semantics coupling. **Influenced:** I7.

The `core_group` interface at `hardware/hdl/rtl/core/core_group.v:35-76` has no
explicit time-tick input. Lines 300-349 decrement refractory state during a
background leak sweep, and lines 440-442 restart that sweep when the FIFO is
empty and the FSM is idle. Refractory duration is therefore coupled to service
cadence and traffic. CeliumNeUR updates refractory and leak only on accepted,
transactional time ticks.

## EDSNN-FANOUT-003 — fixed per-source fanout capacity

**Classification:** capacity contract. **Influenced:** I2.

`hardware/hdl/rtl/router/spike_router.v:13-15,83-92` sizes connection memory as
`NUM_NEURONS * MAX_FANOUT`; the integrated top at lines 518-524 instantiates a
fanout of 32. This is a clear and reasonable hardware resource bound, not a
defect. CeliumNeUR's inter-tile axon representation uses a destination-core
mask and therefore has no independent per-source connection-list cap.

## EDSNN-OUT-004 — generated spikes can be discarded at output saturation

**Classification:** observable loss path. **Influenced:** I1.

`hardware/hdl/rtl/neurons/lif_neuron_array.v:451-465,490-504` pushes a generated
spike only when the output FIFO has space (or pops concurrently); a firing pulse
while full increments an internal drop counter instead. This makes saturation
diagnosable inside the block but does not preserve the event for later
acceptance. CeliumNeUR carries a spike as a held-valid transaction until the
consumer fires it.

## LIF-ARITH-001 — narrow modular arithmetic precedes threshold comparison

**Classification:** arithmetic boundary. **Influenced:** I6.

`src/lif_components.v:3-24` computes leak and the next membrane value directly
in signed 8-bit wires before comparing against threshold. Addition can wrap at
the representable extrema, and arithmetic right shift makes small positive
residues stop leaking. CeliumNeUR widens intermediates, saturates at the state
limits and implements leak toward zero.

## LIF-OBS-002 — top-level membrane state is disconnected

**Classification:** observability boundary. **Influenced:** I5.

`src/project.v:49-85` leaves every `v_mem` output unconnected and exports only
four spike bits plus programming completion. This is a valid TinyTapeout pin
budget choice. CeliumNeUR nevertheless makes soma and dendrite state readable
without entering their update arbiters so state transitions can be audited.

## LIF-TEST-003 — tests never require a positive spike

**Classification:** verification gap. **Influenced:** I8.

`test/test.py:110-160` proves silence with zero weights and later checks only
that outputs remain resolvable. The pinned suite contains no assertion that a
configured neuron must fire. CeliumNeUR's I8 requires positive spike counts,
state changes and exact GIDs so a silent simulation cannot pass as functional
evidence.
