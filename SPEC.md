# CeliumNeUR v1 — Executable Design Contract

This document defines the behavior implemented by the repository. It replaces
historical progress notes with a single auditable contract. Code is licensed
AGPL-3.0-or-later; documentation and artwork are CC BY 4.0. Provenance and
third-party boundaries are recorded in `NOTICE.md`.

## 1. Status and claim boundary

CeliumNeUR v1 is synthesizable Verilog-2001 validated by golden models, RTL
simulation, bounded formal checks, mutation testing, lint and pre-PnR
synthesis. The default `celiumneur_soc` parameters are:

| Parameter | Value | Consequence |
|---|---:|---|
| `NEURONS_PER_TILE` | 256 | 8-bit local neuron address |
| `SYNAPSES_PER_TILE` | 256 | 8-bit physical synapse address |
| Tiles | 4 | 2×2 mesh; tile IDs 0–3 |
| Global neuron IDs | 0–1023 | `tile × 256 + local_neuron` |

The repository does not claim PnR, timing closure, SRAM-macro integration,
power closure, FPGA deployment, tapeout readiness or silicon validation.
Block areas below are standard-cell mapping baselines, not physical-chip area.

## 2. Non-negotiable invariants

| ID | Contract | Observable evidence |
|---|---|---|
| I1 | No accepted transaction is silently lost when every producer obeys `valid/ready` or the documented credit contract. | Held-valid assertions, queue overflow witnesses, adversarial stalls, shadow models, BMC |
| I2 | Connectivity is stored in an addressable synapse table, independent of memory geometry. | 256 physical entries/tile; configurable `pre_gid`, `post_local`, weight |
| I3 | Clock-domain crossings use `hypha_sync_fifo`; the default SoC itself is single-clock. | CDC module stress test and raw probe |
| I4 | Synapse integration and learning are independent walkers; learning does not stop accepted fabric traffic globally. | overlap-directed cocotb tests and busy outputs |
| I5 | Soma and dendrite state are readable without entering the update/configuration arbiters. | live readback tests during activity |
| I6 | Neuron and weight arithmetic saturates instead of wrapping. | golden parity, boundary tests and mutants |
| I7 | Threshold, leak, refractory and reset mode are stored per neuron. | heterogeneous-state tests |
| I8 | Verification must force state changes and spikes; a silent simulation cannot pass as functional evidence. | fire-count, GID, weight and waveform assertions |

I1 is a two-party safety contract. A producer must hold `valid` and payload
stable until `ready`, or spend only an available credit. Arbitrary producers
that ignore backpressure can overrun any finite implementation; the design
exposes such attempts through witnesses rather than claiming the impossible.

## 3. Top-level transaction contract

### 3.1 Tick

`tick && tick_ready` accepts exactly one token into an eight-entry global FIFO.
A queued tick is dispatched to all four tiles in the same cycle only when every
tile reports ready. `tick_backpressure` reports an attempted transfer while
full; `tick_overflow_wit` is the underlying sticky FIFO witness.

### 3.2 Stimulus

`stim_valid`, `stim_tile`, `stim_neuron` and `stim_weight` form a normal
valid/ready transaction. Each tile owns a stimulus FIFO. The producer must hold
the complete payload until `stim_ready` for the selected tile.

### 3.3 Host ingress

`host_valid`, `host_packet` and `host_ready` inject a Hyphae flit through PE0.
Host traffic wins PE0 arbitration for the accepted cycle. `host_ready`
acknowledges **fabric injection**, not remote configuration commit. Software
must complete the five-flit transaction and, when required, observe endpoint or
readback state before relying on the new configuration.

### 3.4 Readback

`rb_tile`, `rb_addr` and `rb_req` select both the 27-bit dendrite word and the
64-bit soma word. Soma readback is asynchronous to the update FSM and returns
`rb_valid` without stalling an event or sweep. Dendrite readback is likewise a
separate array read port in this behavioral RTL. Physical macro selection must
preserve this logical non-invasive contract.

## 4. Hyphae fabric

### 4.1 Common flit

```text
31          28 27          24 23          20 19                 0
+--------------+--------------+--------------+--------------------+
| type         | reserved=0   | destination  | type-specific body |
+--------------+--------------+--------------+--------------------+
```

Implemented endpoint types are `SPIKE=0x1` and `CONFIG=0x2`. Unknown types,
nonzero common reserved bits, or a non-one-hot local delivery mask stall at the
tile boundary and assert `unsupported_packet_wit[tile]`.

### 4.2 Routing and flow control

`hypha_router` uses X-first dimension-order routing over the 2×2 mesh. A
multicast mask is split by branch and reduced as it advances. Every mesh input
owns a four-flit FIFO. Upstream credit counters start at four, decrement on
send, and increment on a returned credit. PE delivery uses valid/ready and must
hold payload under stall.

