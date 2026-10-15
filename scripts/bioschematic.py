"""bioschematic: a small drawing kit for BioRender-style mechanism-of-action figures.

Parts snap together geometrically, so a figure is a short script instead of hand-placed coordinates:
receptors sit on a cell membrane along the surface normal, an antibody docks a chosen binding arm onto
a receptor's binding site, an scFv hangs off the Fc, and a second cell can be placed so that one of
its receptors meets a free binder. Output is plain SVG (plus a PNG when cairosvg or rsvg-convert is
available). Coordinates are pixels on the canvas; y grows downward; angles are degrees clockwise.

Quick start
    from bioschematic import *
    c = Canvas(1600, 1000, title="Anti-CD38 ADC on a myeloma cell")
    mm = c.cell("tumor", cx=800, cy=650, rx=360, ry=230, label="Multiple myeloma cell")
    cd38 = c.receptor(mm, angle=-115, color=TEAL, name="CD38")       # angle -90 = top of the cell
    adc = c.antibody(dock=cd38, arm="right", arms=(TEAL, TEAL), payloads=4)
    c.callout("Anti-CD38 ADC", target=adc.point("hinge"), at=(470, 300))
    c.legend([("igg", "IgG antibody"), ("payload", "Payload on cleavable linker"), ("receptor", "CD38", TEAL)])
    c.save("figure.svg")   # also writes figure.png, figure@2x.png and prints layout warnings

By default (fit=True) the title, subtitle and legend are placed around the finished drawing and the
image is trimmed to it, so there is no need to position them or to fill the whole canvas.
Shapes the kit lacks can be drawn as raw SVG with c.add('<path .../>').

Palette constants: TEXT, MUTED, HEAVY, LIGHT, TEAL, PURPLE, GRAY, GREEN, RED, GOLD, PINK, PAYLOAD.
"""
import io
import json
import math
import os
import random
import shutil
import subprocess
from xml.sax.saxutils import escape as _esc

__all__ = [
    "Canvas", "Cell", "Site", "Antibody", "mix", "darken",
    "TEXT", "MUTED", "HEAVY", "LIGHT", "TEAL", "PURPLE", "GRAY", "GREEN", "RED", "GOLD", "PINK", "PAYLOAD",
]

FONT = "Arial, 'Liberation Sans', 'Helvetica Neue', 'DejaVu Sans', sans-serif"
TEXT = "#1F2430"
MUTED = "#5A6070"
HEAVY = "#3F6DB5"
HEAVY_DK = "#284A82"
LIGHT = "#A8C5EC"
LIGHT_DK = "#6B8FC4"
TEAL = "#2A9D8F"
PURPLE = "#8E6BBF"
GRAY = "#6B6F7B"
GREEN = "#5BA35B"
RED = "#D1495B"
GOLD = "#E0A526"
PINK = "#D9739B"
PAYLOAD = "#F08A33"
PAYLOAD_DK = "#B65F17"

ANTIBODY_SCALE = 1.55   # base size of antibodies (height about 180 px at scale=1)
RECEPTOR_SCALE = 1.35   # base size of receptors (about 65 px tall at scale=1)
RECEPTOR_TIP = 44.0     # binding-site height of a receptor in its own units


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2="#FFFFFF", t=0.4):
    """Blend color c1 toward c2 by fraction t (0..1)."""
    a, b = _hex(c1), _hex(c2)
    return "#%02X%02X%02X" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def darken(c, t=0.3):
    return mix(c, "#000000", t)


def _rot(x, y, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca)


def _dir(psi):
    """Unit vector of 'up' rotated clockwise by psi degrees."""
    a = math.radians(psi)
    return (math.sin(a), -math.cos(a))


def _psi_of(dx, dy):
    """Clockwise rotation (degrees) that turns 'up' into the direction (dx, dy)."""
    return math.degrees(math.atan2(dx, -dy))


def _f(v):
    return f"{v:.1f}"


class Site:
    """A binding site: tip position (x, y), outward direction psi, the membrane base point and a name."""

    def __init__(self, x, y, psi, name=None, base=None, color=None):
        self.x, self.y, self.psi, self.name, self.base, self.color = x, y, psi, name, base, color

    @property
    def xy(self):
        return (self.x, self.y)

    def outward(self):
        return _dir(self.psi)


class Cell:
    """An elliptical cell. point(angle) gives the membrane point and outward normal at a parametric
    angle: 0 = right, -90 = top, 90 = bottom, 180 = left."""

    def __init__(self, kind, cx, cy, rx, ry, name=None):
        self.kind, self.cx, self.cy, self.rx, self.ry, self.name = kind, cx, cy, rx, ry, name

    def point(self, angle):
        t = math.radians(angle)
        x = self.cx + self.rx * math.cos(t)
        y = self.cy + self.ry * math.sin(t)
        nx, ny = math.cos(t) / self.rx, math.sin(t) / self.ry
        n = math.hypot(nx, ny)
        return (x, y), (nx / n, ny / n)

    def inside(self, fx=0.0, fy=0.0):
        """A point inside the cell, as fractions of the radii from the center (-1..1)."""
        return (self.cx + fx * self.rx, self.cy + fy * self.ry)


