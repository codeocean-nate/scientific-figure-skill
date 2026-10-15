---
name: scientific-figure
description: Draw a publication-style scientific illustration (mechanism of action, antibody or ADC binding, receptor engagement, T-cell engagers, cell-cell interactions, central dogma and other biology schematics) as an editable SVG and PNG in the clean look of a BioRender figure. Draws with code, then looks at its own rendering and fixes it. Use when someone asks to draw, illustrate, sketch or diagram biology, or to "make a figure like BioRender/Phylo". Not for data plots or charts.
metadata:
  tags: [figures, illustration, schematic, mechanism-of-action, antibody, visualization]
---

# Scientific figure

Draw the figure with code, using the `bioschematic` drawing kit that ships with this skill (`scripts/bioschematic.py`), then look at the rendered PNG and revise it. Never hand back a figure you have not looked at.

## 1. Pin down the science first
- Restate in one or two lines what will be drawn: each cell, each molecule, and each binding state (bound to what, unbound, free).
- If the request leaves a binding state or the format of a molecule unclear, ask before drawing.
- Draw only what was asked. Don't add cells, interactions or mechanism steps the request didn't mention.

## 2. Workspace: the "Figure studio" capsule
- Look for a capsule of the user's named "Figure studio". If there is none, create it with environment: base image `codeocean/python:3.11.13`; pip `cairosvg`, `pillow`; apt `libcairo2`, `fonts-liberation2`.
- **The kit.** `/code/bioschematic.py` must be this skill's `scripts/bioschematic.py`, byte for byte: sha256 `ebf07513610527021e1efa6657a54d93a30dae087e8523359b091f9ccc540278`, 35,836 bytes, 700 lines.
  - Read it from this skill's capsule (skill files `scripts/bioschematic.py`, or the editor on this skill's capsule). Write it into the studio with the editor's create command in a single call, so the text arrives unchanged.
  - If the studio already has a `bioschematic.py` with a different checksum, it is an older kit: replace it the same way. Older figure scripts keep working.
  - Verify the checksum with `sha256sum` the first time you render. Don't edit the kit.
- `/code/run` (executable), which renders every figure so a reproducible run regenerates all of them:
  ```bash
  #!/usr/bin/env bash
  set -e
  cd /code
  export PYTHONPATH=/code PYTHONDONTWRITEBYTECODE=1
  for f in figures/*/figure.py; do python3 "$f"; done
  ```
- `/code/.gitignore` containing `__pycache__/`. Before every commit, delete any `__pycache__` folder under `/code`.
- If the studio already exists, bring it up to date: replace an older kit as above, and make sure `/code/run` and `/code/.gitignore` match what is shown here.
- Each figure gets its own folder `/code/figures/<slug>/` with one `figure.py`. It writes to `/results/<slug>/`: `figure.svg`, `figure.png`, `figure@2x.png` (for slides) and `figure.warnings.json`.

## 3. Draw, look, fix
1. **Write** `/code/figures/<slug>/figure.py`. Start it exactly like this, because the script lives in a subfolder and must find the kit:
   ```python
   import os, sys
   sys.path.insert(0, "/code")
   sys.dont_write_bytecode = True
   from bioschematic import *
   slug = "<slug>"
   os.makedirs(f"/results/{slug}", exist_ok=True)
   ```
   End it with `c.save(f"/results/{slug}/figure.svg")`.
2. **Render.** Either:
   - start a Terminal cloud workstation, write the file, and run `cd /code && PYTHONDONTWRITEBYTECODE=1 python3 figures/<slug>/figure.py`; or
   - if you can edit capsule files directly, edit the file and start a reproducible run.
   Read every `WARNING:` line the kit prints (off-canvas parts, overlapping labels, text covering a part). Fix any script error before going on.
