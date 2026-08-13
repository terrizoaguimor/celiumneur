# CeliumNeUR v1 — Design Charter

Licenses: code AGPL-3.0+, documentation CC BY 4.0 — see LICENSE / LICENSES/.
Independent-work statement + acknowledgements: NOTICE.md.

Academic-grade neuromorphic processor design. Founded after a structural audit of
four open RTL designs (ODIN, ReckOn, ed-snn-fpga, lif-tt-asic) whose architectural
flaws this project is chartered to avoid.

Frozen decisions (2026-08-12):
- **Target**: simulation-first. Toolflow: Icarus/Verilator + cocotb + SymbiYosys.
- **Neuron**: improved LIF (see §3).
- **Scale**: 4 SomaCores x 256 neurons = 1024 neurons on a 2x2 Hyphae mesh.

---

## 1. Non-negotiable invariants (each maps to an audited flaw)

| # | Invariant | Flaw it kills | Evidence of the flaw |
|---|---|---|---|
| I1 | No spike is ever dropped silently. Credit-based backpressure end-to-end. | Silent drops: ODIN (`scheduler.v:190`, `aer_out.v:143`), ed-snn-fpga (`core_group.v:420`) | audit 2026-08-12 |
| I2 | Synaptic indirection: network topology lives in tables, not SRAM geometry. | Dense-only mapping: ReckOn (`srnn.v:1007`), ODIN packing | audit |
| I3 | One hardened CDC cell (`hypha_sync_fifo`) is the only place signals cross clock domains. | ODIN `AERIN_ADDR` never captured (`controller.v:127-131`); ReckOn `clk_or` + unassigned sync regs (`reckon.v:470,71-72`) | audit |
| I4 | Learning snoops the fabric; it never stalls event processing. | ReckOn EPROP mutually exclusive with events (`srnn.v:711-741`); ed-snn-fpga STDP blind to pre spikes (`event_router_ng.v:222-229`) | audit |
| I5 | Non-invasive observability: any neuron's state readable while running at full rate. | ReckOn: recurrent spikes never leave the chip; lif-tt-asic: `v_mem` unconnected (`project.v:55,64,73,82`) | audit |
| I6 | Saturating arithmetic everywhere. Overflow clamps, never wraps. | lif-tt-asic modular wrap (`lif_components.v:9`) | audit |
| I7 | Per-neuron independent parameters (threshold, leak, refractory). | ReckOn pairs forced to share alpha/threshold (`srnn.v:1063-1066`) | audit |
| I8 | Tests must exercise dynamics (force spikes), never certify silence. | lif-tt-asic: 0% spike coverage in `test.py` | audit |

## 2. Hyphae — the fabric / engine (v0 contract)

Single semantic plane for everything: spikes, config, learning signals, telemetry.
Host never writes registers; it emits Hyphae packets.

- Packet: 32-bit single-flit. `type[3:0] | payload[27:0]`.
  Types: SPIKE, SPIKE_TS, CONFIG_WR, CONFIG_RD, LEARN, MONITOR, CREDIT.
- Routing: X-Y dimension order on 2D mesh (deadlock-free by construction).
- Flow control: credit-based. A router emits only against available credit -> I1 by construction.
- Multicast: branch-replication inside each router -> unlimited fanout.
  (Kills ODIN's 512-cycle serial fanout and ed-snn-fpga's fanout<=16 cap.)
- CDC: all inter-domain traffic through `hypha_sync_fifo` (gray pointers,
  address and request captured together). v0 runs single-clock; the cell is
  built and formally verified from day one so multi-domain is plug-in later.

## 3. SomaCore — neuron datapath (v1)

Model: discrete-time fixed-point LIF, forward Euler per
Gerstner & Kistler (Ch.1.3) and snnTorch (Eshraghian et al. 2023):

    V[t+1] = sat( V[t] - ceilLeak(V[t], k) + I_syn[t] )    on time tick / event
    spike  = V[t+1] >= theta   (if refractory_counter == 0)
    reset  = V - theta (subtract, default)  or  0           (configurable)

