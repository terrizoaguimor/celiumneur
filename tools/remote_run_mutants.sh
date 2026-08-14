#!/usr/bin/env bash
# Run the complete mutation gate and retain a source-bound receipt.
set -euo pipefail
. /home/build/.neuro_env
. /home/build/celiumneur/tools/devbox_env.sh
prepare_cocotb_vvp
trap cleanup_cocotb_vvp EXIT

repo=/home/build/celiumneur
run_id=$(date -u +%Y%m%dT%H%M%SZ)
receipt_dir=/home/build/receipts/celiumneur/mutants/$run_id
mkdir -p "$receipt_dir"
cp "$repo/.source-receipt" "$receipt_dir/source-receipt.txt"

{
  date -u +timestamp=%Y-%m-%dT%H:%M:%SZ
  /home/build/venvs/neuro/bin/python --version
  iverilog -V 2>&1
  sha256sum "$repo/requirements-lock.txt"
} > "$receipt_dir/toolchain.txt"

set +e
(cd "$repo" && /home/build/venvs/neuro/bin/python tools/mutant_sweep.py all) \
  > "$receipt_dir/mutants.log" 2>&1
status=$?
set -e

printf 'exit_status=%s\n' "$status" > "$receipt_dir/status.txt"
sha256sum "$receipt_dir/mutants.log" "$receipt_dir/source-receipt.txt" \
  "$receipt_dir/status.txt" "$receipt_dir/toolchain.txt" \
  > "$receipt_dir/SHA256SUMS"

if [ "$status" -ne 0 ]; then
  echo "MUTATION_FAIL receipt=$receipt_dir" >&2
  exit "$status"
fi
echo "MUTATION_PASS receipt=$receipt_dir"
