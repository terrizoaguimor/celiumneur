# SPDX-License-Identifier: AGPL-3.0-or-later
"""CeliumNeUR cocotb entrypoint (Icarus backend, no makefiles).

Usage: .venv/Scripts/python verification/cocotb/run_tests.py
"""

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parent) + os.pathsep + os.environ.get("PYTHONPATH", "")

try:
    from cocotb_tools.runner import get_runner
except ImportError:  # cocotb 1.x layout
    from cocotb.runner import get_runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RTL = ROOT / "rtl" / "hyphae"

FIFO_SOURCES = [RTL / "hypha_link_fifo.v"]
ROUTER_SOURCES = [RTL / "hypha_link_fifo.v", RTL / "hypha_router.v"]

BUILD_ARGS = ["-g2005"]


def run_case(runner, sources, toplevel, test_module, hdl_top=None):
    build_dir = HERE / "sim_build" / toplevel
    top = hdl_top or toplevel
    runner.build(sources=sources, hdl_toplevel=top, build_dir=build_dir,
                 build_args=BUILD_ARGS, always=True, timescale=("1ns", "1ps"))
    runner.test(hdl_toplevel=top, test_module=test_module,
                build_dir=build_dir, waves=False)


def count_failures(build_dir):
    """Authoritative verdict from cocotb 2.x results.xml:
    root <testsuites> wraps <testsuite>; a <testcase> carries <failure> or
    <error> children when it fails."""
    xml = Path(build_dir) / "results.xml"
    cases = ET.parse(xml).getroot().iter("testcase")
    total, failures = 0, 0
    for case in cases:
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failures += 1
    return total, failures, 0


def main():
    runner = get_runner("icarus")
    fail = 0
    only = sys.argv[1] if len(sys.argv) > 1 else None
    MESH_SOURCES = [RTL / "hypha_link_fifo.v", RTL / "hypha_router.v",
                    ROOT / "rtl" / "top" / "hyphae_mesh_2x2.v"]
    BOTH_TILE = [ROOT / "rtl" / "soma" / "soma_dendrite.v", ROOT / "rtl" / "soma" / "soma_core.v",
                ROOT / "rtl" / "soma" / "neuro_tile.v", RTL / "hypha_link_fifo.v"]
    for sources, toplevel, module, hdl_top in (
        (FIFO_SOURCES, "hypha_link_fifo", "fifo_test", None),
        (ROUTER_SOURCES, "hypha_router", "router_test", None),
        ([RTL / "hypha_sync_fifo.v"], "hypha_sync_fifo", "sync_fifo_test", None),
        ([ROOT / "rtl" / "top" / "hypha_config_endpoint.v"],
         "hypha_config_endpoint", "config_endpoint_test", None),
        ([ROOT / "rtl" / "soma" / "soma_core.v"], "soma_core", "soma_test", None),
        (MESH_SOURCES, "hyphae_mesh_2x2", "mesh_test", None),
        (BOTH_TILE, "neuro_tile", "dendrite_test", None),
        (BOTH_TILE, "adversarial_tile", "adversarial_test", "neuro_tile"),
        ([ROOT / "rtl" / "soma" / "soma_dendrite.v",
          ROOT / "rtl" / "soma" / "soma_core.v",
          ROOT / "rtl" / "soma" / "neuro_tile.v",
          RTL / "hypha_link_fifo.v", RTL / "hypha_router.v",
          ROOT / "rtl" / "top" / "hyphae_mesh_2x2.v",
          ROOT / "rtl" / "top" / "hypha_config_endpoint.v",
          ROOT / "rtl" / "top" / "celiumneur_soc.v"], "celiumneur_soc", "soc_test", None),
    ):
        if only and toplevel != only:
            continue
        build_dir = HERE / "sim_build" / toplevel
        try:
            run_case(runner, sources, toplevel, module, hdl_top)
            total, failures, skipped = count_failures(build_dir)
            if failures:
                fail = 1
                print(f"[FAIL] {toplevel}: {failures}/{total} tests failed")
            elif total == 0:
                fail = 1
                print(f"[FAIL] {toplevel}: no tests executed")
            else:
                print(f"[PASS] {toplevel}: {total - skipped} tests passed")
        except Exception as exc:
            fail = 1
            print(f"[ERROR] {toplevel}: {exc}")
    sys.exit(fail)


def run_probes(runner, only):
    """Raw iverilog+vvp probes (no cocotb environment between us and the
    DUT): the reviewer's instrument. Each .v under verification/probes with
    an entry point compiles+runs; verdict = sim completes with no mismatched
    comparator (the probe itself asserts)."""
    import subprocess
    probes_dir = ROOT / "verification" / "probes"
    for tb in sorted(probes_dir.glob("*.v")):
        name = tb.stem
        if only and only != name:
            continue
        if name == "router_probe_tb":
            srcs = [str(tb), str(RTL / "hypha_router.v"),
                    str(RTL / "hypha_link_fifo.v")]
        elif name == "clock_sanity_tb":
            srcs = [str(tb)]
        elif name == "sync_fifo_smoke_tb":
            srcs = [str(tb), str(RTL / "hypha_sync_fifo.v")]
        elif name == "soc_probe_tb":
            srcs = [str(tb), str(ROOT / "rtl/top/celiumneur_soc.v"),
                    str(ROOT / "rtl/top/hypha_config_endpoint.v"),
                    str(ROOT / "rtl/top/hyphae_mesh_2x2.v"),
                    str(RTL / "hypha_router.v"), str(RTL / "hypha_link_fifo.v"),
                    str(ROOT / "rtl/soma/neuro_tile.v"),
                    str(ROOT / "rtl/soma/soma_dendrite.v"),
                    str(ROOT / "rtl/soma/soma_core.v")]
        else:  # tile-level probes need the whole tile compose
            srcs = [str(tb),
                    str(ROOT / "rtl/soma/soma_dendrite.v"),
                    str(ROOT / "rtl/soma/soma_core.v"),
                    str(ROOT / "rtl/soma/neuro_tile.v"),
                    str(RTL / "hypha_link_fifo.v")]
        work = HERE / "sim_build" / name
        work.mkdir(parents=True, exist_ok=True)
        out = work / "probe.vvp"
        cp = subprocess.run(["iverilog", "-g2005", "-o", str(out)] + srcs,
                            capture_output=True, text=True)
        if cp.returncode != 0:
            print(f"[FAIL] probe {name}: compile: {cp.stderr.strip()[:160]}")
            return 1
        rp = subprocess.run(["vvp", str(out)], capture_output=True, text=True,
                            timeout=180)
        tail = [ln for ln in rp.stdout.splitlines() if ln.strip()]
        pass_lines = [ln for ln in tail if "-PASS" in ln]
        marker = pass_lines[-1] if pass_lines else (tail[-1] if tail else "(empty output)")
        if rp.returncode == 0:
            print(f"[PASS] probe {name} :: {marker}")
        else:
            detail = (tail[-1] if tail else rp.stderr.strip())[:240]
            print(f"[FAIL] probe {name}: {detail}")
            return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probes":
        sys.exit(run_probes(None, None))
    main()