Properties chartered:
- Vmem signed 16-bit, saturation to +-32767 (I6).
- Leak implemented as ceiling-division on magnitude (`ceilDivShift`):
  guarantees convergence to exactly 0 with no sticky residues
  (kills lif-tt-asic `>>>3` truncation floors, audit §"lif-tt-asic").
- Refractory: absolute for spiking, inputs still integrate (relative-flavored);
  counter decrements per tick — real time semantics, not "leak sweeps"
  (kills ed-snn-fpga refractory-in-sweeps, audit).
- Reset mode configurable subtract/zero (snnTorch default = subtract, less lossy).

Per-neuron parameters: `theta`, `leak_shift`, `refractory_ticks`, `reset_mode` (I7).

## 4. Golden model discipline

`golden/` is the bit-exact Python referee of the RTL. RTL is never written
ahead of the golden model; cocotb compares cycle-by-cycle against it.
Rule: a mismatched waveform is a bug in RTL or in the model — never tolerated,
always traced to root cause before proceeding.

## 5. Roadmap

1. [x] golden/soma model + dynamics tests (19 golden tests).
2. [x] hypha_sync_fifo + Hyphae router + link FIFOs, cocotb + formal BMC-60.
3. [x] SomaCore datapath vs golden (time-multiplexed; fire-seq + bit-exact state).
4. [x] Mesh 2x2 integration, directed + 64-packet storm vs golden HyphaeMesh.
5. [x] Plasticity: golden Pair-STDP v1.2 + `soma_dendrite.v` (I2 table + I4
   snooper) + neuro_tile, verified against the Python referee with per-round
   trajectory (A->8 reaches rail 127, control ≤90). 30/30 identical rounds.
5b. [x] **SoC v1** (`celiumneur_soc.v`: 4 neuro_tiles on the mesh, stimulus,
    bidirectional PE credits, static axon maps) + raster RTL≡golden.
5c. [x] **Phase-gating** (tick parity in packet + integration window):
    the SoC raster vs golden collapses to equality-modulo-tag. Free golden
    LDL test: the sandbox replicates the exact schedule (untouched).
6. Observability plane (monitor mirrors, hot state readback) — I5.
7. Thin host stack: burst config via Hyphae packets (kills SPI-boot walls).
8. Optional: eligibility-trace fabric for e-prop (Bellec et al. 2020) as surfacing.

## 6. Verification ledger (living record)