3. **Shut down fully.** If you used a workstation, do a full shutdown, not a hold. Results can't be read while a workstation is still running (the image viewer returns 404), and they appear once it has shut down.
4. **Look at the PNG** with the image viewer: the `computation` source, the capsule **UUID** (not the numeric slug), the computation ID of the workstation session or run, and the path `<slug>/figure.png`.
5. **Review it.** List every problem you see, then sort each one:
   - **Must fix:**
     - a science error, or an element of the request that is missing or in the wrong binding state;
     - **any label that could be read as naming the wrong thing**, or that sits on a different structure than the one it names (a "Nucleus" label outside the nucleus is a must-fix, not a cosmetic issue);
     - clipped, cut-off or overlapping text;
     - a leader line that crosses a molecule or points at the wrong part;
     - a molecule floating off its membrane, colliding with another, or cut off;
     - any kit `WARNING:` you haven't judged to be a false alarm.
   - **Polish:** spacing, balance, color, label wording.
6. **Revise** and go back to step 2.
   - Fix every must-fix item, and the polish items if they're quick.
   - Stop only when no must-fix item is left. That usually takes 2 or 3 rounds.
   - If must-fix items remain after round 3, keep going up to round 5. Then hand over and name exactly what is still wrong.

## 4. Hand it over
- Delete any `__pycache__` under `/code`, commit, then start one reproducible run so the final figure sits in that run's results.
- **Show the figure inline.** Get the file URL for `<slug>/figure.png` from that run's results and embed it in your reply as `<img src="URL" alt="short description" style="max-width:100%">`.
- Then tell the user:
  - the capsule and the run;
  - the files: `figure.png`, `figure@2x.png` for slides, and `figure.svg`, which is editable in Illustrator, Inkscape or PowerPoint;
  - a short list of what the figure shows and anything you simplified.

## bioschematic quick reference
Units are pixels; y grows downward; angles are degrees clockwise. Draw on a 1600×1000 canvas.

The title, subtitle and legend are placed automatically around the finished drawing, and the image is trimmed to it. So:
- don't position them yourself, and don't pass `y=` to the legend;
- don't worry about empty margins;
- do avoid large empty gaps *inside* the drawing, because trimming can't remove those.

```python
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
- `c.antibody(dock=site, arm="left"|"right"|"scfv", arms=(left_color, right_color), payloads=0..8, scfv=color, scale=1.0, align="fc"|"arm", tilt=0)`: an IgG-like molecule.
  - The variable domains are colored by specificity.
  - `payloads` makes it an ADC, and `scfv=color` adds an scFv on the Fc (for example an anti-CD3 arm).
  - It returns an Antibody, whose `.point("hinge"|"fc"|"left"|"right"|"scfv"|"payload0")` gives coordinates for callouts.
  - You can also place it free with `at=(x, y), rotation=deg`.
- `c.cell_for(antibody, which="scfv", kind="t_cell", r=110, receptor_color=GRAY, receptor_name="CD3", label="T cell")` places a second cell whose receptor meets that binder. Use it only when the request says the cells are engaged.
- `c.callout(text, target, at, size=17, bold=False, anchor=None)`: a label with a leader arrow. The leader leaves from the side of the text that faces the target.
- `c.label(text, x, y, size, bold, anchor, halo)`: plain text, with `\n` for line breaks.
- `c.arrow(start, end, curve=0.0, dashed=False)`, `c.granules(start, end, n=7, color)`, `c.payload(x, y)`: process arrows, granule release, a free payload.
- `c.legend(items)`: `(kind, text[, color])` with kind `igg`, `adc`, `payload`, `receptor`, `scfv`, `granule`, `t_cell`, `tumor`.
- **Anything the kit lacks** (DNA, RNA, ribosomes, organelles, proteins, membranes, pathways): draw it as raw SVG with `c.add('<path d="..." fill="..."/>', layer="molecules")`.
  - Layers, back to front: `back`, `cells`, `receptors`, `molecules`, `arrows`, `labels`.
  - Raw shapes are included in the automatic trimming. They get no layout warnings, so check them by eye.

Layout tips from testing:
- A docked antibody stands about 180 px tall at scale 1, and an scFv adds about 60 px. Leave at least 260 px of headroom above receptors that have antibodies on them.
- Place callout text in the margins, away from the molecules, close to what it names.
- Put each structure's label on or right next to that structure. For a compartment such as the nucleus or cytoplasm, put the label inside it.
- The kit's text widths are estimates, so trust the image over the warnings.
