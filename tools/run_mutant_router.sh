#!/usr/bin/env bash
# Overnight: close the two pending router mutant verdicts (rr_stuck,
# credit_gate_inverted). Patches in place, runs ONLY the router case, always
# restores (trap). Verdicts land in /home/build/overnight_mutants.log.
set -u
source /home/build/.neuro_env
cd /home/build/celiumneur || exit 2
F=rtl/hyphae/hypha_router.v
cp "$F" /home/build/router_backup.v
trap 'cp /home/build/router_backup.v "$F"' EXIT

run_case() {
    /home/build/venvs/neuro/bin/python verification/cocotb/run_tests.py hypha_router \
        | grep -E "\[PASS\]|\[FAIL\]"
}

{
echo "=== overnight mutants router $(date -Is)"
sed -i "s/rr_ptr <= (sel_idx == 3'd4) ? 3'd0 : sel_idx + 3'd1;/rr_ptr <= sel_idx;/" "$F"
echo "mutant rr_stuck installed"; run_case
cp /home/build/router_backup.v "$F"
sed -i "s/credits\[1\] != 0, credits\[0\] != 0 };/credits[1] != 0, credits[0] == 0 };/" "$F"
echo "mutant credit_gate installed"; run_case
cp /home/build/router_backup.v "$F"
grep -n "credits\[0\]" "$F"
echo "=== done $(date -Is)"
} >> /home/build/overnight_mutants.log 2>&1
