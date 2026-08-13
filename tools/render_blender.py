# SPDX-License-Identifier: AGPL-3.0-or-later
"""render_blender.py — CeliumNeUR die hero render (Blender >= 4.x, headless).

Run:  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b --python render_blender.py
Writes: render/die_hero.png (1920x1080) + render/die_top.png (floorplan view).

Everything on the die maps 1:1 to real blocks of celiumneur_soc.v:
  substrate + gold bond frame  -> the die itself
  center 2x2 of routers        -> hyphae_mesh_2x2 (Hyphae fabric)
  4 corner tiles               -> neuro_tiles (soma + dendrite + snooper)
  inner cube rows / bars       -> soma array / dendrite table / snooper strip
  thin emissive routes         -> fabric links between cores
"""

import bpy
import math
import mathutils
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "render"
OUT.mkdir(exist_ok=True)


# ---------- scene reset ----------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

scene = bpy.context.scene
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.filepath = str(OUT / "die_hero.png")
scene.world.color = (0.02, 0.02, 0.03)


# ---------- materials ----------
def mat(name, color, metallic=0.0, rough=0.4, emission=None, emis_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if emission is not None:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emis_strength
    return m

SUBSTRATE  = mat("substrate", (0.012, 0.045, 0.070), metallic=0.35, rough=0.25)
GOLD       = mat("gold pads", (0.83, 0.60, 0.10), metallic=1.0, rough=0.18)
CORE_TEAL  = mat("compute teal", (0.015, 0.30, 0.34), metallic=0.55, rough=0.35)
ROUT_TEAL  = mat("router teal", (0.02, 0.22, 0.27), metallic=0.55, rough=0.35)
DEND_SALM  = mat("dendrite salmon", (0.55, 0.20, 0.13), metallic=0.40, rough=0.38)
SNOOP_BLUE = mat("snooper blue", (0.03, 0.08, 0.22), metallic=0.5, rough=0.3)
TRACE_EMIT = mat("traces", (0.06, 0.22, 0.26), metallic=0.5, rough=0.35,
                 emission=(0.08, 0.32, 0.36), emis_strength=0.45)
TOP_GLOW   = mat("block glow", (0.02, 0.10, 0.12), metallic=0.45, rough=0.35,
                 emission=(0.05, 0.28, 0.32), emis_strength=0.25)
CHIP_TEXTM  = mat("etch text", (0.5, 0.85, 0.9), metallic=0.2, rough=0.6,
                  emission=(0.4, 0.8, 0.85), emis_strength=0.5)


def block(name, loc, scale_xyz, material, bevel=0.12):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (scale_xyz[0] / 2, scale_xyz[1] / 2, scale_xyz[2] / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    if bevel > 0:
        mod = o.modifiers.new("bevel", 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    return o


# ---------- die substrate ----------
block("die", (0, 0, -1.1), (26.0, 26.0, 1.6), SUBSTRATE, bevel=0.35)

# bond pads around the perimeter (functional-looking gold frame)
pad_n = 12
for i in range(pad_n):
    x = -11.0 + i * (22.0 / (pad_n - 1))
    block(f"pad_N{i}", (x, 12.45, -0.55), (1.1, 0.9, 0.55), GOLD, bevel=0.08)
    block(f"pad_S{i}", (x, -12.45, -0.55), (1.1, 0.9, 0.55), GOLD, bevel=0.08)
    block(f"pad_W{i}", (-12.45, x, -0.55), (0.9, 1.1, 0.55), GOLD, bevel=0.08)
    block(f"pad_E{i}", (12.45, x, -0.55), (0.9, 1.1, 0.55), GOLD, bevel=0.08)

# ---------- Hyphae mesh (center): slab + 4 routers ----------
block("mesh_slab", (0, 0, 0.2), (7.6, 7.6, 1.1), SNOOP_BLUE, bevel=0.22)
for ix, x in enumerate((-1.85, 1.85)):
    for iy, y in enumerate((-1.85, 1.85)):
        block(f"router_r{ix}{iy}", (x, y, 1.15), (2.9, 2.9, 1.5), ROUT_TEAL,
              bevel=0.18)
        # emissive inner frame per router (an accent ring, not a slab)
        for side, (lo, so) in enumerate([("top", 0),]):
            pass
        block(f"router_r{ix}{iy}_edge", (x, y, 1.94), (1.55, 0.16, 0.10),
              TOP_GLOW, bevel=0.02)
        block(f"router_r{ix}{iy}_edge2", (x, y, 1.94), (0.16, 1.55, 0.10),
              TOP_GLOW, bevel=0.02)

# traces between routers (thin metal lines, barely glowing)
for (a, b) in [((-1.85, -1.85), (1.85, -1.85)), ((-1.85, 1.85), (1.85, 1.85)),
               ((-1.85, -1.85), (-1.85, 1.85)), ((1.85, -1.85), (1.85, 1.85))]:
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    block("tr_mesh", (mx, my, 1.30), (max(dx, 0.10), max(dy, 0.10), 0.12),
          TRACE_EMIT, bevel=0.03)

# ---------- four tiles at corners ----------
tile_centers = [(-7.6, 7.6), (7.6, 7.6), (-7.6, -7.6), (7.6, -7.6)]
for i, (cx, cy) in enumerate(tile_centers):
    block(f"tile{i}_slab", (cx, cy, 0.35), (6.6, 6.6, 0.95), CORE_TEAL,
          bevel=0.22)
    # soma array: 4 neuron cubes in a row (left band)
    for n in range(4):
        block(f"t{i}_neuron{n}", (cx - 2.2 + n * 1.45, cy + 1.9, 1.35),
              (1.1, 1.1, 1.2), CORE_TEAL, bevel=0.1)
        # each neuron gets a tiny emissive cap on top
        block(f"t{i}_neuron{n}_glow", (cx - 2.2 + n * 1.45, cy + 1.9, 1.97),
              (0.42, 0.42, 0.07), TOP_GLOW, bevel=0.02)
    # dendrite table: wide salmon band across the middle
    block(f"t{i}_dendrite", (cx, cy + 0.1, 1.2), (5.4, 1.5, 1.0),
          DEND_SALM, bevel=0.15)
    # snooper: thin dark strip at the bottom
    block(f"t{i}_snooper", (cx, cy - 2.0, 0.95), (5.4, 0.5, 0.6),
          SNOOP_BLUE, bevel=0.08)

# tile -> mesh: Manhattan L-routes of thin traces (horizontal leg + vertical leg)
TRW = 0.16
for (tx, ty) in tile_centers:
    ex = 1.85 if tx > 0 else -1.85     # mesh edge x nearest the tile
    ey = 1.85 if ty > 0 else -1.85     # mesh edge y nearest the tile
    # horizontal leg at tile's y
    block("tr_tile_h", ((tx + ex) / 2, ty, 0.85), (abs(tx - ex), TRW, TRW),
          TRACE_EMIT, bevel=0.03)
    # vertical leg at mesh corner x
    block("tr_tile_v", (ex, (ty + ey) / 2, 0.85), (TRW, abs(ty - ey), TRW),
          TRACE_EMIT, bevel=0.03)

# ---------- etched label (no secrets) ----------
bpy.ops.object.text_add(location=(-2.8, -11.35, 0.05), rotation=(0, 0, 0))
t = bpy.context.active_object
t.data.body = "CELIUMNEUR"
t.data.size = 1.0
t.data.align_x = 'LEFT'
t.data.extrude = 0.05
t.data.materials.append(CHIP_TEXTM)


# ---------- lighting ----------
def area(name, loc, energy, color, size=6.0):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.name = name
    L.data.energy = energy
    L.data.color = color
    L.data.shape = 'DISK'
    L.data.size = size
    # point at origin
    d = mathutils.Vector((0, 0, 0)) - L.location
    L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return L

area("key",    (16, -14, 26), 2400, (1.0, 0.9, 0.8))
area("fill",   (-18, 10, 18), 1500, (0.55, 0.8, 1.0))
area("rim",    (0, 18, 20),   1300, (0.4, 0.85, 0.95))
bpy.ops.object.light_add(type='POINT', location=(0, 0, 8))
glow = bpy.context.active_object
glow.data.energy = 60
glow.data.color = (0.35, 0.8, 0.85)

# ---------- camera (3/4 die shot) ----------
bpy.ops.object.camera_add(location=(28, -28, 26))
cam = bpy.context.active_object
d = mathutils.Vector((0, 0, 2.0)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
scene.camera.data.lens = 52

bpy.ops.render.render(write_still=True)
print("WROTE", scene.render.filepath)

# ---------- second pass: top-down floorplan ----------
scene.render.resolution_x = 1600
scene.render.resolution_y = 1600
scene.render.filepath = str(OUT / "die_top.png")
cam.location = (0, 0, 34)
cam.rotation_euler = (0, 0, 0)
scene.camera.data.type = 'ORTHO'
scene.camera.data.ortho_scale = 30
bpy.ops.render.render(write_still=True)
print("WROTE", scene.render.filepath)
