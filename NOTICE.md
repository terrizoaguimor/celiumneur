# NOTICE — CeliumNeUR



Licensed: source code under AGPL-3.0-or-later (`LICENSES/AGPL-3.0.txt`);
documentation and artwork under CC BY 4.0 (`LICENSES/CC-BY-4.0.txt`).

## Acknowledgements and independent-work statement

This project's RTL was written from scratch. It was CONCEIVED against a
structural audit of published open designs, listed here with respect and
gratitude; no RTL from them was copied:

- ODIN — C. Frenkel, M. Lefebvre, J.-D. Legat, D. Bol, IEEE TBioCAS 13(1),
  2019 (arXiv:1804.07858). HDL released under Solderpad Hardware License
  2.0 (UCLouvain). Audited; informed our invariants via its weaknesses.
- ReckOn — C. Frenkel, G. Indiveri, ISSCC 2022. HDL released under
  Solderpad Hardware License 2.1 (University of Zurich). Audited.
- Event-Driven Spiking Neural Network Accelerator for FPGA — J. Lee
  (Kwangwoon University), MIT license. Audited.
- lif-spiking-neural-network — I. Stankulov (TinyTapeout GF180),
  Apache-2.0. Audited; its extrema are why our specification exists.

Nothing in this notice grants rights to their works; those remain under
their licenses and authors.

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
