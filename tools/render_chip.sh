#!/usr/bin/env bash
# render_chip.sh — yosys structural schematics (SVG) for CeliumNeUR.
# Renders: full SoC block map, and the neuro_tile datapath midd-view.
set -euo pipefail
export PATH=/opt/oss-cad-suite/bin:$PATH
OUT=/home/build/render
mkdir -p "$OUT"
cd /home/build/celiumneur

# 1) Full hierarchy, block-level (no gate blow-up): module-level map.
cat > /tmp/render_soc.ys <<'EOF'
read_verilog rtl/soma/soma_dendrite.v rtl/soma/soma_core.v rtl/soma/neuro_tile.v rtl/hyphae/hypha_link_fifo.v rtl/hyphae/hypha_router.v rtl/top/hyphae_mesh_2x2.v rtl/top/celiumneur_soc.v
hierarchy -check -top celiumneur_soc
proc
show -stretch -format svg -prefix /home/build/render/celiumneur_soc_map -notitle celiumneur_soc
EOF

# 2) neuro_tile flattened: the datapath mid view (Somas + dendrite internals visible as blocks).
cat > /tmp/render_tile.ys <<'EOF'
read_verilog rtl/soma/soma_dendrite.v rtl/soma/soma_core.v rtl/soma/neuro_tile.v
hierarchy -check -top neuro_tile
proc
show -stretch -format svg -prefix /home/build/render/neuro_tile_map -notitle neuro_tile
EOF

yosys -Q /tmp/render_soc.ys > "$OUT/soc_render.log" 2>&1 || true
yosys -Q /tmp/render_tile.ys > "$OUT/tile_render.log" 2>&1 || true
ls -la "$OUT"
