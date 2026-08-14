#!/usr/bin/env bash
# Run the Hyphae BMCs and retain complete, source-bound receipts.
set -euo pipefail
source /home/build/.neuro_env

repo=/home/build/celiumneur
formal_dir="$repo/verification/formal"
run_id=$(date -u +%Y%m%dT%H%M%SZ)
receipt_dir="/home/build/receipts/celiumneur/formal/$run_id"
mkdir -p "$receipt_dir"
cp "$repo/.source-receipt" "$receipt_dir/source-receipt.txt"

run_bmc() {
  local name=$1
  local sby_file=$2
  local log="$receipt_dir/$name.log"
  echo "START name=$name utc=$(date -u -Is)" | tee -a "$receipt_dir/summary.txt"
  if (cd "$formal_dir" && sby -f "$sby_file") >"$log" 2>&1; then
    echo "PASS name=$name utc=$(date -u -Is)" | tee -a "$receipt_dir/summary.txt"
  else
    local status=$?
    echo "FAIL name=$name exit=$status utc=$(date -u -Is)" | tee -a "$receipt_dir/summary.txt"
    return "$status"
  fi
}

run_bmc fifo_bmc hypha_link_fifo.sby
run_bmc router_bmc hypha_router.sby
sha256sum "$receipt_dir"/*.log "$receipt_dir/source-receipt.txt" \
  > "$receipt_dir/SHA256SUMS"
echo "FORMAL_PASS receipt=$receipt_dir"
