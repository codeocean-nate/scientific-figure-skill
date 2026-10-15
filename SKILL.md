---
name: scientific-figure
description: Draw a publication-style scientific illustration (mechanism of action, antibody or ADC binding, receptor engagement, T-cell engagers, cell-cell interactions) as an editable SVG and PNG in the clean look of a BioRender figure. Draws with code, then looks at its own rendering and fixes it, up to three rounds. Use when someone asks to draw, illustrate, sketch or diagram biology, or to "make a figure like BioRender/Phylo". Not for data plots or charts.
metadata:
  tags: [figures, illustration, schematic, mechanism-of-action, antibody, visualization]
---

# Scientific figure

Draw the figure with code, using the `bioschematic` drawing kit that ships with this skill, then look at the rendered PNG and revise it. Never hand back a figure you have not looked at.

## 1. Pin down the science first
- Restate in one or two lines what will be drawn: each cell, each molecule, and each binding state (bound to what, unbound, free).
- If the request leaves a binding state or the format of a molecule unclear, ask before drawing.
- Draw only what was asked. Don't add cells, interactions or mechanism steps the request didn't mention.

## 2. Workspace: the "Figure studio" capsule
- Look for a capsule of the user's named "Figure studio". If there is none, create it:
  - Environment: base image `codeocean/python:3.11.13`; pip `cairosvg`, `pillow`; apt `libcairo2`, `fonts-liberation2`.
  - `/code/bioschematic.py`: copy byte for byte from this skill's own `bioschematic.py`, the file next to this SKILL.md in this skill's capsule. Verify it with `sha256sum`; it must be `aaca2bf5a8c7e40ccf301274c270fae14ce7097226be4a2317f50d41f2cff1f4` (30,713 bytes, 609 lines). Don't edit the kit.
  - `/code/run` (executable): renders every figure, so a reproducible run regenerates all of them:
    ```bash
    #!/usr/bin/env bash
    set -e
    cd /code
    for f in figures/*/figure.py; do python3 "$f"; done
    ```
- Each figure gets its own folder `/code/figures/<slug>/` with one `figure.py`. It writes to `/results/<slug>/figure.svg`; the kit also writes `figure.png` and `figure.warnings.json` there.

## 3. Draw, look, fix (at most 3 rounds)
1. **Write** `/code/figures/<slug>/figure.py` with the kit (see the reference below). Start with `os.makedirs(f"/results/{slug}", exist_ok=True)` and end with `c.save(f"/results/{slug}/figure.svg")`.
2. **Render.** Either:
   - start a Terminal cloud workstation, write the file, and run `cd /code && python3 figures/<slug>/figure.py`; or
   - if you can edit capsule files directly, edit the file and start a reproducible run.
   Read every `WARNING:` line the kit prints. These are off-canvas parts, overlapping labels, and a legend covering a cell. Fix any script error before going on.
3. **Shut down fully.** If you used a workstation, do a full shutdown, not a hold. Results files can't be read while a workstation is still running (the image viewer returns 404), and they appear once it has shut down.
4. **Look at the PNG** with the image viewer, using the `computation` source with the capsule **UUID** (not the numeric slug), the computation ID of the workstation session or run, and the path `<slug>/figure.png`.
5. **Review it like a demanding biologist and a professional illustrator:**
   - Is every element of the request present, with each binding state drawn exactly as stated?
   - Are any labels clipped, overlapping, or far from what they name? Do any leader lines cross molecules or point at the wrong part?
   - Are any molecules floating off a membrane, colliding, or cut off at the edge?
   - Is there awkward empty space, or a crowded area?
6. **Revise** and go back to step 2. Stop after round 3, or sooner if the figure has no real problems left.

Round 1 nearly always has layout problems (clipped text, a legend over the cell), so plan on at least two rounds.

## 4. Hand it over
- Commit, then start one reproducible run so the final figure sits in that run's results.
- Tell the user the capsule, the run, and the paths `<slug>/figure.png` and `<slug>/figure.svg`. The SVG is editable in Illustrator, Inkscape or PowerPoint.
- Also give a short list of what the figure shows and anything you simplified.