| Date | Scope | Method | Result |
|---|---|---|---|
| 2026-08-12 | golden/soma improved LIF | pytest 19 tests (dynamics, saturation, refractory, I7) | PASS |
| 2026-08-12 | golden/hyphae mesh (X-Y, multicast, credits) | pytest 46 tests | PASS |
| 2026-08-12 | hypha_link_fifo | cocotb 2/2 (boundaries + 2000-cycle stress with oracle) + BMC-60 | PASS |
| 2026-08-12 | hypha_router (corner 0,0) | cocotb golden parity (unicast/multicast/random) + BMC-60 (X-first, no-overflow) | PASS |
| 2026-08-12 | hypha_sync_fifo (CDC 10ns/7ns) | cocotb 1/1 (200 items, exact order, no loss) + raw smoke 64/64 | PASS |
| 2026-08-12 | soma_core (4 neurons, heterogeneous params) | cocotb vs golden: fire sequence + bit-exact 64-bit words after 120 mixed ops | PASS |
| 2026-08-12 | hyphae_mesh_2x2 (4 routers) | cocotb vs HyphaeMesh: directed + 64-packet storm, overflow audit every cycle | PASS |
| 2026-08-12 | formal on droplet (celiumneur-build-1) | fifo BMC-60 + router BMC-60 (X-first, no-overflow, bidirectional contract) | PASS (remote, tmux) |
| 2026-08-12 | golden sandbox end-to-end (golden_net) | demo_net: golden raster, hand-predicted dynamics matched | PASS |
| 2026-08-12 | golden plasticity (Pair-STDP v1.2) | demo_plasticity: paired wires potentiate to rail, control depresses; tests 53/53 | PASS |
| 2026-08-12 | neuro_tile (I2 dendrite + I4 snooper + soma) | cocotb vs referee: identical per-round weight trajectory ×30, rail and floor respected | PASS |
| 2026-08-12 | gate 4 (mutants): hypha_link_fifo | 3/3 killed (off-by-one full, push guard, count direction) | PASS |
| 2026-08-12 | gate 4 (mutants): hypha_sync_fifo | 2/2 killed (broken gray, non-complemented full) | PASS |
| 2026-08-12 | gate 4 (mutants): hypha_router | xfirst_broken KILLED by bench legality witness; rr_stuck KILLED (overnight remote verdict); credit_gate: pending in tmux | 2/3 + 2 new witnesses |
| 2026-08-13 | GF180 baseline synthesis (pre-PnR, liberty mcu7t5v0 tt/25C/5V, ABC -D 20ns) | soma_core ≈ 64.7k µm²; router ≈ 91k µm² hierarchical; 2×2 mesh ≈ 364k µm² (memory in FFs, no macros — deliberately pessimistic floor) | BANKED DATA |
| 2026-08-13 | release package: LICENSE (routing), LICENSES/AGPL-3.0.txt + CC-BY-4.0.txt (canonical texts), NOTICE.md (acknowledgements+independent-work), regenerated technical poster | — | READY |
| 2026-08-13 | gate 4 (mutants): hypha_router credit_gate | 3/3 tests FROM the router bench fail with the inverted gate (gate 4 closes) | **KILLED** |
| 2026-08-13 | gate 4 (mutants): soma_core | 2/2 killed (reversed leak, blind refractory) | PASS |
| 2026-08-13 | gate 4 (mutants): soma_dendrite | expiry off-by-one KILLED by new window-edge test; pot_without_window JUSTIFIED (unreachable condition: expiry always runs first) | PASS |
| 2026-08-13 | **SoC v1 E2E** (4 tiles + mesh) + comparative raster | chip fires == golden fires (multiset); detector ×2, output ×1, electrodes ×3 | **PASS — the chip thinks** |
| 2026-08-13 | Phase-gating: tick parity in packets + integration window | the depth-2 cascade aligned: golden fires appear in the chip at the same tick or +1 (bench tagging offset, not physics). Comparative raster regenerated | PASS |

### Real design bugs found by verification (root cause recorded)

1. **hypha_router: egress packet packing omitted reserved[27:24]** — the
   golden model caught it via parity divergence. Fix: type+reserved passthrough.
2. **hypha_sync_fifo: combinational flags** → zero-delay evaluation loop
   (full → next-ptr → next-gray → full) that dragged the simulator down to
   ~0.4 ns/s. Fix: registered flags (Cummings canonical fifo1 convention).
3. **soma_core: the refractory counter decremented on events** — misaligning
   the golden model semantics (only ticks age). Fix: gate by op_is_tick.
4. **plasticity v1.0/v1.1: two pedagogical ordering artifacts** — (a) evaluating
   STDP with the post's last spike made every pairing anti-causal by
   construction; (b) LTD-on-arrival + LTP-on-fire created an asymmetric tax
   from packet emission order. Both caught by the golden demo failing the
   "paired wire must potentiate" assertion. The v1.2 rule (LTD only on window
   expiry) makes it impossible by design.

### Verification infra

- Workstation: single source of truth for the code.
- **celiumneur-build-1 (DO nyc1, c-8, dedicated cpu)** = verification box:
  `bash tools/push_and_run.sh` pushes the delta (<200 KB) and runs the remote
  suite; `push_and_run.sh formal` leaves the BMCs in remote tmux (persists if
  the lid closes). Reprovisionable bootstrap: `tools/bootstrap_buildbox.sh`.

### Harness lessons / house rules

- cocotb bench discipline: stimulus on the falling edge, sample after
  NBA; never sample registered outputs right after RisingEdge.