class Antibody:
    """Geometry of a drawn antibody. point(name) returns canvas coordinates for 'hinge', 'fc',
    'left', 'right' (Fab tips), 'scfv' (scFv tip) or 'payload0'.. ; direction(name) is the unit vector
    a binder points along."""

    def __init__(self, tx, ty, alpha, s, local_points, local_dirs, name=None):
        self.tx, self.ty, self.alpha, self.s = tx, ty, alpha, s
        self._pts, self._dirs, self.name = local_points, local_dirs, name

    def to_canvas(self, x, y):
        rx, ry = _rot(x * self.s, y * self.s, self.alpha)
        return (self.tx + rx, self.ty + ry)

    def point(self, name):
        return self.to_canvas(*self._pts[name])

    def tip(self, which):
        return self.point(which)

    def direction(self, which):
        return _dir(self._dirs[which] + self.alpha)

    def points(self):
        return {k: self.point(k) for k in self._pts}


class Canvas:
    LAYERS = ("back", "cells", "receptors", "molecules", "arrows", "labels", "frame")

    def __init__(self, width=1600, height=1000, title=None, subtitle=None, background="#FFFFFF", fit=True):
        """fit=True (default): at save time the title, subtitle and legend are placed around the drawing
        and the image is trimmed to it. fit=False keeps the fixed canvas, with the title at the top and the
        legend along the bottom."""
        self.w, self.h, self.bg = width, height, background
        self.fit = fit
        self._layers = {k: [] for k in self.LAYERS}
        self._defs = {}
        self._boxes = []    # estimated text boxes: (x0, y0, x1, y1, text)
        self._frame = set()  # indexes into _boxes for the title, subtitle and legend
        self._extent = []   # sample points of drawn parts: (x, y, what)
        self._n = 0
        self._title, self._subtitle = title, subtitle
        self._legend_req = None
        self._viewbox = (0, 0, width, height)

    # ---------- internals ----------
    def _id(self, prefix):
        self._n += 1
        return f"{prefix}{self._n}"

    def _add(self, layer, s):
        self._layers[layer].append(s)

    def add(self, svg, layer="molecules"):
        """Add raw SVG (paths, shapes, text) for anything the kit has no part for. Layers, back to
        front: back, cells, receptors, molecules, arrows, labels."""
        self._add(layer, svg)

    def _track(self, x, y, what):
        self._extent.append((x, y, what))

    def _marker(self, color):
        mid = "arr" + color.lstrip("#")
        if mid not in self._defs:
            self._defs[mid] = (f'<marker id="{mid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
                               f'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>')
        return mid

    def _radial(self, inner, outer, cx=0.42, cy=0.38):
        gid = self._id("g")
        self._defs[gid] = (f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="0.75">'
                           f'<stop offset="0" stop-color="{inner}"/><stop offset="1" stop-color="{outer}"/></radialGradient>')
        return gid

    @staticmethod
    def _text_width(line, size, bold):
        wide = sum(1 for ch in line if ch.isupper() or ch in "mwMW@%")
        return (len(line) * (0.56 if bold else 0.53) + wide * 0.12) * size

    # ---------- text ----------
    def label(self, text, x, y, size=18, bold=False, italic=False, color=TEXT, anchor="middle",
              line_height=1.25, halo=False, layer="labels"):
        """Text at (x, y); y is the baseline of the first line. Use '\\n' for line breaks.
        anchor: 'start' | 'middle' | 'end'. halo=True adds a white outline for text over shapes."""
        lines = str(text).split("\n")
        weight = "700" if bold else "400"
        style = ' font-style="italic"' if italic else ""
        spans = "".join(
            f'<tspan x="{_f(x)}" dy="{0 if i == 0 else _f(size * line_height)}">{_esc(t)}</tspan>'
            for i, t in enumerate(lines))
        common = (f'x="{_f(x)}" y="{_f(y)}" font-size="{size}" font-weight="{weight}"{style} '
                  f'text-anchor="{anchor}"')
        if halo:
            self._add(layer, f'<text {common} fill="none" stroke="#FFFFFF" stroke-width="5" '
                             f'stroke-linejoin="round">{spans}</text>')
        self._add(layer, f'<text {common} fill="{color}">{spans}</text>')
        wmax = max(self._text_width(t, size, bold) for t in lines)
        x0 = {"start": x, "middle": x - wmax / 2, "end": x - wmax}[anchor]
        top = y - size * 0.8
        bottom = y + size * line_height * (len(lines) - 1) + size * 0.25
        self._boxes.append((x0, top, x0 + wmax, bottom, lines[0]))
        if layer == "frame":
            self._frame.add(len(self._boxes) - 1)
        return (x0, top, x0 + wmax, bottom)

    def callout(self, text, target, at, size=17, bold=False, color=TEXT, anchor=None, line_color="#2B2F3A",
                arrow=True):
        """A label at `at` with a leader line (and arrowhead) to `target`. Anchor defaults to the side
        facing the target."""
        tx, ty = target
        ax, ay = at
        if anchor is None:
            anchor = "end" if ax < tx else "start"
        x0, y0, x1, y1 = self.label(text, ax, ay, size=size, bold=bold, color=color, anchor=anchor)
        midy = (y0 + y1) / 2
        if tx > x1 + 4:      # leader leaves from the side of the text that faces the target
            sx, sy = x1 + 10, midy
        elif tx < x0 - 4:
            sx, sy = x0 - 10, midy
        else:
            sx, sy = (x0 + x1) / 2, (y1 + 6 if ty > y1 else y0 - 6)
        d = math.hypot(tx - sx, ty - sy) or 1
        ex, ey = tx - (tx - sx) / d * 4, ty - (ty - sy) / d * 4
        mk = f' marker-end="url(#{self._marker(line_color)})"' if arrow else ""
        self._add("arrows", f'<line x1="{_f(sx)}" y1="{_f(sy)}" x2="{_f(ex)}" y2="{_f(ey)}" stroke="{line_color}" '
                            f'stroke-width="1.6"{mk}/>')

    # ---------- cells ----------
    _CELL_STYLES = {
        # kind: (fill inner, fill outer, membrane, nucleus)
        "tumor": ("#F1EDFB", "#D4CAF0", "#9C8AD6", "#8B78C9"),
        "t_cell": ("#EAF3FD", "#C2DAF4", "#7FA4D8", "#6E95CF"),
        "nk_cell": ("#EAF7EF", "#C5E6D1", "#6FB58A", "#5E9F78"),
        "macrophage": ("#FDF1E6", "#F3D5B8", "#D69A62", "#C4854C"),
        "generic": ("#F2F4F1", "#D9E0D4", "#93A58A", "#7F9276"),
    }

    def cell(self, kind="tumor", cx=800, cy=600, rx=300, ry=None, label=None, label_at=None, label_size=22,
             nucleus=True, colors=None):
        """Draw a cell. kind: tumor | t_cell | nk_cell | macrophage | generic. ry defaults to rx.
        label_at=(x, y) overrides the default label spot near the bottom inside the cell."""
        ry = ry or rx
        fin, fout, mem, nuc = colors or self._CELL_STYLES.get(kind, self._CELL_STYLES["generic"])
        gid = self._radial(fin, fout)
        parts = [f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(rx)}" ry="{_f(ry)}" fill="url(#{gid})" '
                 f'stroke="{mem}" stroke-width="7"/>',
                 f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(rx - 8)}" ry="{_f(ry - 8)}" fill="none" '
                 f'stroke="{mix(mem, "#FFFFFF", 0.45)}" stroke-width="2"/>']
        rng = random.Random(int(cx * 7 + cy * 13 + rx))
        if kind == "t_cell" or kind == "nk_cell":
            ncx, ncy, nrx, nry = cx + 0.12 * rx, cy + 0.05 * ry, 0.52 * rx, 0.5 * ry
        else:
            ncx, ncy, nrx, nry = cx + 0.24 * rx, cy - 0.02 * ry, min(0.3 * rx, 0.45 * ry), min(0.42 * ry, 0.34 * rx)
        for _ in range(int(18 + (rx * ry) / 2500)):
            fx, fy = rng.uniform(-0.85, 0.85), rng.uniform(-0.85, 0.85)
            if fx * fx + fy * fy > 0.72:
                continue
            px, py = cx + fx * rx, cy + fy * ry
            if nucleus and ((px - ncx) / (nrx + 14)) ** 2 + ((py - ncy) / (nry + 14)) ** 2 < 1:
                continue
            parts.append(f'<circle cx="{_f(px)}" cy="{_f(py)}" r="{_f(rng.uniform(1.6, 3.4))}" fill="{mem}" '
                         f'fill-opacity="0.35"/>')
        if nucleus:
            if kind not in ("t_cell", "nk_cell"):
                er = mix(mem, "#FFFFFF", 0.25)
                for k in range(3):
                    r1 = nrx + 26 + k * 13
                    parts.append(f'<path d="M{_f(ncx - r1 * 0.95)},{_f(ncy - nry * 0.55)} '
                                 f'Q{_f(ncx - r1 * 1.18)},{_f(ncy)} {_f(ncx - r1 * 0.95)},{_f(ncy + nry * 0.6)}" '
                                 f'fill="none" stroke="{er}" stroke-width="3.2" stroke-linecap="round" '
                                 f'stroke-opacity="0.8"/>')
            ngid = self._radial(mix(nuc, "#FFFFFF", 0.35), nuc)
            parts.append(f'<ellipse cx="{_f(ncx)}" cy="{_f(ncy)}" rx="{_f(nrx)}" ry="{_f(nry)}" fill="url(#{ngid})" '
                         f'stroke="{darken(nuc, 0.15)}" stroke-width="3"/>')
            for _ in range(22):
                fx, fy = rng.uniform(-0.75, 0.75), rng.uniform(-0.75, 0.75)
                if fx * fx + fy * fy > 0.6:
                    continue
                parts.append(f'<circle cx="{_f(ncx + fx * nrx)}" cy="{_f(ncy + fy * nry)}" '
                             f'r="{_f(rng.uniform(2.5, 6.5))}" fill="{darken(nuc, 0.22)}" fill-opacity="0.45"/>')
        self._add("cells", "".join(parts))
        for px, py in ((cx - rx, cy), (cx + rx, cy), (cx, cy - ry), (cx, cy + ry)):
            self._track(px, py, f"{kind} cell edge")
        c = Cell(kind, cx, cy, rx, ry, label)
        if label:
            lx, ly = label_at or (cx - 0.05 * rx, cy + 0.74 * ry)
            self.label(label, lx, ly, size=label_size, bold=True)
        return c

    # ---------- receptors ----------
    def _receptor_svg(self, color, shape="y"):
        dk = darken(color, 0.25)
        stalk = (f'<rect x="-2" y="-1" width="4" height="10" rx="2" fill="{dk}"/>'
                 f'<rect x="-3.2" y="-30" width="6.4" height="31" rx="3.2" fill="{color}" stroke="{dk}" '
                 f'stroke-width="1"/>')
        if shape == "knob":
            return stalk + f'<circle cx="0" cy="-37" r="8.5" fill="{color}" stroke="{dk}" stroke-width="1"/>'
        return stalk + (f'<ellipse cx="-7" cy="-38" rx="5.6" ry="10.5" transform="rotate(-24 -7 -38)" '
                        f'fill="{color}" stroke="{dk}" stroke-width="1"/>'
                        f'<ellipse cx="7" cy="-38" rx="5.6" ry="10.5" transform="rotate(24 7 -38)" '
                        f'fill="{color}" stroke="{dk}" stroke-width="1"/>')

    def receptor(self, cell, angle, color=TEAL, name=None, scale=1.0, shape="y"):
        """A transmembrane receptor on `cell` at parametric `angle` (0 right, -90 top, 90 bottom, 180 left).
        shape: 'y' (two-lobed head) or 'knob'. Returns a Site whose tip is the binding site."""
        (px, py), (nx, ny) = cell.point(angle)
        psi = _psi_of(nx, ny)
        s = RECEPTOR_SCALE * scale
        self._add("receptors", f'<g transform="translate({_f(px)},{_f(py)}) rotate({_f(psi)}) scale({s:.3f})">'
                               f'{self._receptor_svg(color, shape)}</g>')
        ox, oy = _dir(psi)
        tip = (px + ox * RECEPTOR_TIP * s, py + oy * RECEPTOR_TIP * s)
        self._track(*tip, f"receptor {name or ''}")
        return Site(tip[0], tip[1], psi, name, base=(px, py), color=color)

    # ---------- antibodies ----------
    @staticmethod
    def _fab_svg(tip_color):
        vh, vl = tip_color, mix(tip_color, "#FFFFFF", 0.38)
        return (f'<rect x="-4.6" y="-31" width="9.2" height="28" rx="4.6" fill="{HEAVY}" stroke="{HEAVY_DK}" '
                f'stroke-width="1.1"/>'
                f'<rect x="-4.6" y="-60" width="9.2" height="27" rx="4.6" fill="{vh}" stroke="{darken(vh, 0.25)}" '
                f'stroke-width="1.1"/>'
                f'<rect x="5.6" y="-30" width="9.2" height="24" rx="4.6" fill="{LIGHT}" stroke="{LIGHT_DK}" '
                f'stroke-width="1.1"/>'
                f'<rect x="5.6" y="-60" width="9.2" height="27" rx="4.6" fill="{vl}" stroke="{darken(vl, 0.25)}" '
                f'stroke-width="1.1"/>')

    @staticmethod
    def _payload_svg():
        zig = " ".join(f"{(-2.6 if i % 2 else 2.6) if 0 < i < 6 else 0},{-i * 2.6:.1f}" for i in range(7))
        hexa = " ".join(f"{6.2 * math.cos(math.radians(60 * k + 30)):.2f},"
                        f"{-22 + 6.2 * math.sin(math.radians(60 * k + 30)):.2f}" for k in range(6))
        return (f'<polyline points="{zig}" fill="none" stroke="#555A66" stroke-width="1.3" stroke-linejoin="round"/>'
                f'<polygon points="{hexa}" fill="{PAYLOAD}" stroke="{PAYLOAD_DK}" stroke-width="1.2"/>')

    _PAYLOAD_SITES = [(-10.4, 13, -75), (10.4, 13, 75), (-10.4, 45, -105), (10.4, 45, 105),
                      (-10.4, 26, -90), (10.4, 26, 90), (-10.4, 53, -125), (10.4, 53, 125)]

    def _antibody_local(self, arms, payloads, scfv, arm_angle):
        left_c, right_c = arms
        a = arm_angle
        parts = [
            f'<rect x="-6.6" y="-3" width="3" height="10" rx="1.5" fill="{HEAVY_DK}"/>',
            f'<rect x="3.6" y="-3" width="3" height="10" rx="1.5" fill="{HEAVY_DK}"/>',
            f'<g transform="translate(4,-1) rotate({a})">{self._fab_svg(right_c)}</g>',
            f'<g transform="translate(-4,-1) scale(-1,1) rotate({a})">{self._fab_svg(left_c)}</g>',
        ]
        for x in (-10.4, 1.0):
            parts.append(f'<rect x="{x}" y="6" width="9.4" height="25" rx="4.7" fill="{HEAVY}" stroke="{HEAVY_DK}" '
                         f'stroke-width="1.1"/>')
            parts.append(f'<rect x="{x}" y="33" width="9.4" height="24" rx="4.7" fill="{HEAVY}" stroke="{HEAVY_DK}" '
                         f'stroke-width="1.1"/>')
        pts = {"hinge": (0.0, 0.0), "fc": (0.0, 57.0)}
        rx_, ry_ = _rot(5, -61, a)
        pts["right"] = (4 + rx_, -1 + ry_)
        pts["left"] = (-4 - rx_, -1 + ry_)
        dirs = {"right": a, "left": -a, "fc": 180.0, "hinge": 0.0}
        for i, (x, y, psi) in enumerate(self._PAYLOAD_SITES[:max(0, min(payloads, 8))]):
            parts.append(f'<g transform="translate({x},{y}) rotate({psi})">{self._payload_svg()}</g>')
            ox, oy = _dir(psi)
            pts[f"payload{i}"] = (x + ox * 22, y + oy * 22)
            dirs[f"payload{i}"] = psi
        if scfv:
            vl = mix(scfv, "#FFFFFF", 0.38)
            parts.append('<path d="M0,57 q4.5,3 0,6 q-4.5,3 0,6" fill="none" stroke="#555A66" stroke-width="1.4"/>')
            parts.append(f'<rect x="-9.6" y="69" width="9.2" height="24" rx="4.6" fill="{scfv}" '
                         f'stroke="{darken(scfv, 0.25)}" stroke-width="1.1"/>')
            parts.append(f'<rect x="0.4" y="69" width="9.2" height="24" rx="4.6" fill="{vl}" '
                         f'stroke="{darken(vl, 0.25)}" stroke-width="1.1"/>')
            pts["scfv"] = (0.0, 94.0)
            dirs["scfv"] = 180.0
        return "".join(parts), pts, dirs

    def antibody(self, dock=None, arm="left", at=None, rotation=0.0, arms=(HEAVY, HEAVY), payloads=0, scfv=None,
                 scale=1.0, arm_angle=35, gap=2.0, align="fc", tilt=0.0, name=None):
        """Draw an IgG-like antibody and return its Antibody geometry.
        arms=(left_tip_color, right_tip_color) colors the variable domains by specificity.
        payloads=0..8 draws drug payloads on cleavable linkers along the Fc (an ADC).
        scfv=color adds an scFv binder on the Fc C-terminus (e.g. an anti-CD3 arm).
        Placement, either:
          dock=Site, arm='left'|'right'|'scfv'  -> that binder's tip sits on the site;
              align='fc' (default for Fab arms): the Fc points straight away from the cell, the classic
              upside-down Y; align='arm': the docked arm lines up with the receptor axis (always used for
              scfv); tilt=degrees rotates the whole antibody about the docked tip;
          at=(x, y) hinge position, rotation=degrees clockwise (0 = Fc pointing down)."""
        svg, pts, dirs = self._antibody_local(arms, payloads, scfv, arm_angle)
        s = ANTIBODY_SCALE * scale
        if dock is not None:
            if arm not in pts or arm not in ("left", "right", "scfv"):
                raise ValueError(f"arm must be left, right or scfv (scfv needs scfv=color); got {arm!r}")
            if align == "fc" and arm != "scfv":
                alpha = dock.psi - 180.0 + tilt
            else:
                alpha = dock.psi + 180.0 - dirs[arm] + tilt
            lx, ly = pts[arm]
            rx_, ry_ = _rot(lx * s, ly * s, alpha)
            ox, oy = dock.outward()
            tx, ty = dock.x + ox * gap - rx_, dock.y + oy * gap - ry_
        else:
            if at is None:
                raise ValueError("give dock=Site or at=(x, y)")
            alpha, (tx, ty) = rotation, at
        self._add("molecules", f'<g transform="translate({_f(tx)},{_f(ty)}) rotate({_f(alpha)}) scale({s:.3f})">'
                               f'{svg}</g>')
        ab = Antibody(tx, ty, alpha, s, pts, dirs, name)
        for k, p in ab.points().items():
            self._track(*p, f"antibody {name or ''} {k}")
        return ab

    def cell_for(self, binder, which="scfv", kind="t_cell", r=110, receptor_color=GRAY, receptor_name=None,
                 label=None, receptor_scale=1.0, gap=2.0, receptor_shape="y"):
        """Place a new round cell so that one of its receptors meets binder.tip(which) (for example a
        T cell engaged by a T-cell engager's anti-CD3 scFv). Returns (cell, site)."""
        tx, ty = binder.tip(which)
        dx, dy = binder.direction(which)
        bx, by = tx + dx * gap, ty + dy * gap
        h = RECEPTOR_TIP * RECEPTOR_SCALE * receptor_scale
        mx, my = bx + dx * h, by + dy * h
        cx, cy = mx + dx * r, my + dy * r
        c = self.cell(kind, cx, cy, r, r, label=label, label_at=(cx, cy + r * 0.62) if label else None,
                      label_size=20)
        angle = math.degrees(math.atan2(my - cy, mx - cx))
        site = self.receptor(c, angle, receptor_color, receptor_name, receptor_scale, receptor_shape)
        return c, site

    # ---------- other marks ----------
    def payload(self, x, y, angle=0.0, scale=1.0):
        """A free payload (e.g. released inside the cell); angle rotates it."""
        s = ANTIBODY_SCALE * scale
        self._add("molecules", f'<g transform="translate({_f(x)},{_f(y)}) rotate({_f(angle)}) scale({s:.3f}) '
                               f'translate(0,22)">{self._payload_svg()}</g>')
        self._track(x, y, "payload")

    def arrow(self, start, end, curve=0.0, dashed=False, color=TEXT, width=2.0, head=True):
        """Straight or curved arrow; curve bends it sideways by that fraction of its length."""
        (x1, y1), (x2, y2) = start, end
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L = math.hypot(x2 - x1, y2 - y1) or 1
        nx, ny = -(y2 - y1) / L, (x2 - x1) / L
        qx, qy = mx + nx * curve * L, my + ny * curve * L
        dash = ' stroke-dasharray="7 6"' if dashed else ""
        mk = f' marker-end="url(#{self._marker(color)})"' if head else ""
        self._add("arrows", f'<path d="M{_f(x1)},{_f(y1)} Q{_f(qx)},{_f(qy)} {_f(x2)},{_f(y2)}" fill="none" '
                            f'stroke="{color}" stroke-width="{width}"{dash} stroke-linecap="round"{mk}/>')
        self._track(x1, y1, "arrow")
        self._track(x2, y2, "arrow")

    def granules(self, start, end, n=7, color=PURPLE, r=5.0, curve=0.0):
        """A trail of granules (e.g. perforin/granzyme) from start to end."""
        (x1, y1), (x2, y2) = start, end
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L = math.hypot(x2 - x1, y2 - y1) or 1
        nx, ny = -(y2 - y1) / L, (x2 - x1) / L
        qx, qy = mx + nx * curve * L, my + ny * curve * L
        out = []
        for i in range(n):
            t = (i + 0.5) / n
            x = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * qx + t * t * x2
            y = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * qy + t * t * y2
            out.append(f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{_f(r * (0.8 + 0.4 * ((i * 37) % 5) / 4))}" '
                       f'fill="{color}" fill-opacity="0.8"/>')
        self._add("molecules", "".join(out))

    def legend(self, items, y=None, margin=40, size=15, title=None):
        """A legend box. items: (kind, text) or (kind, text, color) with kind one of igg, adc, payload,
        receptor, scfv, granule, t_cell, tumor. Wraps to more rows as needed. With fit=True and no y it
        is placed under the finished drawing at save time; otherwise it runs along the bottom (or at y)."""
        for it in items:
            self._legend_icon(it[0], 0, 0, it[2] if len(it) > 2 else None)   # fail early on a bad kind
        if y is None and self.fit:
            self._legend_req = dict(items=items, margin=margin, size=size, title=title)
            return None
        return self._legend_draw(items, margin, self.w - 2 * margin, self.h - margin if y is None else None,
                                 y, size, title, "labels")

    def _legend_draw(self, items, x_left, box_w, bottom, top, size, title, layer, shrink=False):
        icon_w, pad, gap = 58, 18, 26
        widths = []
        for it in items:
            lines = it[1].split("\n")
            widths.append(icon_w + 8 + max(self._text_width(t, size, False) for t in lines))
        avail = box_w - 2 * pad
        rows, row, used = [], [], 0
        for i, wd in enumerate(widths):
            if row and used + gap + wd > avail:
                rows.append(row)
                row, used = [], 0
            used += (gap if row else 0) + wd
            row.append(i)
        if row:
            rows.append(row)
        row_h = 62
        box_h = pad * 2 + row_h * len(rows) + (26 if title else 0)
        if shrink:   # box hugs its widest row, centered where it was
            widest = max(sum(widths[i] for i in r) + gap * (len(r) - 1) for r in rows)
            if title:
                widest = max(widest, self._text_width(title, size + 1, True))
            x_left, box_w, avail = x_left + (box_w - widest - 2 * pad) / 2, widest + 2 * pad, widest
        y0 = top if top is not None else bottom - box_h
        out = [f'<rect x="{_f(x_left)}" y="{_f(y0)}" width="{_f(box_w)}" height="{_f(box_h)}" rx="10" '
               f'fill="#FFFFFF" stroke="#C9CDD6" stroke-width="1.4"/>']
        if title:
            out.append(f'<text x="{_f(x_left + pad)}" y="{_f(y0 + pad + 14)}" font-size="{size + 1}" '
                       f'font-weight="700" fill="{TEXT}">{_esc(title)}</text>')
        for r_i, row in enumerate(rows):
            total = sum(widths[i] for i in row) + gap * (len(row) - 1)
            x = x_left + pad + (avail - total) / 2
            cy = y0 + pad + (26 if title else 0) + row_h * r_i + row_h / 2
            for i in row:
                kind, text = items[i][0], items[i][1]
                color = items[i][2] if len(items[i]) > 2 else None
                out.append(self._legend_icon(kind, x + icon_w / 2, cy, color))
                lines = text.split("\n")
                ty = cy - (len(lines) - 1) * size * 0.62 + size * 0.35
                spans = "".join(f'<tspan x="{_f(x + icon_w + 8)}" dy="{0 if k == 0 else _f(size * 1.25)}">'
                                f'{_esc(t)}</tspan>' for k, t in enumerate(lines))
                out.append(f'<text x="{_f(x + icon_w + 8)}" y="{_f(ty)}" font-size="{size}" fill="{TEXT}">{spans}</text>')
                x += widths[i] + gap
        self._add(layer, "".join(out))
        self._boxes.append((x_left, y0, x_left + box_w, y0 + box_h, "<legend>"))
        if layer == "frame":
            self._frame.add(len(self._boxes) - 1)
        return (x_left, y0, x_left + box_w, y0 + box_h)

    def _legend_icon(self, kind, x, y, color):
        if kind in ("igg", "adc"):
            c = color or HEAVY
            svg, _, _ = self._antibody_local((c, c), 4 if kind == "adc" else 0, None, 35)
            return f'<g transform="translate({_f(x)},{_f(y - 6)}) scale(0.42)">{svg}</g>'
        if kind == "payload":
            return f'<g transform="translate({_f(x - 14)},{_f(y)}) rotate(90) scale(1.25)">{self._payload_svg()}</g>'
        if kind == "receptor":
            return (f'<g transform="translate({_f(x)},{_f(y + 22)}) scale(0.95)">'
                    f'{self._receptor_svg(color or TEAL)}</g>')
        if kind == "scfv":
            c = color or GRAY
            vl = mix(c, "#FFFFFF", 0.38)
            return (f'<g transform="translate({_f(x)},{_f(y)}) scale(1.2)">'
                    f'<rect x="-9.6" y="-12" width="9.2" height="24" rx="4.6" fill="{c}" stroke="{darken(c, .25)}"/>'
                    f'<rect x="0.4" y="-12" width="9.2" height="24" rx="4.6" fill="{vl}" stroke="{darken(vl, .25)}"/>'
                    f'</g>')
        if kind == "granule":
            c = color or PURPLE
            return "".join(f'<circle cx="{_f(x + dx)}" cy="{_f(y + dy)}" r="5" fill="{c}" fill-opacity="0.8"/>'
                           for dx, dy in ((-10, 4), (0, -7), (10, 4)))
        if kind in ("t_cell", "tumor"):
            fin, fout, mem, _ = self._CELL_STYLES["t_cell" if kind == "t_cell" else "tumor"]
            return (f'<circle cx="{_f(x)}" cy="{_f(y)}" r="20" fill="{fout}" stroke="{mem}" stroke-width="4"/>')
        raise ValueError(f"unknown legend kind {kind!r}")

    # ---------- output ----------
    def check(self, margin=6):
        """Layout warnings: things off the canvas and text boxes that overlap each other."""
        warns = []
        for x, y, what in self._extent:
            if x < margin or y < margin or x > self.w - margin or y > self.h - margin:
                warns.append(f"{what.strip()} at ({x:.0f}, {y:.0f}) is outside the canvas")
        for k, (x0, y0, x1, y1, t) in enumerate(self._boxes):
            if k in self._frame and self._viewbox != (0, 0, self.w, self.h):
                continue
            if x0 < margin or y0 < margin or x1 > self.w - margin or y1 > self.h - margin:
                warns.append(f"text '{t}' runs off the canvas (box {x0:.0f},{y0:.0f}-{x1:.0f},{y1:.0f})")
        b = self._boxes
        for i in range(len(b)):
            for j in range(i + 1, len(b)):
                ox = min(b[i][2], b[j][2]) - max(b[i][0], b[j][0])
                oy = min(b[i][3], b[j][3]) - max(b[i][1], b[j][1])
                if ox > 2 and oy > 2:
                    warns.append(f"text '{b[i][4]}' overlaps text '{b[j][4]}'")
        for x, y, what in self._extent:
            for x0, y0, x1, y1, t in self._boxes:
                if x0 < x < x1 and y0 < y < y1 and ("cell edge" not in what or t == "<legend>"):
                    warns.append(f"text '{t}' covers {what.strip()}")
        return sorted(set(warns))

    def svg(self, frame=True, viewbox=None):
        vx, vy, vw, vh = viewbox or self._viewbox
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(vw)}" height="{_f(vh)}" '
                f'viewBox="{_f(vx)} {_f(vy)} {_f(vw)} {_f(vh)}" font-family="{FONT}">')
        body = [f'<defs>{"".join(self._defs.values())}</defs>',
                f'<rect x="{_f(vx)}" y="{_f(vy)}" width="{_f(vw)}" height="{_f(vh)}" fill="{self.bg}"/>']
        for layer in self.LAYERS:
            if layer == "frame" and not frame:
                continue
            body.append(f'<g id="{layer}">{"".join(self._layers[layer])}</g>')
        return head + "".join(body) + "</svg>"

    def _content_bbox(self):
        """Pixel bounds of everything drawn so far except the title, subtitle and legend, or None."""
        try:
            import cairosvg
            from PIL import Image, ImageChops
        except ImportError:
            return None
        png = cairosvg.svg2png(bytestring=self.svg(frame=False, viewbox=(0, 0, self.w, self.h)).encode("utf-8"),
                               output_width=self.w)
        im = Image.open(io.BytesIO(png)).convert("RGB")
        diff = ImageChops.difference(im, Image.new("RGB", im.size, self.bg)).convert("L")
        return diff.point(lambda v: 255 if v > 10 else 0).getbbox()

    def _place_frame(self, bbox):
        """Draw title, subtitle and legend around bbox (or the fixed canvas when bbox is None) and set
        the view box."""
        if bbox is None:
            if self._title:
                self.label(self._title, self.w / 2, 58, size=30, bold=True, layer="frame")
            if self._subtitle:
                self.label(self._subtitle, self.w / 2, 94, size=19, color=MUTED, layer="frame")
            if self._legend_req:
                r = self._legend_req
                self._legend_draw(r["items"], r["margin"], self.w - 2 * r["margin"], self.h - r["margin"], None,
                                  r["size"], r["title"], "frame")
            self._viewbox = (0, 0, self.w, self.h)
            return
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) / 2
        boxes = [(x0, y0, x1, y1)]
        yt = y0 - 40 - (34 if self._subtitle else 0)
        if self._title:
            boxes.append(self.label(self._title, cx, yt, size=30, bold=True, layer="frame"))
        if self._subtitle:
            boxes.append(self.label(self._subtitle, cx, yt + 34 if self._title else y0 - 40, size=19,
                                    color=MUTED, layer="frame"))
        if self._legend_req:
            r = self._legend_req
            width = max(x1 - x0, 900)
            boxes.append(self._legend_draw(r["items"], cx - width / 2, width, None, y1 + 36, r["size"],
                                           r["title"], "frame", shrink=True))
        pad = 36
        vx0 = min(b[0] for b in boxes) - pad
        vy0 = min(b[1] for b in boxes) - pad
        vx1 = max(b[2] for b in boxes) + pad
        vy1 = max(b[3] for b in boxes) + pad
        self._viewbox = (vx0, vy0, vx1 - vx0, vy1 - vy0)

    def save(self, path, png=True):
        """Write the SVG, figure PNGs next to it (1x and @2x, when a renderer is available) and
        <name>.warnings.json. Prints the layout warnings. With fit=True the title, subtitle and legend
        are placed around the drawing here and the image is trimmed to it."""
        if not any(k in self._frame for k in range(len(self._boxes))):   # place the frame once
            self._place_frame(self._content_bbox() if self.fit else None)
        svg = self.svg()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        warns = self.check()
        base = os.path.splitext(path)[0]
        with open(base + ".warnings.json", "w") as fh:
            json.dump(warns, fh, indent=1)
        for w in warns:
            print("WARNING:", w)
        if png:
            vw = round(self._viewbox[2])
            render_png(path, base + ".png", vw)
            render_png(path, base + "@2x.png", 2 * vw)
        return warns


def render_png(svg_path, png_path, width=1600):
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=width)
        return png_path
    except ImportError:
        pass
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-w", str(width), "-o", png_path, svg_path], check=True)
        return png_path
    print("NOTE: no SVG renderer (cairosvg or rsvg-convert); PNG not written")
    return None
