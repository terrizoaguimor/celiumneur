#!/usr/bin/env bash
# push_and_run.sh — single-source-of-truth loop for CeliumNeUR:
# local edit (authoritative tree on the workstation) -> push delta -> the
# droplet is always what verifies. Usage, from the celiumneur dir:
#   bash tools/push_and_run.sh            # push + full cocotb suite
#   bash tools/push_and_run.sh formal     # push + formal BMCs (tmux, long)
set -euo pipefail

DROPLET="build@159.223.142.34"
KEY="$HOME/.ssh/celiums-workers"
SRC="/mnt/c/Users/Mario/Documents/neuromorphic/celiumneur"

ssh -i "$KEY" -o BatchMode=yes "$DROPLET" true  # fail fast if unreachable

tmp=$(mktemp)
tar czf "$tmp" -C "$SRC" \
    --exclude=.venv --exclude=.pytest_cache --exclude=__pycache__ \
    --exclude=verification/cocotb/sim_build --exclude=verification/cocotb/suite.log \
    --exclude=tools/oss-cad-suite --exclude=tools/oss-cad-suite.tgz \
    .
scp -q -i "$KEY" "$tmp" "$DROPLET:/tmp/celiumneur_push.tgz"
rm -f "$tmp"
ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
    "cd /home/build/celiumneur && tar xzf /tmp/celiumneur_push.tgz && rm /tmp/celiumneur_push.tgz"

if [ "${1:-suite}" = "formal" ]; then
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "tmux new-session -d -s formal bash /home/build/run_formal.sh 2>/dev/null || true; echo formal: tmux session \$(tmux ls 2>/dev/null | grep formal)"
else
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "cd /home/build/celiumneur && . /home/build/.neuro_env && /home/build/venvs/neuro/bin/python verification/cocotb/run_tests.py" \
        | grep -E '\[PASS\]|\[FAIL\]|\[ERROR\]'
fi