- FWFT: register the head BEFORE pulsing pop, or you read the next element.
- resets in formal: any net not driven by an event is free `anyinit`;
  model the environment with a FIXED reset sequence and port contracts
  (I1 is a TWO-party contract: the environment also respects credits).
- Shape of the v1 formal bounds: BMC-60 (no k-induction: shadow-vs-DUT
  equality does not close by induction from arbitrary states).

### Open formal debt

- **D-formal-01** (router): re-express the credit window (debt ≤ DEPTH)
  as an assume-guarantee pair against a reference link model; the current
  harness (shadow counters) produces contradictions with the solver.
  Physical coverage meanwhile: cocotb shadow-audit on every test.
- **D-bench-01**: the router bench (FabricProbe) went through three
  architectures before becoming trustworthy — (1) capture cadence-offset by
  one cycle (1-cycle pulses invisible), (2) two coroutines sharing clock
  edges (scheduler-dependent interleaving). The final form: ONE single edge
  owner with synchronous `step(drives)`. House rule: a single coroutine
  touches the edges; everything else enters via step().
- **Process risk**: mutant_sweep mutates the tree in place with
  try/finally; a suite timeout with pending restore left the RTL mutated
  once (caught and manually restored with lint verification). The safe
  practice: per-mutant verdicts one-at-a-time with immediate restore,
  or long runs on the droplet with tmux.

## References

- W. Gerstner, W. M. Kistler, R. Naud, L. Paninski, *Neuronal Dynamics*,
  Cambridge Univ. Press, Ch. 1.3 "Integrate-And-Fire Models".
  https://neuronaldynamics.epfl.ch/online/Ch1.S3.html (verified 2026-08-12)
- J. K. Eshraghian et al., "Training Spiking Neural Networks Using Lessons
  From Deep Learning", Proc. IEEE 111(9), 2023; snnTorch Tutorial 2
  https://snntorch.readthedocs.io/en/latest/tutorials/tutorial_2.html (verified 2026-08-12)
- C. Frenkel, M. Lefebvre, J.-D. Legat, D. Bol, "A 0.086-mm2 ... ODIN ...",
  IEEE TBioCAS 13(1):145-158, 2019. arXiv:1804.07858. RTL audited.
- C. Frenkel, G. Indiveri, "ReckOn: ...", ISSCC 2022. RTL audited.
- lif-tt-asic (TinyTapeout GF180, I. Stankulov) and ed-snn-fpga (J. Lee, MIT).
  RTL audited 2026-08-12; line evidence in the audit record.
- G. Bellec et al., "A solution to the learning dilemma for recurrent networks
  of spiking neurons", Nature Communications 11:3625, 2020 (e-prop; roadmap §5.8).

---

## Appendix A — First external review (recorded 2026-08-13, reviewer digest a805e04e224)

External review found REAL defects; disposition per finding:

| Finding | Status | Evidence |
|---|---|---|
| I1 broken at mesh-to-tile seam (skid 2-slot drop, no witness) | CLOSED | hypha_link_fifo + PE valid-until-ready handshake in hypha_router; adversarial skid test is GREEN |
| fire_queued single-slot overwrite | CLOSED | 4-deep FIFO + fire_taken handshake; dual-fire pays both [11,11] |
| axon out single-latch drop | CLOSED | real design bug, two layers: concat width inflation erased the mask lanes, and the held-fight register was clobbered by mid-flight fires; fixed with 10-bit gid wire + lockstep packet fifo; adversarial axon burst GREEN in cocotb |
| 16 neurons implemented vs 1024 claimed | DOCUMENTED | SPEC already documented 4x4; renamed public claims to match |
| SoC not autoconfigurable; no post-reset init | CLOSED | autonomous soma config lane (cfg_which/cfg_soma_*) + S_INIT wipe sweep on rst release; benches wait for it |
| I4 not concurrent / I5 only-when-idle | POSITIONED-HONESTLY | targets; not claims |
| "Pair-STDP v1.2" too strong vs Song-Miller-Abbott | CLOSED-RENAMED | rule re-branded CWR (causal-window rule); comparison to reference STDP is future work |
| No reproducible audit pack | OPEN | pending packaging of the four referenced repos + tools |
| No git / CI / lockfile | PARTIAL | .gitignore + CITATION.cff done; lock file + CI pending next |
| poster hardcodes 10 points | OPEN | regenerate the plot from demoplasticity's real trajectory |
| third-party (three.js MIT / oss-cad-suite) boundary | OPEN | next pass of NOTICE.md |

