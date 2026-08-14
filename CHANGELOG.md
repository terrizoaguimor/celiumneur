# Changelog

All notable changes to CeliumNeUR are documented here. The project follows
[Semantic Versioning](https://semver.org/) while the public surface remains in
the `0.y.z` development phase.

## [0.0.2] - 2026-08-13

### Added

- A routed five-flit CONFIG endpoint with transactional state mutation.
- Independent live soma and dendrite readback paths.
- Tick and stimulus queues with explicit backpressure and diagnostics.
- Golden, cocotb, raw-probe, mutation, lint, bounded-formal, and synthesis
  release gates with source-bound receipts.
- A reproducible external design audit and source manifest.
- A literature-informed GPT Image 2 conceptual die visualization with an
  explicit provenance boundary.
- Repository ownership policy through `CODEOWNERS`.

### Changed

- Scaled the default SoC to four 256-neuron tiles and global IDs 0–1023.
- Hardened FIFO, router, CDC, mesh, tile, soma, dendrite, learning, and
  readback behavior around explicit valid/ready invariants.
- Replaced presentation diagrams and executable demo figures so they match
  the current RTL topology and verified traces.
- Locked the Python verification dependency set by hash.

### Fixed

- Removed silent overwrite and discard paths under legal producer behavior.
- Made fire records own both learning and packet side effects under stall.
- Made malformed or incomplete CONFIG traffic fail without mutating state.
- Closed scale-boundary, arithmetic-saturation, stale-mutant, and protocol
  witness gaps found during the full audit.

## [0.0.1] - 2026-08-13

- Initial public research release.

[0.0.2]: https://github.com/terrizoaguimor/celiumneur/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/terrizoaguimor/celiumneur/releases/tag/v0.0.1
