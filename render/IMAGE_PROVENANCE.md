# CeliumNeUR die concept — image provenance

## Asset

- File: `celiumneur_die_concept_v0.0.2.png`
- Generated: 2026-08-13
- Generator: GPT Image 2 through the built-in Codex image-generation tool
- Use: README hero image for release v0.0.2
- License: CC BY 4.0 under the repository artwork policy

## Truth boundary

The image is a conceptual scientific visualization. It is not a die
micrograph, a DEF/GDS-derived floorplan, a post-layout result, a fabricated
chip, or evidence of timing, power, area, or silicon behavior. The topology
reference was the repository's verified `architecture_block.png`; no
third-party image was supplied to the generator.

The physical vocabulary was informed at a general level by primary literature:

- ODIN: dense synapse/neuron SRAM regions plus controller and peripheral event
  interfaces in a digital neuromorphic processor.
  <https://arxiv.org/abs/1804.07858>
- ReckOn: integrated recurrent-neural-network processing and on-chip learning
  in a compact neuromorphic research IC.
  <https://arxiv.org/abs/2208.09759>
- Loihi: repeated neuromorphic cores organized as an on-chip manycore fabric.
  <https://doi.org/10.1109/MM.2018.112130359>

The result does not reproduce or imitate a specific published die micrograph.

## Generation prompt

```text
Create a wide 16:9 hyper-realistic scientific product photograph of a
conceptual bare neuromorphic CMOS die for the CeliumNeUR research RTL project.
Use the supplied architecture diagram only as a topology reference, never as a
visual style reference.

SUBJECT AND TOPOLOGY
- One complete rectangular silicon die, centered and fully visible, viewed
  almost top-down with a subtle 20-degree oblique macro-camera angle.
- The floorplan must visibly suggest four equal neuromorphic tile regions
  arranged as a symmetric 2-by-2 grid.
- Each tile contains physically plausible repeated SRAM-like bitcell textures
  plus compact neuron-state/control logic bands; the four tiles must look
  integrated into one monolithic die, not like raised blocks or separate
  modules.
- At the exact center, show a small compact 2-by-2 routing/control fabric,
  connected radially and orthogonally to all four tiles through dense thin
  multi-layer metal interconnect.
- Around the die perimeter, include realistic I/O bond pads, power rings,
  clock/control strips, and sparse test structures.
- The relative visual hierarchy should be: memory-dense tiles dominate area,
  central router is small, peripheral interfaces are narrow.

MATERIALS AND REALISM
- Physically plausible advanced digital CMOS die photography: dark
  indigo/charcoal silicon, microscopic copper/aluminum routing, subtle gold pad
  metallurgy, cyan-magenta-green thin-film interference, faint lithographic
  grain and reticle variation.
- Controlled cleanroom/studio macro lighting, soft specular highlights,
  realistic micro-scale surface detail, high dynamic range, sharp die surface
  with only gentle background falloff.
- Dark neutral background with no package, no PCB, no laboratory props.
- Premium semiconductor die-shot realism, restrained and technically
  credible; avoid sci-fi spectacle.

TRUTH AND EXCLUSIONS
- This is a conceptual visualization informed by published neuromorphic-chip
  floorplan conventions, not an exact post-layout floorplan.
- Do not imitate any single published chip or reproduce a specific micrograph.
- No labels, no letters, no numbers, no logos, no watermark.
- No glowing neural networks, no brain shapes, no biological neurons, no
  floating particles, no holograms.
- No raised architectural blocks, toy diorama, cityscape, CPU package, pins,
  heatsink, PCB, or impossible luminous wires.
- Do not add decorative text.

COMPOSITION
- Wide README hero image, 16:9, generous but not excessive dark breathing
  room.
- The die occupies about 75 percent of the frame width.
- Editorial-grade, photoreal, precise, sober, research-oriented.
```