This routing discipline is covered at corner (0,0) by bounded formal checks;
it is not a general proof for arbitrary mesh dimensions.

### 4.3 SPIKE body

```text
[19]    source tick parity
[18:10] reserved, zero
[9:0]   source global neuron ID
```

Each neuron owns a configurable 4-bit axon destination mask. Reset defaults are
tile 0→tile 2, tile 1→tile 2, tile 2→tile 3 and tile 3→none, preserving the demo
network while allowing every entry to be rewritten through CONFIG space 2.

Inbound spikes with the current phase parity wait in the tile input FIFO until
the phase changes; `integrate_open` is the explicit integration gate.

## 5. Routed configuration protocol

A CONFIG transaction is five ordered flits with the same destination mask.
After the common header, the 20-bit bodies are:

```text
header: [19:17] kind=0 | [16:15] space | [14:7] address | [6:0] zero
data 1: [19:17] kind=1 | [16:1] data[15:0]  | [0] zero
data 2: [19:17] kind=2 | [16:1] data[31:16] | [0] zero
data 3: [19:17] kind=3 | [16:1] data[47:32] | [0] zero
data 4: [19:17] kind=4 | [16:1] data[63:48] | [0] zero
```

Spaces are:

| Space | Target | Significant payload bits |
|---:|---|---|
| 0 | Dendrite entry | `[26:0]` |
| 1 | Soma neuron word | `[63:0]` |
| 2 | Axon destination mask | `[3:0]` |
| 3 | Reserved/invalid | none |

Each destination tile assembles independently, so one ordered stream may
multicast the same write. The final fragment creates a held commit transaction;
the endpoint stops accepting more fragments until the selected target accepts
the write. Reserved-bit violations, missing/out-of-order fragments, nested
headers and reserved space set sticky `config_protocol_error[tile]`, cancel the
partial transaction and never write configuration.

## 6. Neuron, synapse and learning behavior

### 6.1 Soma word

```text
[63:48] threshold, unsigned 16-bit
[47]    reset mode: 1 subtract threshold, 0 reset to zero
[46:43] leak shift k
[42:35] refractory duration in ticks
[34:27] reserved, write zero
[26:19] refractory countdown state
[18:16] reserved flags, write zero
[15:0]  membrane potential, signed 16-bit
```

On a time tick, leak moves the membrane potential toward zero by
`ceil(abs(v) / 2**k)`. Synaptic input and leak use a widened accumulator and
clamp to signed 16-bit range. A neuron fires when it is not refractory and the
updated potential reaches its threshold. Fire payload records local neuron,
phase parity and physical fire tick, and remains stable until accepted.
Refractory countdown ages on ticks, not synaptic events.

Reset performs a deterministic 256-entry zero sweep before the soma accepts
normal work. Configuration writes an entire neuron word atomically while idle.

### 6.2 Synapse word

```text
[26]    valid
[25:16] presynaptic global neuron ID
[15:8]  postsynaptic local neuron ID
[7:0]   signed weight
```

Integration scans all physical entries for one accepted presynaptic GID. Every
matching entry emits an independent soma event under valid/ready; duplicate
table entries therefore have real multiplicity.

### 6.3 Causal-window rule (CWR)

The integration walker records the latest accepted arrival tick per physical
synapse entry. A postsynaptic fire starts a separate learning pass. A matching
entry whose latest arrival is no more than `WINDOW` ticks old increments by
one and consumes that ledger record. An unpaired record older than `WINDOW`
decrements by one on an expiry pass. Weights saturate at −128 and +127.

Integration and learning walkers may be active together. If learning clears an
entry in the same cycle that integration records a newer arrival, the newer
arrival wins. CWR is an intentionally small pairwise causal rule; it is not
presented as biologically complete STDP.

## 7. Queue ownership and backpressure

The design uses explicit ownership rather than pulse coupling:

- Soma fire is a held valid/ready record.
- A tile captures each accepted fire once into lockstep learning/fire and
  packet records.
- The packet payload is constructed at physical fire time, so later fires
  cannot overwrite an in-flight packet.
- Dendrite events remain valid with stable payload until Soma accepts them.
- A pending learning fire retains its original physical fire tick.
- Tick and stimulus acceptance are independently queued.

Public diagnostic surfaces include `mesh_overflow_any`, `tile_overflow_any`,
`tile_backpressure`, `tile_busy`, `tile_dend_busy`, the per-tile byte lanes of
`spike_backpressure_count`, protocol errors and unsupported-packet witnesses.

## 8. Verification and reproducibility

### 8.1 Current gate matrix

