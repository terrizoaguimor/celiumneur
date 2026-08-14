#!/usr/bin/env bash
# push_and_run.sh — single-source-of-truth loop for CeliumNeUR:
# local edit (authoritative tree on the workstation) -> push delta -> the
# droplet is always what verifies. Usage, from the celiumneur dir:
#   bash tools/push_and_run.sh            # push + full cocotb suite
#   bash tools/push_and_run.sh probes     # push + self-checking raw-vvp probes
#   bash tools/push_and_run.sh mutants    # push + mutation gate receipt
#   bash tools/push_and_run.sh lint       # push + Verilator receipt
#   bash tools/push_and_run.sh synth      # push + GF180 synthesis receipts
#   bash tools/push_and_run.sh formal     # push + formal BMCs (tmux, long)
set -euo pipefail

DROPLET="build@159.223.142.34"
KEY="$HOME/.ssh/celiums-workers"
SRC="/mnt/c/Users/Mario/Documents/neuromorphic/celiumneur"

ssh -i "$KEY" -o BatchMode=yes "$DROPLET" true  # fail fast if unreachable

tmp=$(mktemp)
file_list=$(mktemp)
trap 'rm -f "$tmp" "$file_list"' EXIT

# Transfer tracked files plus non-ignored new source files. This keeps .git,
# local tool bundles, caches and receipts outside the synchronization boundary
# without silently omitting a new RTL or test file from verification.
(cd "$SRC" && git ls-files -co --exclude-standard -z | LC_ALL=C sort -z) \
    > "$file_list"
tar --null -czf "$tmp" -C "$SRC" -T "$file_list"

base_commit=$(cd "$SRC" && git rev-parse HEAD)
working_diff_sha256=$(cd "$SRC" && git diff --binary HEAD -- . | sha256sum | cut -d' ' -f1)
source_manifest_sha256=$(
    cd "$SRC"
    xargs -0 sha256sum < "$file_list" | sha256sum | cut -d' ' -f1
)

scp -q -i "$KEY" "$tmp" "$DROPLET:/tmp/celiumneur_push.tgz"
ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
    "cd /home/build/celiumneur && \
     tar xzf /tmp/celiumneur_push.tgz && rm /tmp/celiumneur_push.tgz && \
     printf 'base_commit=%s\nworking_diff_sha256=%s\nsource_manifest_sha256=%s\n' \
       '$base_commit' '$working_diff_sha256' '$source_manifest_sha256' \
       > .source-receipt"

mode="${1:-suite}"
if [ "$mode" = "formal" ]; then
    session="celiumneur-formal-$(date -u +%Y%m%dT%H%M%SZ)"
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "tmux new-session -d -s '$session' \
          'bash /home/build/celiumneur/tools/remote_run_formal.sh'; \
         tmux has-session -t '$session'; echo formal_session='$session'"
elif [ "$mode" = "mutants" ]; then
    session="celiumneur-mutants-$(date -u +%Y%m%dT%H%M%SZ)"
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "tmux new-session -d -s '$session' \
          'bash /home/build/celiumneur/tools/remote_run_mutants.sh'; \
         tmux has-session -t '$session'; echo mutation_session='$session'"
elif [ "$mode" = "synth" ]; then
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "bash /home/build/celiumneur/tools/remote_run_synth.sh"
elif [ "$mode" = "probes" ]; then
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "bash /home/build/celiumneur/tools/remote_run_verify.sh probes"
elif [ "$mode" = "lint" ]; then
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "bash /home/build/celiumneur/tools/remote_run_verify.sh lint"
else
    ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
        "bash /home/build/celiumneur/tools/remote_run_verify.sh suite"
fi
