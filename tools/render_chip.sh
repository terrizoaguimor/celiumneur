#!/usr/bin/env bash
# Render the human-auditable SoC and tile diagrams from the current contract.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
python3 tools/make_architecture_diagram.py