| Layer | Current scope | Required verdict |
|---|---|---|
| Golden | 55 pytest cases, including the published learning demo | all pass |
| Cocotb | 32 tests in 9 compiled groups | all pass, nonzero tests/group |
| Raw probes | 8 direct Icarus/vvp benches | self-check marker and rc=0 |
| Mutation | 17 targeted RTL faults in 7 groups | every mutant killed; no stale anchor |
| Lint | default 4×256 SoC, Verilator `-Wall` | rc=0, no emitted warnings |
| FIFO formal | legal push/pop environment, occupancy/flags, overflow safety | BMC depth 60 PASS |
| Router formal | legal ingress credits/routing masks, modeled egress credits, PE hold, X-first corner rule, internal overflow | BMC depth 60 PASS |
| Synthesis | CONFIG endpoint and router GF180 mapping; default SoC coarse lowering/check | valid JSON/log receipts and hashes |

The lint command sets `--unroll-count 256` so Verilator releases before 5.026
can elaborate the design's 256-entry nonblocking reset loops. No diagnostic is
waived; current Verilator releases accept the same command.

The FIFO uses Yices and the router uses Bitwuzla through SymbiYosys. Formal
reset is constrained low initially and high thereafter. FIFO data ordering is
tested against a deque for 2,000 simulation cycles rather than encoded as an
SMT array proof. The router proof models finite egress credits and requires
legal upstream credit behavior. These assumptions are part of the claim.

### 8.2 Mutation inventory

The sweep covers FIFO full/push/count faults, router credit/fairness/X-first
faults, CDC Gray/full faults, soma leak/refractory faults, CWR window/expiry
faults, CONFIG commit/order/header faults, and SoC scale/axon-configuration
faults. A timeout counts as a kill only because the injected fault prevents the
target suite from completing inside its established limit; the process group
is terminated and the original source is restored in `finally`.

### 8.3 Reproducible inputs and receipts

`requirements.in` is the human-maintained dependency set.
`requirements-lock.txt` contains the transitive Python resolution with hashes.
The GitHub Actions workflow pins third-party actions by full commit SHA.

`tools/push_and_run.sh` synchronizes a sorted manifest of tracked and
non-ignored new files. Remote simulation, probe, lint, mutation, formal and
synthesis receipts record:

- base Git commit;
- SHA-256 of the working diff;
- SHA-256 of the synchronized source manifest;
- toolchain versions and dependency-lock hash;
- logs/results and their SHA-256 hashes.

A receipt proves only the synchronized source and named tools. A local workflow
file does not prove that hosted CI executed it.

### 8.4 Synthesis snapshot

The verified build box uses Yosys `0.68+50` and the GF180 MCU 7-track 5 V
standard-cell liberty at TT, 25 °C, 5.0 V with an ABC 20 ns target.

| Artifact | Cells | Mapped cell area |
|---|---:|---:|
| `hypha_config_endpoint` | 271 | 10,025.48 µm² |
| `hypha_router` | 2,535 | 91,076.65 µm² |
| default SoC coarse front end | 55,130 | not mapped; memories retained |

The whole-SoC count is a structural elaboration/lowering statistic and is not
comparable to mapped block area.

## 9. Known limits and next gates

The following remain outside the v1 evidence boundary:

1. replace behavioral arrays with selected physical or FPGA memory macros;
2. prove liveness/fairness beyond bounded safety and the corner-router harness;
3. add routed CONFIG read/response and a versioned host driver;
4. use `hypha_sync_fifo` in a real multi-clock top-level integration;
5. run FPGA implementation or ASIC PnR, STA, DRC/LVS and power analysis;
6. compare CWR empirically with named reference learning rules;
7. archive verification receipts with an immutable release revision; and
8. independently reproduce the complete flow on a clean machine.

## 10. References and provenance

- W. Gerstner et al., *Neuronal Dynamics*, Cambridge University Press,
  chapter 1.3, integrate-and-fire models.
- J. K. Eshraghian et al., “Training Spiking Neural Networks Using Lessons
  From Deep Learning,” *Proceedings of the IEEE* 111(9), 2023.
- C. Frenkel et al., “A 0.086-mm² 12.7-pJ/SOP 64k-synapse 256-neuron online-
  learning digital spiking neuromorphic processor,” *IEEE TBioCAS*, 2019.
- C. Frenkel and G. Indiveri, “ReckOn,” ISSCC 2022.
- `lif-tt-asic` and `ed-snn-fpga`, listed with the other audited works in
  `NOTICE.md`.

The audit informed the invariants. No third-party RTL is incorporated into
CeliumNeUR. Exact repositories, commits, trees, license hashes, evidence files
and line ranges are locked and independently checkable in `audit/`; source and
license boundaries are controlled by `NOTICE.md`, not by marketing language in
this contract.