## bioschematic quick reference
Units are pixels; y grows downward; angles are degrees clockwise. A 1600×1000 canvas suits most figures.

```python
import os
from bioschematic import *     # Canvas, colors TEAL PURPLE GRAY GREEN RED GOLD PINK HEAVY LIGHT TEXT MUTED PAYLOAD, mix(), darken()
slug = "cd38-dual-targeting"
os.makedirs(f"/results/{slug}", exist_ok=True)
c = Canvas(1600, 1000, title="Short title", subtitle="Optional one-line subtitle")
mm = c.cell("tumor", cx=800, cy=640, rx=420, ry=210, label="Multiple myeloma cell", label_at=(760, 790))
cd38 = c.receptor(mm, angle=-125, color=TEAL, name="CD38")    # angle: 0 right, -90 top, 90 bottom, 180 left
adc = c.antibody(dock=cd38, arm="right", arms=(TEAL, TEAL), payloads=4, name="ADC")
c.callout("Anti-CD38 ADC\n(4 site-specific payloads)", target=adc.point("hinge"), at=(330, 250), bold=True)
c.legend([("adc", "Antibody–drug conjugate"), ("payload", "Payload on cleavable linker"), ("receptor", "CD38", TEAL)])
c.save(f"/results/{slug}/figure.svg")
```

- `c.cell(kind, cx, cy, rx, ry=None, label=None, label_at=None)`: kinds `tumor`, `t_cell`, `nk_cell`, `macrophage`, `generic`.
- `c.receptor(cell, angle, color, name=None, scale=1.0, shape="y"|"knob")` returns a Site, the binding tip.
- `c.antibody(dock=site, arm="left"|"right"|"scfv", arms=(left_color, right_color), payloads=0..8, scfv=color, scale=1.0, align="fc"|"arm", tilt=0)`: an IgG-like molecule. The variable domains are colored by specificity. `payloads` makes it an ADC, and `scfv=color` adds an scFv on the Fc (for example an anti-CD3 arm). It returns an Antibody, whose `.point("hinge"|"fc"|"left"|"right"|"scfv"|"payload0")` gives coordinates for callouts. You can also place it free with `at=(x, y), rotation=deg`.
- `c.cell_for(antibody, which="scfv", kind="t_cell", r=110, receptor_color=GRAY, receptor_name="CD3", label="T cell")` places a second cell whose receptor meets that binder. Use it only when the request says the cells are engaged.
- `c.callout(text, target, at, size=17, bold=False, anchor=None)`: a label with a leader arrow. `c.label(text, x, y, size, bold, anchor, halo)` is plain text, with `\n` for line breaks.
- `c.arrow(start, end, curve=0.0, dashed=False)`, `c.granules(start, end, n=7, color)`, `c.payload(x, y)`: process arrows, granule release, a free payload.
- `c.legend(items)`: `(kind, text[, color])` with kind `igg`, `adc`, `payload`, `receptor`, `scfv`, `granule`, `t_cell`, `tumor`. It sits along the bottom and wraps rows.
- For a shape the kit lacks, add raw SVG: `c._add("molecules", '<path d="..." fill="..."/>')`. Layers are `back`, `cells`, `receptors`, `molecules`, `arrows`, `labels`.

Layout tips from testing:
- A docked antibody stands about 180 px tall at scale 1, and an scFv adds about 60 px. Leave at least 260 px of headroom above receptors that have antibodies on them, and keep the title clear of them.
- When the action is on the cell's top surface, make the cell wide (rx 380–450) and keep its bottom (cy + ry) above about 850 px, where a one-row legend starts on a 1000-px canvas. For example cy 640, ry 210. Set `label_at` so the cell label sits inside the visible part.
- Place callout text in the margins, away from the molecules. The leader leaves from the side of the text that faces its target.
- The kit's text widths are estimates, so trust the image over the warnings.
