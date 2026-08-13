#!/usr/bin/env bash
# yosys synthesis baseline for CeliumNeUR blocks on GF180 (pre-PnR evidence).
# Usage: synth_baseline.sh <name> <top_module> <verilog files...>
# Writes /home/build/synth/<name>.log (yosys -l) and <name>.json (stat -json),
# then prints: cell count / total area / ABC longest-path vs 20 ns target.
set -euo pipefail
NAME=$1; TOP=$2; shift 2
LIB=/home/build/.volare/volare/gf180mcu/versions/c6d73a35f524070e85faff4a6a9eef49553ebc2b/gf180mcuA/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_5v00.lib
export PATH=/opt/oss-cad-suite/bin:$PATH
mkdir -p /home/build/synth
OUT=/home/build/synth/${NAME}.log
JSN=/home/build/synth/${NAME}.json
cat > /tmp/${NAME}_synth.ys <<EOF
read_liberty -lib $LIB
read_verilog $@
hierarchy -check -top $TOP
proc; opt; fsm; opt; memory; opt
techmap; opt
dfflibmap -liberty $LIB
abc -liberty $LIB -D 20000
stat -liberty $LIB
EOF
yosys -l "$OUT" -s /tmp/${NAME}_synth.ys
export LIB_FILE="$LIB"
echo "--- metrics for $NAME:"
grep -aE "Number of cells|Chip area|ABC: Delay" "$OUT" | tail -6
