# NOTICE — CeliumNeUR



Licensed: source code under Apache-2.0 (`LICENSES/Apache-2.0.txt`);
documentation and artwork under CC BY 4.0 (`LICENSES/CC-BY-4.0.txt`).

## Acknowledgements and independent-work statement

This project's RTL was written from scratch. It was CONCEIVED against a
structural audit of published open designs, listed here with respect and
gratitude; no RTL from them was copied:

- ODIN — C. Frenkel, M. Lefebvre, J.-D. Legat, D. Bol, IEEE TBioCAS 13(1),
  2019 (arXiv:1804.07858). HDL released under Solderpad Hardware License
  2.0 (UCLouvain). Audited; its structural tradeoffs informed our invariants.
- ReckOn — C. Frenkel, G. Indiveri, ISSCC 2022. HDL released under
  Solderpad Hardware License 2.1 (University of Zurich). Audited.
- Event-Driven Spiking Neural Network Accelerator for FPGA — J. Lee
  (Kwangwoon University), MIT license. Audited.
- lif-spiking-neural-network — I. Stankulov (TinyTapeout GF180),
  Apache-2.0. Audited; its extrema are why our specification exists.

Nothing in this notice grants rights to their works; those remain under
their licenses and authors.

The exact repositories, commits, Git trees, license hashes, evidence-file
hashes and line-range hashes are locked in
[`audit/source_snapshot.lock.json`](audit/source_snapshot.lock.json). The
interpretation and clean-checkout reproducer are in [`audit/`](audit/README.md).
No third-party RTL is stored in this repository.

## References on which the engineering semantics stand

- W. Gerstner, W. Kistler, R. Naud, L. Paninski, *Neuronal Dynamics*,
  Cambridge Univ. Press, Ch. 1.3.
- J. K. Eshraghian et al., "Training SNNs Using Lessons From Deep
  Learning", Proc. IEEE 111(9), 2023; snnTorch docs.
- Glass & Ni, "The Turn Model for Adaptive Routing", ISCA 1992;
  Dally & Seitz, IEEE TC C-36(5), 1987.
- C. Cummings, SNUG 2002 async-FIFO canon (Sunburst Design).
- Song, Miller & Abbott, "Competitive Hebbian learning through STDP",
  Nat. Neurosci. 3:919-926, 2000.
- Bellec et al., "A solution to the learning dilemma for spiking RNNs",
  Nat. Commun. 11:3625, 2020 (e-prop; roadmap §5.8).

Verification record and debt: see SPEC.md.

## Bundled presentation runtime

`render/html/` includes selected unmodified Three.js runtime and example
modules solely for the interactive chip visualization. They remain © Three.js
authors and are distributed under the MIT license; the exact notice is in
`render/html/THIRD-PARTY-NOTICES.md`. These files are not CeliumNeUR RTL and
the project's Apache-2.0 license does not replace their upstream license.

The OSS CAD Suite may be installed locally by the bootstrap tooling but is not
tracked or redistributed by this repository. Icarus Verilog, Verilator,
Yosys, SymbiYosys, solvers and PDK content retain their own upstream licenses.
