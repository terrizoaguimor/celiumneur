#!/usr/bin/env bash
# Run one simulation/static gate and retain a source-bound receipt.
set -euo pipefail
. /home/build/.neuro_env
. /home/build/celiumneur/tools/devbox_env.sh
prepare_cocotb_vvp
trap cleanup_cocotb_vvp EXIT

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <suite|probes|lint>" >&2
  exit 2
fi
mode=$1
case "$mode" in
  suite|probes|lint) ;;
  *) echo "unsupported verification mode: $mode" >&2; exit 2 ;;
esac

repo=/home/build/celiumneur
run_id=$(date -u +%Y%m%dT%H%M%SZ)
receipt_dir=/home/build/receipts/celiumneur/verify/${run_id}-${mode}
mkdir -p "$receipt_dir"
cp "$repo/.source-receipt" "$receipt_dir/source-receipt.txt"

{
  date -u +timestamp=%Y-%m-%dT%H:%M:%SZ
  /home/build/venvs/neuro/bin/python --version
  iverilog -V 2>&1
  verilator --version
  sha256sum "$repo/requirements-lock.txt"
} > "$receipt_dir/toolchain.txt"

set +e
case "$mode" in
  suite)
    (cd "$repo" && /home/build/venvs/neuro/bin/python \
      verification/cocotb/run_tests.py) > "$receipt_dir/gate.log" 2>&1
    ;;
  probes)
    (cd "$repo" && /home/build/venvs/neuro/bin/python \
      verification/cocotb/run_tests.py --probes) > "$receipt_dir/gate.log" 2>&1
    ;;
  lint)
    (cd "$repo" && verilator --lint-only -Wall --top-module celiumneur_soc \
      rtl/hyphae/hypha_link_fifo.v rtl/hyphae/hypha_router.v \
      rtl/soma/soma_dendrite.v rtl/soma/soma_core.v rtl/soma/neuro_tile.v \
      rtl/top/hypha_config_endpoint.v rtl/top/hyphae_mesh_2x2.v \
      rtl/top/celiumneur_soc.v) > "$receipt_dir/gate.log" 2>&1
    ;;
esac
status=$?
set -e

printf 'mode=%s\nexit_status=%s\nlog_bytes=%s\n' \
  "$mode" "$status" "$(wc -c < "$receipt_dir/gate.log")" \
  > "$receipt_dir/status.txt"
sha256sum "$receipt_dir/gate.log" "$receipt_dir/source-receipt.txt" \
  "$receipt_dir/status.txt" "$receipt_dir/toolchain.txt" \
  > "$receipt_dir/SHA256SUMS"

cat "$receipt_dir/gate.log"
if [ "$status" -ne 0 ]; then
  echo "VERIFY_FAIL mode=$mode receipt=$receipt_dir" >&2
  exit "$status"
fi
echo "VERIFY_PASS mode=$mode receipt=$receipt_dir"
