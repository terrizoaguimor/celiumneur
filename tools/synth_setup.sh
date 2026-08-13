#!/usr/bin/env bash
# LibreLane + GF180 PDK setup on the build box. Idempotent; logs to LOG.
set -uo pipefail
LOG=/home/build/synth_setup.log
{
  echo "=== synth setup $(date -Is)"
  export PATH=/home/build/.local/bin:/opt/oss-cad-suite/bin:$PATH
  uv --version || exit 3
  uv pip install --python /home/build/venvs/neuro/bin/python librelane volare || exit 4
  /home/build/venvs/neuro/bin/volare enable --pdk gf180mcu gf180mcuD || exit 5
  echo SETUP_DONE
} >> "$LOG" 2>&1