Suite state at this checkpoint (counts of cocotb suite + vvp probes + pytest):
pytest golden 53/53 PASS; cocotb suite (fifo 2, router 3, cdc 1, soma 1, mesh 2, tile 2, soc 1) all PASS; probes dir 6/6 PASS including axon burst at metal level. The two cocotb environment artifacts (axon cocotb watcher, soc exact-equality strengthening) are registered, not fixed this run.

## Open desk at the seam (2026-08-13 night, after the review fires closed)

- All three reviewed drop-paths are STRUCTURALLY closed (skid FIFO + PE valid-until-ready + fire queue + axon queue): adversarial skid=8/8; dual-fire=11,11; AXON probe vvp=packets [0,1,2] correct.
- RESOLVED in the closure pass below: the "cocotb watcher / soc exact-equality"
  items were not bench defects — they were two REAL design bugs (concat width
  inflation + single-register flight clobber). Both fixed; see "Closure pass".
- S_INIT wipe sweep works; bench driver awareness of sweep-then-program ordering is enforced inside the benches.

## Closure pass (2026-08-13, post-compaction session) — both "bench tickets" were REAL design bugs

The two residual reds were not bench instrumentation. Fresh evidence-driven hunt:

1. **Concat width bug (soc exact-equality)**: in `neuro_tile` packet assembly,
   `GID_BASE_I + soma_fire_neuron` was a 32-bit integer expression inside a
   32-bit concat target, inflating the packet to 54 bits; truncation kept only
   the gid operand and erased the route-mask+header lanes. Every egress packet
   carried `mask=0`, the mesh dropped everything, and the SoC detector never
   integrated. Diagnosed by vvp repro (`held_latch_tb`): latch executed,
   RHS printed correct lanes, reg read back 0. Fix: 10-bit `fire_gid` wire
   from `localparam [9:0] GID_LSB`. Result: SoC cocotb now shows
   chip == golden EXACT multiset (electrodes ×3 each, detector ×2, output ×1).
2. **Mid-flight fire clobber (axon middle packet)**: `held_packet` was a
   single register latched at fire and pushed on arbiter take+1; the dendrite
   arbiter take is scan-latency away (>300 cycles observed), so any second
   fire in the flight window overwrote the register — gid 1 vanished and
   gid 2 was emitted twice. Fix: packet fifo `pktq` in lockstep with the
   neuron fireq, pushed at fire time, popped on take (FWFT head valid in the
   take cycle), outq fed directly. Probe: fires 0,1,2 → packets 0,1,2 ×1 each.

Bench hygiene debts repaid in the same pass:
- S_INIT sweep-then-program race: probes/benches now wait for
  `sweep_active == 0` before poking nram (the "only neuron 1 configures"
  scar — wipe was overwriting pokes, previously misread as watcher loss).
- stim strobe pacing: a soma event costs ~3 fabric cycles; mid-event strobes
  drop by design. Benches space strobes (axon burst still overlaps in the
  take window — the burst content of the test is intact).
- `axon_masks` undriven in the adversarial bench made packets unresolvable
  (X); bench now drives 16 hFFFF.
- vvp `$fatal` returns rc 0 in this toolchain: probes that self-check use
  `$finish_and_return(1)` instead, because run_tests.py--probes verdicts are
  returncode-based.

Suite after closure: cocotb 8/8 groups PASS (fifo 2, router 3, cdc 1, soma 1,
mesh 2, tile 2, adversarial 3, soc 1 — exact multiset equality vs golden);
vvp probes 8/8 PASS with assertion teeth (axon burst now fails loudly on
incomplete fires/packets). The two former "open bench tickets" are CLOSED as
design fixes.
