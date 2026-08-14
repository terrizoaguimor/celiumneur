#!/usr/bin/env bash
# Receipt-producing GF180 synthesis run on the authoritative devbox.
set -euo pipefail
. /home/build/.neuro_env

ROOT=/home/build/celiumneur
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RECEIPT=/home/build/receipts/celiumneur/synth/$STAMP
mkdir -p "$RECEIPT"
cd "$ROOT"

if [ ! -f .source-receipt ]; then
  echo "missing .source-receipt; synchronize with push_and_run.sh first" >&2
  exit 2
fi
cp .source-receipt "$RECEIPT/source-receipt.txt"

export SYNTH_OUT_DIR="$RECEIPT"
{
  date -u +timestamp=%Y-%m-%dT%H:%M:%SZ
  yosys -V
  sha256sum requirements-lock.txt
} > "$RECEIPT/toolchain.txt"

bash tools/synth_baseline.sh config_endpoint hypha_config_endpoint \
  rtl/top/hypha_config_endpoint.v

bash tools/synth_baseline.sh router hypha_router \
  rtl/hyphae/hypha_link_fifo.v rtl/hyphae/hypha_router.v

# Whole-chip synthesis front end at the published default 4x256 scale. Keep
# memories as memories here: this receipt proves elaboration/process lowering
# and structural checks, not a macro-free area estimate.
cat > "$RECEIPT/soc_coarse.ys" <<EOF
read_verilog rtl/hyphae/hypha_link_fifo.v rtl/hyphae/hypha_router.v
read_verilog rtl/soma/soma_dendrite.v rtl/soma/soma_core.v rtl/soma/neuro_tile.v
read_verilog rtl/top/hypha_config_endpoint.v rtl/top/hyphae_mesh_2x2.v
read_verilog rtl/top/celiumneur_soc.v
hierarchy -check -top celiumneur_soc
proc; opt; memory_collect; opt; check
tee -o $RECEIPT/soc_coarse.json stat -json
EOF
yosys -l "$RECEIPT/soc_coarse.log" -s "$RECEIPT/soc_coarse.ys" >/dev/null
python3 -m json.tool "$RECEIPT/soc_coarse.json" >/dev/null
sha256sum "$RECEIPT/soc_coarse.log" "$RECEIPT/soc_coarse.json" \
  > "$RECEIPT/soc_coarse.sha256"

sha256sum "$RECEIPT/source-receipt.txt" "$RECEIPT/toolchain.txt" \
  > "$RECEIPT/receipt.sha256"
printf 'SYNTH_PASS receipt=%s\n' "$RECEIPT"
