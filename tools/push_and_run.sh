#!/usr/bin/env bash
# push_and_run.sh — single-source-of-truth loop for CeliumNeUR:
# local edit (authoritative tree on the workstation) -> push delta -> the
# droplet is always what verifies. Usage, from the celiumneur dir:
#   bash tools/push_and_run.sh            # push + full cocotb suite
#   bash tools/push_and_run.sh probes     # push + self-checking raw-vvp probes
#   bash tools/push_and_run.sh mutants    # push + mutation gate receipt
#   bash tools/push_and_run.sh lint       # push + Verilator receipt
#   bash tools/push_and_run.sh synth      # push + GF180 synthesis receipts
#   bash tools/push_and_run.sh formal     # push + formal BMCs
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

mode="${1:-suite}"
run_token="$(date -u +%Y%m%dT%H%M%SZ)-$$"
remote_archive="/tmp/celiumneur_push_${run_token}.tgz"

scp -q -i "$KEY" "$tmp" "$DROPLET:$remote_archive"

# Extraction, source-receipt creation and the complete gate share one remote
# lock. Mutation tests therefore cannot modify the authoritative checkout
# while formal, synthesis or simulation is copying or reading it. A unique
# upload path also prevents concurrent callers from overwriting an archive.
ssh -i "$KEY" -o BatchMode=yes "$DROPLET" \
    "flock -x /home/build/celiumneur.verify.lock bash -s -- \
      '$remote_archive' '$base_commit' '$working_diff_sha256' \
      '$source_manifest_sha256' '$mode'" <<'REMOTE'
set -euo pipefail

archive=$1
base_commit=$2
working_diff_sha256=$3
source_manifest_sha256=$4
mode=$5
repo=/home/build/celiumneur

trap 'rm -f -- "$archive"' EXIT
cd "$repo"
tar xzf "$archive"
printf 'base_commit=%s\nworking_diff_sha256=%s\nsource_manifest_sha256=%s\n' \
  "$base_commit" "$working_diff_sha256" "$source_manifest_sha256" \
  > .source-receipt
bash tools/remote_dispatch.sh "$mode"
REMOTE
