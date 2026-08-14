#!/usr/bin/env bash
# Dispatch one already-locked verification mode on the authoritative devbox.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <suite|probes|mutants|lint|formal|synth>" >&2
  exit 2
fi

case "$1" in
  suite|probes|lint)
    exec bash /home/build/celiumneur/tools/remote_run_verify.sh "$1"
    ;;
  mutants)
    exec bash /home/build/celiumneur/tools/remote_run_mutants.sh
    ;;
  formal)
    exec bash /home/build/celiumneur/tools/remote_run_formal.sh
    ;;
  synth)
    exec bash /home/build/celiumneur/tools/remote_run_synth.sh
    ;;
  *)
    echo "unsupported verification mode: $1" >&2
    exit 2
    ;;
esac
