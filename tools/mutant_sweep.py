# SPDX-License-Identifier: Apache-2.0
"""mutant_sweep.py — gate 4, mechanical: inject one seeded fault (mutant) into
an RTL file at a time, rerun the FULL cocotb suite via run_tests.py (the
proven process configuration), and the suite MUST fail.

A survived mutant means the verification is decorative at exactly that spot.
Policy (verification-gates skill): never patch the DUT to kill a survivor —
the hole is in the tests; strengthen the tests.

Design choice (battle scars logged): the sweep mutates the working tree and
restores it, ALWAYS, even on error (try/finally). This reuses the blessed
runner path instead of a bespoke sim harness whose env-layering already
burned an afternoon, once.

Usage:  python tools/mutant_sweep.py all
        python tools/mutant_sweep.py hypha_router
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "verification" / "cocotb" / "run_tests.py"
MUTANT_TIMEOUT_SECONDS = 10

# (mutant_id, rtl_file_rel_to_rtl, old, new) — anchor old must match 1x.
MUTANTS = {
    "hypha_link_fifo": [
        ("full_off_by_one", "hyphae/hypha_link_fifo.v",
         "assign full  = (count == DEPTH_COUNT);",
         "assign full  = (count == DEPTH_COUNT - 1);"),
        ("push_without_guard", "hyphae/hypha_link_fifo.v",
         "wire do_push = push & ~full;",
         "wire do_push = push;"),
        ("count_down_on_push", "hyphae/hypha_link_fifo.v",
         "2'b10: count <= count + 1'b1;",
         "2'b10: count <= count - 1'b1;"),
    ],
    "hypha_router": [
        ("credit_gate_inverted", "hyphae/hypha_router.v",
         "credits[1] != 0, credits[0] != 0 };",
         "credits[1] != 0, credits[0] == 0 };"),
        ("rr_stuck", "hyphae/hypha_router.v",
         "rr_ptr <= (sel_idx == 3'd4) ? 3'd0 : sel_idx + 3'd1;",
         "rr_ptr <= sel_idx;"),
        ("xfirst_broken", "hyphae/hypha_router.v",
         "if (dx == CORE_X && dy > CORE_Y) branch_mask[d] = 1'b1;",
         "if (dy > CORE_Y) branch_mask[d] = 1'b1;"),
    ],
    "hypha_sync_fifo": [
        ("gray_not_gray", "hyphae/hypha_sync_fifo.v",
         "wire [PTR_BITS-1:0] wr_gray_next = (wr_bin_next >> 1) ^ wr_bin_next;",
         "wire [PTR_BITS-1:0] wr_gray_next = (wr_bin_next >> 1);"),
        ("full_no_complement", "hyphae/hypha_sync_fifo.v",
         "wire full_next = (wr_gray_next == {~rd_gray_w2[PTR_BITS-1:PTR_BITS-2],",
         "wire full_next = (wr_gray_next == {rd_gray_w2[PTR_BITS-1:PTR_BITS-2],"),
    ],
    "soma_core": [
        # leak direction inverted (away from zero instead of toward it)
        ("leak_away_from_zero", "soma/soma_core.v",
         "acc_wide = {v_mem[15], v_mem} + (v_mem[15] ? {1'b0, lmag} : -{1'b0, lmag});",
         "acc_wide = {v_mem[15], v_mem} + (v_mem[15] ? -{1'b0, lmag} : {1'b0, lmag});"),
        # refractory never gates evaluation
        ("refractory_blind", "soma/soma_core.v",
         "if (refr_cnt == 8'd0 && v_next >= theta) begin",
         "if (v_next >= theta) begin"),
    ],
    "soma_dendrite": [
        # LTP window collapsed to same-tick-only.
        ("pot_window_zero", "soma/soma_dendrite.v",
         "<= WINDOW) begin",
         "<= 0) begin"),
        # expiry threshold off by one (>= instead of >)
        ("expiry_window_off_by_one", "soma/soma_dendrite.v",
         "> WINDOW) begin",
         ">= WINDOW) begin"),
    ],
    "hypha_config_endpoint": [
        ("commit_does_not_backpressure", "top/hypha_config_endpoint.v",
         "assign pkt_ready = !commit_pending;",
         "assign pkt_ready = 1'b1;"),
        ("fragment_order_ignored", "top/hypha_config_endpoint.v",
         "|| packet_kind != expected_kind",
         "|| 1'b0"),
        ("nested_header_allowed", "top/hypha_config_endpoint.v",
         "if (transaction_active || pkt_body[6:0] != 7'd0",
         "if (pkt_body[6:0] != 7'd0"),
    ],
    "soc_scale": [
        ("four_neurons_only", "top/celiumneur_soc.v",
         "parameter NEURONS_PER_TILE    = 256,",
         "parameter NEURONS_PER_TILE    = 4,"),
        ("axon_config_ignored", "soma/neuro_tile.v",
         "axon_table[cfg_axon_addr] <= cfg_axon_wdata;",
         "axon_table[cfg_axon_addr] <= axon_table[cfg_axon_addr];"),
    ],
}

# Mutants whose survival is *justified and documented* (reviewed per case,
# not swept under the rug). Each entry carries the reason the check is
# structurally unreachable. Do not add entries to quiet the suite.
KNOWN_SURVIVORS = {}

# suite tag printed by run_tests.py per logical mutant target
SUITE_TAG = {
    "hypha_link_fifo": "hypha_link_fifo",
    "hypha_router": "hypha_router",
    "hypha_sync_fifo": "hypha_sync_fifo",
    "soma_core": "soma_core",
    "soma_dendrite": "neuro_tile",
    "hypha_config_endpoint": "hypha_config_endpoint",
    "soc_scale": "celiumneur_soc",
}


def run_suite_for(module):
    """Returns (suite_rc, verdict_line_for_module)."""
    tag = SUITE_TAG.get(module, module)
    proc = subprocess.Popen(
        [sys.executable, str(RUNNER), tag],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name != "nt"),
    )
    try:
        stdout, _stderr = proc.communicate(timeout=MUTANT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.communicate()
        return 124, [
            f"[FAIL] {tag}: {MUTANT_TIMEOUT_SECONDS}s timeout under mutant"
        ]
    verdict = [ln for ln in stdout.splitlines() if tag in ln]
    return proc.returncode, verdict


def run_group(module):
    """Run one mutation group and return True only when every mutant dies."""
    survivors = []
    skipped = []
    for mid, rel, old, new in MUTANTS[module]:
        target = ROOT / "rtl" / rel
        original = target.read_text()
        if original.count(old) != 1:
            print(f"[SKIP] {mid}: anchor matched {original.count(old)}x (expected 1)")
            skipped.append(mid)
            continue
        try:
            target.write_text(original.replace(old, new))
            rc, verdict = run_suite_for(module)
            failed_early = rc != 0 and any(
                "FAIL" in ln or "ERROR" in ln for ln in verdict
            )
            status = "KILLED" if failed_early else "SURVIVED"
            if status == "SURVIVED" and (module, mid) in KNOWN_SURVIVORS:
                print(f"[JUSTIFIED] {module}/{mid}: {KNOWN_SURVIVORS[(module, mid)]}")
                continue
            print(
                f"[{status}] {module}/{mid} :: "
                f"{verdict[0] if verdict else '(no line)'}",
                flush=True,
            )
            if status == "SURVIVED":
                survivors.append(mid)
        finally:
            target.write_text(original)   # always restore
    total = len(MUTANTS[module])
    killed = total - len(survivors) - len(skipped)
    print(f"\nsummary {module}: {killed}/{total} killed")
    if survivors or skipped:
        if survivors:
            print(f"SURVIVORS: {survivors} — strengthen the tests, never the RTL")
        if skipped:
            print(f"SKIPPED: {skipped} — stale mutation anchors are a gate failure")
        return False
    return True


def main():
    choices = ["all", *MUTANTS]
    if len(sys.argv) != 2 or sys.argv[1] not in choices:
        print(f"usage: {sys.argv[0]} <{'|'.join(choices)}>")
        sys.exit(2)

    selected = MUTANTS if sys.argv[1] == "all" else [sys.argv[1]]
    failed_groups = [module for module in selected if not run_group(module)]
    if failed_groups:
        print(f"\nmutation gate failed: {', '.join(failed_groups)}")
        sys.exit(1)
    print(f"\nmutation gate passed: {len(selected)} group(s)")


if __name__ == "__main__":
    main()
