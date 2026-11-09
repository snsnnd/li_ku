"""ASRS V02 engineering prototype. Millimetres, Z up; no V01 files are written.

Purchased parts are explicitly simplified envelopes, not supplier-certified models.
Exact B-rep interference checks are separate from dimensional and load calculations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "model" / "V02"
_GENERATOR_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def source_sha256():
    return _GENERATOR_SHA256


@dataclass(frozen=True)
class Design:
    columns: int = 4
    rows: int = 5
    column_pitch: float = 150.0
    row_pitch: float = 95.0
    first_deck: float = 200.0
    tray_y: float = -78.0
    storage_y: float = 65.0
    eye_offset_y: float = -68.0
    y_rail_min: float = -225.0
    y_rail_max: float = -25.0
    y_block_to_pin: float = 50.0
    y_block_length: float = 39.9
    z_rail_min: float = 85.0
    z_rail_max: float = 585.0
    z_block_length: float = 45.4
    z_block_offsets: tuple = (-79.0, -29.0)
    x_block_offsets: tuple = (-40.0, 40.0)
    payload_kg: float = 1.0

    @property
    def x_positions(self):
        return [(i + .5) * self.column_pitch for i in range(self.columns)]

    @property
    def decks(self):
        return [self.first_deck + i * self.row_pitch for i in range(self.rows)]

    @property
    def transfer(self):
        return self.storage_y - self.tray_y


def box(x, y, z, w, d, h):
    """Centre X/Y, BOTTOM Z; intentionally not a bounding-box centre API."""
    return cq.Solid.makeBox(w, d, h, cq.Vector(x-w/2, y-d/2, z))


def cyl(x, y, z, r, length, axis=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, length, cq.Vector(x, y, z), cq.Vector(*axis))


def fuse(*shapes):
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result.clean()


def drill(shape, holes):
    for h in holes:
        p, axis, dia, length = h
        shape = shape.cut(cyl(*p, dia/2, length, axis))
    return shape.clean()


def hz(x, y, z, dia, length):
    return ((x, y, z), (0, 0, 1), dia, length)


def hy(x, y, z, dia, length):
    return ((x, y, z), (0, 1, 0), dia, length)


def hx(x, y, z, dia, length):
    return ((x, y, z), (1, 0, 0), dia, length)


def slot_y(x, y, z, length, diameter, height):
    straight = length-diameter
    return fuse(box(x, y, z, diameter, straight, height),
                cyl(x, y-straight/2, z, diameter/2, height),
                cyl(x, y+straight/2, z, diameter/2, height))


COLORS = {
    "aluminum": (.64, .69, .73), "steel": (.28, .33, .38),
    "PETG": (.15, .61, .78), "POM": (.88, .78, .37),
    "rubber": (.12, .14, .16), "purchased": (.25, .29, .34),
    "guard": (.57, .79, .85, .18), "safety": (.90, .28, .15),
}


@dataclass
class Part:
    name: str
    shape: cq.Shape
    material: str
    process: str
    holes: list = field(default_factory=list)
    note: str = ""


@dataclass
class Instance:
    name: str
    part: Part
    origin: tuple
    group: str = "fixed"

    def located(self, dx=0, dz=0, q=0, pin_lift=0, bin_q=None):
        x, y, z = self.origin
        if self.group != "fixed":
            x += dx
        if self.group in ("z", "y", "pin", "bin", "crank", "roller", "spring"):
            z += dz
        if self.group in ("y", "pin", "bin", "crank", "roller", "spring"):
            y += bin_q if self.group == "bin" and bin_q is not None else q
        if self.group in ("pin", "roller"):
            z += pin_lift
        shape = self.part.shape
        if self.group == "spring":
            height = 16-pin_lift
            if height <= 0:
                raise ValueError("Return spring coil-bound")
            shape = cyl(0, 0, 0, 3.5, height).cut(cyl(0, 0, -1, 3.2, height+2))
            z += pin_lift
        phi = math.acos(max(-1, min(1, 1-pin_lift/7)))
        if self.group == "roller":
            y += 7*math.sin(phi)
        if self.group == "crank":
            shape = shape.rotate((0, 0, 0), (1, 0, 0), math.degrees(phi))
        return shape.translate((x, y, z))


class Model:
    def __init__(self, design=Design()):
        self.d = design
        self.parts = {}
        self.items = []
        self.allowed = {}  # Explicit pair -> physical reason, NEVER group-wide exclusions.
        self.x = design.x_positions[1]
        self.deck = design.decks[2]

    def part(self, name, shape, material="aluminum", process="machined", holes=(), note=""):
        if name in self.parts:
            return self.parts[name]
        if not shape.isValid() or len(shape.Solids()) != 1:
            raise ValueError(f"Invalid/non-single solid: {name}")
        p = Part(name, shape, material, process, list(holes), note)
        self.parts[name] = p
        return p

    def add(self, name, p, origin=(0, 0, 0), group="fixed"):
        if any(i.name == name for i in self.items):
            raise ValueError("Duplicate instance " + name)
        i = Instance(name, p, origin, group)
        self.items.append(i)
        return i

    def allow(self, a, b, reason):
        self.allowed[tuple(sorted((a, b)))] = reason


def extrusion(w, length, axis):
    """Conservative square extrusion with centre bore; slots are supplier-dependent."""
    core_r = 3.4 if w == 30 else 2.1  # Specified end taps: M8 for 3030, M5 for 2020.
    if axis == "X":
        s = box(0, 0, 0, length, w, w)
        return s.cut(cyl(-length/2-1, 0, w/2, core_r, length+2, (1, 0, 0)))
    if axis == "Y":
        s = box(0, 0, 0, w, length, w)
        return s.cut(cyl(0, -length/2-1, w/2, core_r, length+2, (0, 1, 0)))
    return box(0, 0, 0, w, w, length).cut(cyl(0, 0, -1, core_r, length+2))


def make_bin():
    s = box(0, 0, 0, 110, 120, 60).cut(box(0, 0, 2.4, 105.2, 115.2, 60))
    # Horizontal, thickened tow eye. A metal pin engages along Z, not by forced rotation.
    eye = box(0, -67, 10, 32, 18, 6)
    eye = eye.cut(cyl(0, -68, 9, 3.1, 8))
    return s.fuse(eye).clean()


def deck_plate():
    s = fuse(box(0, 0, 0, 124, 130, 4),
             box(-57.1, 0, 4, 3, 130, 6), box(57.1, 0, 4, 3, 130, 6))
    holes = [hz(x, y, -1, 4.5, 6) for x in (-52, 52) for y in (-50, 50)]
    return drill(s, holes), holes


def rail_shape(width, height, length, pitch):
    s = box(0, 0, 0, width, length, height)
    holes = [hz(0, -length/2+10+i*pitch, -1, 3.5, height+2)
             for i in range(int((length-20)/pitch)+1)]
    return drill(s, holes), holes


def block_shape(width, length, h1, total_h, rail_w, rail_h, spacing):
    s = box(0, 0, h1, width, length, total_h-h1)
    # Rail channel (rolling raceways are not modeled). No false stacking of heights.
    s = s.cut(box(0, 0, h1-1, rail_w+.4, length+2, rail_h-h1+1.2))
    sx, sy = spacing if isinstance(spacing, tuple) else (spacing, spacing)
    holes = [hz(x, y, total_h-4, 2.5, 5)
             for x in (-sx/2, sx/2) for y in (-sy/2, sy/2)]
    return drill(s, holes), holes


def pulley():
    s = fuse(cyl(0, 0, 0, 8.5, 1), cyl(0, 0, 1, 6.1, 7), cyl(0, 0, 8, 8.5, 1))
    return s.cut(cyl(0, 0, -1, 2.6, 11))


def belt_shape(distance):
    # GT2 purchased belt: smooth effective envelope, NOT a manufacturable tooth profile.
    r, t = 6.3, 1.4
    a = box(-r-t/2, distance/2, 1.5, t, distance, 6)
    b = box(r+t/2, distance/2, 1.5, t, distance, 6)
    bottom = cyl(0, 0, 1.5, r+t, 6).cut(cyl(0, 0, 1, r, 7))
    bottom = bottom.intersect(box(0, -r-t, 1, 30, 2*(r+t), 8))
    top = cyl(0, distance, 1.5, r+t, 6).cut(cyl(0, distance, 1, r, 7))
    top = top.intersect(box(0, distance+r+t, 1, 30, 2*(r+t), 8))
    return fuse(a, b, bottom, top)


def build_model(d=Design()):
    if d != Design():
        raise ValueError("V02 is a frozen 4x5 baseline; changed parameters require coordinated interface redesign")
    m = Model(d)
    x, D = m.x, m.deck
    # Continuous datum plate, anchored to the workbench; no edge-only base joints.
    feet = [(c*150, yy) for c in range(5) for yy in (10, 140)]
    feet += [(xx, yy) for xx in (-70, 670) for yy in (-330, 170)]
    holes = [hz(a, b, -1, 6.5, 8) for a in (-35, 635) for b in (-320, 160)]
    holes += [hz(xx+a, yy+b, -1, 4.2, 8) for xx, yy in feet for a in (-14, 14) for b in (-14, 14)]
    rail_fix_x = (-27.5, 97.5, 222.5, 347.5, 472.5, 622.5)
    holes += [hz(xx, yy, -1, 4.2, 8) for xx in rail_fix_x for yy in (-285, -215)]
    holes += [hz(xx, yy, -1, 4.2, 8) for xx in (630, 660, 675) for yy in (-261, -239)]
    holes += [hz(xx, yy, -1, 4.2, 8) for xx in (-73, -17) for yy in (-265, -235)]
    base = m.part("Base_780x540x6", drill(box(300, -80, 0, 780, 540, 6), holes), holes=holes)
    m.add("base", base)
    # Solid tapped datum bars remove ambiguous T-slot/rail-strip connections.
    beam_h = [hz(v, 0, 17, 2.5, 8) for v in range(-340, 341, 25)]
    beam_h += [hz(v-300, 0, -1, 5.5, 26) for v in rail_fix_x]
    beam_h += [hz(v-300, 0, 20, 9.5, 5) for v in rail_fix_x]
    bx = m.part("X_Datum_Bar_700x30x24", drill(box(0, 0, 0, 700, 30, 24), beam_h), holes=beam_h,
                note="6061; M3 tapped rail holes; 6x DIN7984 low-head M5x25 to base, head <=3.5 mm")
    for y in (-285, -215):
        m.add(f"rail_beam_{y}", bx, (300, y, 6))

    # Rack: front AND rear posts, metal shelf angles, rear shear panel.
    post = m.part("2020_Rack_Z650", extrusion(20, 650, "Z"), process="purchased")
    for c in range(d.columns+1):
        for y in (10, 140):
            m.add(f"rack_post_{c}_{y}", post, (c*d.column_pitch, y, 26))
    deck_s, deck_h = deck_plate()
    cell_s = fuse(deck_s, box(0, 64, 4, 124, 2, 6))
    cell = m.part("Cell_124x130", cell_s, "PETG", "print", deck_h,
                  "Print bottom down; add 0.5 mm entrance chamfer after fit coupon")
    bin_p = m.part("Bin_110x120_TowEye", make_bin(), "PETG", "print",
                   [hz(0, -68, 9, 6.2, 8)], "Open top UP; tow eye only takes horizontal force")
    for side in (-1, 1):
        # Left/right metal L20x23x3, contact faces coincide instead of overlapping.
        a = fuse(box(side*63.5, 0, -27, 3, 150, 23),
                 box(side*55, 0, -7, 20, 150, 3))
        hh = [hx(-70, yy, -17, 5.5, 140) for yy in (-65, 65)]
        hh += [hz(side*52, yy, -8, 3.3, 5) for yy in (-60, 40)]
        p = m.part(f"Shelf_Angle_{side}", drill(a, hh), holes=hh,
                   note="M5 to slot nuts front/rear, M4 tapped shelf attachment")
        for c, xx in enumerate(d.x_positions):
            for r, z in enumerate(d.decks):
                m.add(f"shelf_angle_{c}_{r}_{side}", p, (xx, 75, z))
    for c, xx in enumerate(d.x_positions):
        for r, z in enumerate(d.decks):
            m.add(f"cell_{c}_{r}", cell, (xx, 65, z-4))
            if (c, r) != (1, 2):
                m.add(f"stored_bin_{c}_{r}", bin_p, (xx, d.storage_y, z))
    rear_h = [hy(xx, 151, zz, 5.5, 6) for xx in (0, 150, 300, 450, 600) for zz in (50, 650)]
    rear = m.part("Rack_Rear_Shear_620x630x3", drill(box(300, 153.5, 45, 620, 3, 630), rear_h),
                  holes=rear_h, note="10 M5 slot-nut joints; panel is a structural shear diaphragm")
    # 2 mm standoffs prevent panel penetrating posts; fitted stand-offs included in BOM.
    m.add("rack_rear_shear", rear)
    stand = m.part("Rear_Panel_Standoff_2", cyl(0, 0, 0, 5, 2, (0, 1, 0)).cut(
                   cyl(0, -1, 0, 2.75, 4, (0, 1, 0))))
    for xx in (0, 150, 300, 450, 600):
        for zz in (50, 650):
            m.add(f"rear_panel_standoff_{xx}_{zz}", stand, (xx, 150, zz))
    foot_h = [hz(a, b, -1, 5.5, 8) for a in (-14, 14) for b in (-14, 14)]
    foot_h += [hz(0, 0, -1, 5.5, 8), hz(0, 0, -1, 9.5, 6)]
    foot = m.part("Rack_Foot_40x40x6", drill(box(0, 0, 0, 40, 40, 6), foot_h), holes=foot_h,
                 note="Central underside counterbore M5x12 to post end; 4x M5x25 through pedestal into base")
    # Feet occupy 20..26, above base with 14 mm metal pedestals (positive load path).
    ped_h = [hz(a, b, -1, 5.5, 16) for a in (-14, 14) for b in (-14, 14)]
    pedestal = m.part("Rack_Pedestal_40x40x14", drill(box(0, 0, 0, 40, 40, 14), ped_h), holes=ped_h)
    for c in range(5):
        for y in (10, 140):
            m.add(f"rack_pedestal_{c}_{y}", pedestal, (c*150, y, 6))
            m.add(f"rack_foot_{c}_{y}", foot, (c*150, y, 20))
    enclosure_post = m.part("2020_Guard_Z720", extrusion(20, 720, "Z"), process="purchased")
    enclosure_x = m.part("2020_Guard_X760", extrusion(20, 760, "X"), process="purchased")
    enclosure_y = m.part("2020_Guard_Y480", extrusion(20, 480, "Y"), process="purchased")
    for xx in (-70, 670):
        for yy in (-330, 170):
            m.add(f"guard_pedestal_{xx}_{yy}", pedestal, (xx, yy, 6))
            m.add(f"guard_foot_{xx}_{yy}", foot, (xx, yy, 20))
            m.add(f"guard_post_{xx}_{yy}", enclosure_post, (xx, yy, 26))
        m.add(f"guard_top_side_{xx}", enclosure_y, (xx, -80, 746))
    for yy in (-330, 170):
        m.add(f"guard_top_cross_{yy}", enclosure_x, (300, yy, 746))

    # X rails: H=13 relative to rail datum; blocks separated by 80 mm.
    rail_s, rail_h = rail_shape(12, 8, 700, 25)
    rail_s = rail_s.rotate((0, 0, 0), (0, 0, 1), -90)
    xr = m.part("MGN12_Rail_X700", rail_s, "steel", "purchased", note="HIWIN dimensional envelope")
    bs, bh = block_shape(27, 45.4, 3, 13, 12, 8, 20)
    xb = m.part("MGN12H_X", bs.rotate((0, 0, 0), (0, 0, 1), 90), "steel", "purchased")
    for y in (-285, -215):
        m.add(f"x_rail_{y}", xr, (300, y, 30))
        for off in d.x_block_offsets:
            m.add(f"x_block_{y}_{off}", xb, (x+off, y, 30), "x")
    xholes = [hz(off+a, yy+b, -1, 3.5, 10)
              for off in d.x_block_offsets for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    xholes += [hz(off+a, yy+b, 4.8, 6.2, 4.2)
               for off in d.x_block_offsets for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    xholes += [hz(xx, -18, -1, 8.5, 10) for xx in (-45, 45)]
    xholes += [hz(xx+off, yy, -1, 5.0, 10) for xx in (-45, 45) for off in (-8, 8) for yy in (-45, 9)]
    xholes += [hz(xx, 13, -1, 3.3, 10) for xx in (-9, 9)]
    xplate = m.part("X_Carriage_160x110x8", drill(box(0, 0, 0, 160, 110, 8), xholes), holes=xholes)
    m.add("x_carriage", xplate, (x, -250, 43), "x")

    # X belt, inverted motor above its mount, no body below the workbench.
    pul = m.part("GT2_20T_6mm_Envelope", pulley(), "purchased", "purchased",
                 note="Purchased 20T; teeth intentionally omitted, never print this envelope")
    xb_s = belt_shape(690).rotate((0, 0, 0), (0, 0, 1), -90)
    xb_p = m.part("X_GT2_Belt_Loop", xb_s, "rubber", "purchased")
    m.add("x_belt", xb_p, (-45, -250, 32))
    for name, xx in (("x_drive_pulley", -45), ("x_idler_pulley", 645)):
        m.add(name, pul, (xx, -250, 32))
    motor = m.part("NEMA17_42x42x40", fuse(box(0, 0, -40, 42, 42, 40), cyl(0, 0, 0, 2.5, 22)),
                   "purchased", "purchased", note="Vendor shaft/flange drawing required")
    inverted_motor = m.part("NEMA17_Inverted", motor.shape.rotate((0, 0, 0), (1, 0, 0), 180),
                            "purchased", "purchased", note=motor.note)
    m.add("x_motor", inverted_motor, (-45, -250, 54))
    xm_h = [hz(a, b, -1, 3.5, 7) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    xm_h += [hz(0, 0, -1, 23, 7)]
    xm_h += [hz(xx, yy, -1, 5.5, 7) for xx in (-28, 28) for yy in (-15, 15)]
    xm = m.part("X_Motor_Mount", drill(box(0, 0, 0, 68, 44, 5), xm_h), holes=xm_h)
    m.add("x_motor_mount", xm, (-45, -250, 49))
    xp_h = [hz(xx, 0, -1, 5.5, 45) for xx in (-28, 28)]
    xp_h += [hz(xx, yy, -1, 6.2, 45) for xx in (-15.5, 15.5) for yy in (-.5, .5)]
    xp = m.part("X_Motor_Mount_Leg", drill(box(0, 0, 0, 68, 10, 43), xp_h), holes=xp_h,
                note="Long M5x55 + two 1 mm washers clamp mount/leg to base; motor screws via access bores before installing module")
    for off in (-15, 15):
        m.add(f"x_motor_leg_{off}", xp, (-45, -250+off, 6))
    idler_s = fuse(box(0, 0, 0, 44, 36, 6), box(0, 0, 6, 16, 16, 18), cyl(0, 0, 24, 2.5, 12))
    for xx in (-15, 15):
        for yy in (-11, 11):
            cutter = slot_y(0, 0, -1, 10, 5.5, 8).rotate((0, 0, 0), (0, 0, 1), 90).translate((xx, yy, 0))
            idler_s = idler_s.cut(cutter)
    idler_post = m.part("X_Idler_Pedestal", idler_s,
                        note="Four 10x5.5 X slots, +/-2.25 mm adjustment; four M5 clamp bolts")
    m.add("x_idler_pedestal", idler_post, (645, -250, 6))
    xa_h = [hx(-6, 0, 3, 3.3, 12)] + [hz(0, yy, -1, 5.5, 20) for yy in (-11, 11)]
    xa = m.part("X_Tension_Adjuster", drill(box(0, 0, 0, 10, 30, 18), xa_h), holes=xa_h,
                note="M4x16 pusher plus jam nut, 4 mm tension travel; adjust with power isolated")
    m.add("x_tension_adjuster", xa, (675, -250, 6))
    xclamp_s = box(0, 0, 0, 28, 20, 8).cut(box(0, 0, -1, 30, 1.8, 5))
    xclamp_h = [hz(xx, 6, -1, 4.5, 10) for xx in (-9, 9)]
    xclamp = m.part("X_Belt_Clamp", drill(xclamp_s, xclamp_h), "PETG", "print", xclamp_h,
                   "Clamp with steel backing plate; tune groove using belt coupon")
    m.add("x_belt_clamp", xclamp, (x, -243, 35), "x")
    xback_h = [hz(xx, 0, -1, 4.5, 4) for xx in (-9, 9)]
    xback = m.part("X_Clamp_Steel_Backer", drill(box(0, 0, 0, 28, 8, 2), xback_h), "steel", holes=xback_h,
                   note="2x M4x16 from underside, 6 mm thread in X plate; bolts never cross belt lane")
    m.add("x_clamp_backer", xback, (x, -237, 33), "x")
    m.allow("x_belt_clamp", "x_belt", "Intentional clamped belt contact")

    # Z tower: two 3030s, bottom end faces seated ON X plate, not through cross plates.
    zp = m.part("3030_Z600", extrusion(30, 600, "Z"), process="purchased")
    for off in (-45, 45):
        m.add(f"z_post_{off}", zp, (x+off, -268, 51), "x")
    gus_h = [hz(a, -12, -1, 6.5, 6) for a in (-8, 8)]
    gus_h += [hy(0, -5, zz, 6.5, 7) for zz in (14, 26)]
    gus_s = fuse(box(0, -10, 0, 30, 20, 4), box(0, -2, 3, 30, 4, 29))
    gus = m.part("Z_Foot_Angle_30x20x32", drill(gus_s, gus_h), holes=gus_h,
                 note="M6 to 3030 slot nuts; M6x12 to X plate; rail starts 2 mm above bracket")
    gus_front = m.part("Z_Foot_Angle_Front", gus.shape.rotate((0, 0, 0), (0, 0, 1), 180),
                       holes=[hz(-a, 12, -1, 6.5, 6) for a in (-8, 8)] +
                             [((0, 5, zz), (0, -1, 0), 6.5, 7) for zz in (14, 26)], note=gus.note)
    for off in (-45, 45):
        m.add(f"z_foot_rear_{off}", gus, (x+off, -283, 51), "x")
        m.add(f"z_foot_front_{off}", gus_front, (x+off, -253, 51), "x")
    top_h = [hz(a, 0, -1, 8.5, 10) for a in (-45, 45)]
    top_h += [hz(a, b, -1, 3.5, 10) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    top_h += [hz(0, 0, -1, 23, 10)]
    top_h += [hz(xx, 0, -1, 4.5, 10) for xx in (-23, 23)]
    top = m.part("Z_Top_Motor_Plate_130x60x8", drill(box(0, 0, 0, 130, 60, 8), top_h), holes=top_h)
    m.add("z_top_plate", top, (x, -268, 651), "x")
    zrs, _ = rail_shape(12, 8, 500, 25)
    # Local rail Y -> world Z, local rail Z -> world +Y.
    zrs = zrs.rotate((0, 0, 0), (1, 0, 0), 90).rotate((0, 0, 0), (0, 0, 1), 180)
    zr = m.part("MGN12_Rail_Z500", zrs, "steel", "purchased")
    zbs = bs.rotate((0, 0, 0), (1, 0, 0), 90).rotate((0, 0, 0), (0, 0, 1), 180)
    zb = m.part("MGN12H_Z", zbs, "steel", "purchased")
    zstrip_h = [hy(0, -1, zz, 2.5, 6) for zz in range(-240, 241, 25)]
    strip_fix_z = (-227.5, -127.5, -27.5, 72.5, 172.5)
    zstrip_h += [hy(0, -1, zz, 5.5, 6) for zz in strip_fix_z]
    zstrip_s = drill(box(0, 2, -250, 20, 4, 500), zstrip_h)
    for zz in strip_fix_z:
        zstrip_s = zstrip_s.cut(cq.Solid.makeCone(2.75, 5.2, 2.45, cq.Vector(0, 1.55, zz), cq.Vector(0, 1, 0)))
    zstrip = m.part("Z_Rail_Datum_20x4x500", zstrip_s, holes=zstrip_h,
                   note="Five flush M5 countersunk screws to slot nuts; M3 tapped holes at rail pitch")
    for off in (-45, 45):
        m.add(f"z_strip_{off}", zstrip, (x+off, -253, 335), "x")
        m.add(f"z_rail_{off}", zr, (x+off, -249, 335), "x")
        for zz in d.z_block_offsets:
            m.add(f"z_block_{off}_{zz}", zb, (x+off, -249, D+zz), "z")
    # With H=13 the carriage rear plane is Y=-236 (not the old -150).
    zholes = [hy(a+aa, -1, zz+bb, 3.5, 10) for a in (-45, 45)
              for zz in d.z_block_offsets for aa in (-10, 10) for bb in (-10, 10)]
    zholes += [hy(a+aa, 4.8, zz+bb, 6.2, 4.2) for a in (-45, 45)
               for zz in d.z_block_offsets for aa in (-10, 10) for bb in (-10, 10)]
    zholes += [hy(a+aa, -1, -16.5, 5.5, 10) for a in (-44, 44) for aa in (-5, 5)]
    zholes += [hy(aa, -1, zz, 5.5, 10) for aa in (-13, 13) for zz in (-66, -46)]
    zplate = m.part("Z_Carriage_130x100x8", drill(box(0, 4, -104, 130, 8, 100), zholes), holes=zholes)
    m.add("z_carriage", zplate, (x, -236, D), "z")

    # TR8x2 screw, bronze working nut + independently captive secondary nut.
    screw_s = fuse(cyl(0, 0, 110, 4, 478), cyl(0, 0, 90, 3, 20), cyl(0, 0, 588, 3, 50))
    screw_s = screw_s.cut(cyl(-4, 0, 612.5, 1.25, 8, (1, 0, 0)))
    screw = m.part("TR8x2_Screw_Machined_Ends", screw_s, "steel", "purchased",
                  note="TR8x2, 6 mm journals, 2.5 H7 matched cross-hole at Z612.5; shaft yield >=500 MPa; supplier drawing mandatory")
    m.add("z_screw", screw, (x, -268, 0), "x")
    nut_pattern = ((-8, 0), (8, 0), (0, -8), (0, 8))
    nut_h = [hz(a, b, -1, 3.5, 5) for a, b in nut_pattern]
    nut_s = fuse(cyl(0, 0, 0, 11, 4), cyl(0, 0, 4, 5.1, 11)).cut(cyl(0, 0, -1, 4.15, 17))
    nut = m.part("TR8x2_Bronze_Nut", drill(nut_s, nut_h), "purchased", "purchased", nut_h,
                 "Thread fit is a purchased interface, not evaluated by smooth cylinders")
    for name, off in (("z_working_nut", -60), ("z_safety_nut", -84)):
        m.add(name, nut, (x, -268, D+off), "z")
    bridge_h = [hz(a, b, -1, 2.5, 10) for a, b in nut_pattern]
    bridge_h += [hz(0, 0, -1, 11, 10)]
    bridge_s = fuse(box(0, 10, 0, 40, 44, 8), box(0, 28, 0, 40, 8, 28))
    bridge_h += [hy(a, 21, zz, 4.2, 16) for a in (-13, 13) for zz in (4, 24)]
    bridge_h += [hz(a, b, -1, 2.5, 10) for a in (-16, 16) for b in (-9, 9)]
    bridge = m.part("Z_Nut_Bridge", drill(bridge_s, bridge_h), "steel", holes=bridge_h)
    m.add("z_nut_bridge", bridge, (x, -268, D-70), "z")
    # Primary flange seats on bridge top at D-62; set flange bottom accordingly.
    next(i for i in m.items if i.name == "z_working_nut").origin = (x, -268, D-62)
    cage_s = box(0, 0, 0, 40, 32, 19.8).cut(box(0, 0, 5, 25, 25, 17))
    cage_h = [hz(0, 0, -1, 11, 23)] + [hz(a, b, -1, 3.5, 23) for a in (-16, 16) for b in (-9, 9)]
    cage_h += [hz(a, 0, -1, 2.5, 7) for a in (-8, 8)]
    cage = m.part("Z_Secondary_Nut_Cage", drill(cage_s, cage_h), "steel", holes=cage_h,
                  note="0.8 mm axial catch clearance; steel/Al, never PETG")
    m.add("z_safety_cage", cage, (x, -268, D-89.8), "z")
    key_stud = m.part("Safety_Nut_AntiRotation_Stud", fuse(cyl(0, 0, -3, 1.2, 3),
                     cyl(0, 0, 0, 1.5, 10), cyl(0, 0, 10, 2.5, 2)), "steel", "purchased",
                     note="M3 shoulder stud, retains rotation but allows secondary nut to float axially")
    for xx in (-8, 8):
        m.add(f"safety_nut_key_{xx}", key_stud, (x+xx, -268, D-84.8), "z")
    # Bearing housing and integrated normally-engaged brake motor envelopes.
    housing_h = [hz(0, 0, -1, 19.02, 8), hz(0, 0, 6, 24.1, 21)]
    housing_h += [hz(a, 0, -1, 4.5, 28) for a in (-23, 23)]
    housing = m.part("Z_Fixed_Bearing_Housing", drill(box(0, 0, 0, 60, 40, 26), housing_h), holes=housing_h,
                     note="Radial seat 19 H7, stepped thrust abutment; paired F6-12M; preload and collar rating pending")
    m.add("z_fixed_bearing_housing", housing, (x, -268, 595), "x")
    cap_h = [hz(0, 0, -1, 6.5, 6)] + [hz(a, 0, -1, 4.5, 6) for a in (-23, 23)]
    cap = m.part("Z_Thrust_End_Cap", drill(box(0, 0, 0, 60, 40, 4), cap_h), "steel", holes=cap_h)
    m.add("z_thrust_end_cap", cap, (x, -268, 621), "x")
    hanger_h = [hz(0, 0, -1, 25, 28)] + [hz(a, 0, -1, 4.5, 28) for a in (-23, 23)]
    hanger = m.part("Z_Bearing_Hanger", drill(box(0, 0, 0, 60, 40, 26), hanger_h), holes=hanger_h)
    m.add("z_bearing_hanger", hanger, (x, -268, 625), "x")
    ring = m.part("626ZZ_6x19x6", cyl(0, 0, 0, 9.5, 6).cut(cyl(0, 0, -1, 3.02, 8)), "steel", "purchased")
    m.add("z_fixed_radial_bearing", ring, (x, -268, 595), "x")
    abut = m.part("Z_Thrust_Abutment_Washer", cyl(0, 0, 0, 12, 3).cut(cyl(0, 0, -1, 3.25, 5)), "steel")
    m.add("z_thrust_abutment", abut, (x, -268, 601), "x")
    thrust = m.part("F6_12M_6x12x4p5", cyl(0, 0, 0, 6, 4.5).cut(cyl(0, 0, -1, 3.05, 7)), "steel", "purchased")
    for zz in (604, 616.5):
        m.add(f"z_thrust_bearing_{zz}", thrust, (x, -268, zz), "x")
    collar_s = cyl(0, 0, 0, 8, 8).cut(cyl(0, 0, -1, 3.0, 10))
    collar_s = collar_s.cut(cyl(-9, 0, 4, 1.25, 18, (1, 0, 0)))
    collar = m.part("Shaft_Collar_6x16x8", collar_s, "steel", "purchased",
                    note="Positive axial retention by matched 2.5 mm cross-pin, NOT set-screw friction alone; verify catch load >=1200 N")
    m.add("z_shaft_collar", collar, (x, -268, 608.5), "x")
    cross_pin = m.part("Z_Thrust_Cross_Pin_D2p5x16", cyl(0, 0, 0, 1.25, 16, (1, 0, 0)), "steel", "purchased",
                       note="Hardened retained dowel, minimum verified double-shear capacity 2500 N; match-ream shaft/collar")
    m.add("z_thrust_cross_pin", cross_pin, (x-8, -268, 612.5), "x")
    float_pattern = [(xx, yy) for xx in (-12, 12) for yy in (-10, 10)]
    float_h = [hz(0, 0, -1, 6.5, 10), hz(0, 0, 2, 19.02, 7)]
    float_h += [hz(xx, yy, -1, 4.5, 10) for xx, yy in float_pattern]
    fl = m.part("Z_Floating_Bearing_Housing", drill(box(0, 0, 0, 32, 30, 8), float_h), holes=float_h)
    m.add("z_floating_bearing", fl, (x, -268, 95), "x")
    fc_h = [hz(0, 0, -1, 6.5, 4)] + [hz(xx, yy, -1, 4.5, 4) for xx, yy in float_pattern]
    fc = m.part("Z_Floating_Bearing_Cap", drill(box(0, 0, 0, 32, 30, 2), fc_h), "steel", holes=fc_h)
    m.add("z_floating_bearing_cap", fc, (x, -268, 103), "x")
    m.add("z_floating_radial_bearing", ring, (x, -268, 97), "x")
    fp_h = [hz(0, 0, -1, 8.2, 46)] + [hz(xx, yy, 36, 3.3, 10) for xx, yy in float_pattern]
    fp = m.part("Z_Floating_Bearing_Pedestal", drill(box(0, 0, 0, 32, 30, 44), fp_h), holes=fp_h)
    m.add("z_floating_pedestal", fp, (x, -268, 51), "x")
    brake_motor = m.part("NEMA17_NC_Brake_Envelope", fuse(box(0, 0, 0, 42, 42, 65),
                         cyl(0, 0, -20, 2.5, 20)), "safety", "purchased",
                         note="24 V fail-safe brake >=0.3 N m; full vendor selection pending")
    m.add("z_brake_motor", brake_motor, (x, -268, 659), "x")
    coupling_s = cyl(0, 0, 0, 9.5, 25).cut(cyl(0, 0, -1, 3.05, 13.5))
    coupling_s = coupling_s.cut(cyl(0, 0, 12.5, 2.55, 13.5))
    coupling = m.part("Coupler_5x6_Envelope", coupling_s, "purchased", "purchased")
    m.add("z_coupling", coupling, (x, -268, 630), "x")

    # Two METAL rectangular-tube cantilevers, tops UNDER the tray datum.
    tube_h = [hz(0, yy, -1, 4.5, 27) for yy in (d.tray_y-43, d.tray_y+47, -110, -50)]
    tube_h += [hx(-14, -208, 12.5, 5.5, 28)]
    tube_s = box(0, -114.5, 0, 25, 227, 25).cut(box(0, -114.5, 2, 21, 229, 21))
    tube = m.part("Tray_Al_Tube_25x25x2_L227", drill(tube_s, tube_h), holes=tube_h,
                  note="M4 compression sleeves through tube; no polymer in primary bending path")
    plug_h = [hy(xx, -1, 0, 4.2, 22) for xx in (-5, 5)]
    plug_h += [hx(-12, 20, 0, 4.2, 24)]
    plug = m.part("Tube_End_Plug", drill(box(0, 15, -10.4, 20.8, 30, 20.8), plug_h), holes=plug_h,
                  note="2x M5 tapped end; transverse M5 retention bolt; 0.2 mm insertion clearance")
    for off in (-44, 44):
        m.add(f"tray_tube_{off}", tube, (x+off, 0, D-29), "z")
        m.add(f"tray_tube_plug_{off}", plug, (x+off, -228, D-16.5), "z")
    tray_h = [hz(xx, yy, -1, 4.5, 6) for xx in (-44, 44)
              for yy in (-43, 47, -110-d.tray_y, -50-d.tray_y)]
    tray_s = drill(deck_s, tray_h).cut(box(0, -3.5, -1, 40, 125, 6))
    tray = m.part("Carrier_Tray_124x130", tray_s, "PETG", "print", tray_h,
                  "40 mm front-open mast slot, 6 mm rear bridge; supports box on two side wings")
    m.add("carrier_tray", tray, (x, d.tray_y, D-4), "z")
    spine_h = [hz(-13, yy, -1, 2.5, 8) for yy in range(-215, -34, 20)]
    spine_h += [hz(xx, yy, -1, 4.5, 8) for xx in (-35, 35) for yy in (-110, -50)]
    spine_h += [hz(13+xx, -35+yy, -1, 3.5, 8) for xx in (-15.5, 15.5) for yy in (-15.5, 15.5)]
    spine_h += [hz(13, -35, -1, 23, 8)]
    spine_h += [hz(xx, -202, -1, 2.5, 8) for xx in (8, 18)]
    spine_s = drill(box(0, -119.5, 0, 82, 211, 6), spine_h)
    for xx, length, dia in ((7, 6.5, 3.5), (13, 8.5, 5.5), (19, 6.5, 3.5)):
        spine_s = spine_s.cut(slot_y(xx, -217, -1, length, dia, 8))
    spine = m.part("Y_Spine_82x211x6", spine_s, holes=spine_h,
                   note="Rear idler: central 8.5x5.5 Y slot, two 6.5x3.5 Y slots; +/-1.5 mm tension travel")
    m.add("y_spine", spine, (x, 0, D-46), "z")
    mount_h = [hz(xx, 0, -1, 3.3, 13) for xx in (-10, -1)]
    mount = m.part("Y_Spine_Metal_Spacer", drill(box(0, 0, 0, 26, 20, 11), mount_h), holes=mount_h)
    mount_left = m.part("Y_Spine_Metal_Spacer_Left", mount.shape.rotate((0, 0, 0), (0, 0, 1), 180),
                        holes=[hz(-xx, 0, -1, 3.3, 13) for xx in (-10, -1)])
    for side in (-1, 1):
        for yy in (-110, -50):
            m.add(f"y_spine_spacer_{side}_{yy}", mount if side == 1 else mount_left,
                  (x+side*45, yy, D-40), "z")
    yrs, _ = rail_shape(9, 6.5, 200, 20)
    yr = m.part("MGN9_Rail_Y200", yrs, "steel", "purchased")
    m.add("y_rail", yr, (x-13, -125, D-40), "z")
    ybs, _ = block_shape(20, 39.9, 2, 10, 9, 6.5, (15, 16))
    yb = m.part("MGN9H_Y", ybs, "steel", "purchased")
    pin_y = d.tray_y+d.eye_offset_y
    bc = pin_y-d.y_block_to_pin
    m.add("y_block", yb, (x-13, bc, D-40), "y")
    yplate_h = [hz(-13+xx, yy, -1, 3.5, 6) for xx in (-7.5, 7.5) for yy in (-8, 8)]
    yplate_h += [hz(15, yy, -1, 3.5, 6) for yy in (-4.5, 1.5)]
    yplate_h += [hz(xx, 25, -1, 3.5, 6) for xx in (-10, 10)]
    yp = m.part("Y_Puller_Plate_46x60x4", drill(box(0, 10, 0, 46, 60, 4), yplate_h), holes=yplate_h)
    m.add("y_puller_plate", yp, (x, bc, D-30), "y")
    ybelt = m.part("Y_GT2_Belt_Loop", belt_shape(182), "rubber", "purchased")
    m.add("y_belt", ybelt, (x+13, -217, D-40), "z")
    for name, yy in (("y_drive_pulley", -35), ("y_idler_pulley", -217)):
        m.add(name, pul, (x+13, yy, D-40), "z")
    yi = m.part("Y_Idler_Shoulder_Axle_M5", fuse(cyl(0, 0, 0, 5, 2), cyl(0, 0, 2, 2.0, 6),
                cyl(0, 0, 8, 2.5, 15.5)), "steel", "purchased",
                note="M5 thread into carrier, 5 mm bearing shoulder; retaining groove at top, not a plain loose bolt")
    m.add("y_idler_axle", yi, (x+13, -217, D-54), "z")
    yic_h = [hz(0, 0, -1, 4.2, 8)] + [hz(xx, 0, -1, 2.5, 8) for xx in (-6, 6)]
    yic = m.part("Y_Idler_Tension_Carrier", drill(box(0, 0, 0, 18, 12, 6), yic_h), holes=yic_h,
                 note="Two M3 screws clamp through spine slots; M3 pusher contacts front face")
    m.add("y_idler_tension_carrier", yic, (x+13, -217, D-52), "z")
    ya_h = [hy(0, -5, 5, 2.5, 10)] + [hz(xx, 0, -1, 3.5, 12) for xx in (-5, 5)]
    ya = m.part("Y_Tension_Adjuster", drill(box(0, 0, 0, 16, 8, 10), ya_h), holes=ya_h,
                note="M3x16 pusher + jam nut, +/-1.5 mm; two M3 screws into spine")
    m.add("y_tension_adjuster", ya, (x+13, -202, D-56), "z")
    m.add("y_motor", motor, (x+13, -35, D-53), "z")
    ym_h = [hz(a, b, -1, 3.5, 9) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    ym_h += [hz(0, 0, -1, 23, 9)]
    ym = m.part("Y_Motor_Spacer_7", drill(box(0, 0, 0, 42, 42, 7), ym_h), holes=ym_h)
    m.add("y_motor_spacer", ym, (x+13, -35, D-53), "z")
    yc_h = [hz(-5, yy, -1, 3.3, 10) for yy in (-3, 3)]
    yc_s = box(0, 0, 0, 18, 14, 8).cut(box(0, 0, -1, 2.0, 16, 6))
    # One connected counterbore slot; two tangent circles created a non-manifold STL.
    yc_s = yc_s.cut(slot_y(-5, 0, -1, 12, 6, 2.2))
    yc = m.part("Y_Belt_Clamp", drill(yc_s, yc_h), "PETG", "print", yc_h,
                "12x6 counterbore SLOT 1.2 deep, not two tangent holes; print web down")
    m.add("y_belt_clamp", yc, (x+20, bc-1.5, D-38), "y")
    nut_m3 = cq.Workplane("XY").polygon(6, 5.5*2/math.sqrt(3)).extrude(2.4).val()
    nut_m3 = nut_m3.cut(cyl(0, 0, -1, 1.5, 5))
    locknut = m.part("M3_Clamp_Nut", nut_m3, "steel", "purchased",
                     note="M3x16 DIN7984 low head; head counterbore 1.2 mm; thread locking required")
    for yy in (-3, 3):
        m.add(f"y_clamp_nut_{yy}", locknut, (x+15, bc-1.5+yy, D-26), "y")
    m.allow("y_belt_clamp", "y_belt", "Belt compresses into adjustable clamping pocket")

    # Guided steel drop pin, a printed scotch-yoke actuator, METAL mast.
    mast_h = [hy(xx, -4, zz, 3.5, 8) for xx in (-8, 8) for zz in (21, 57)]
    mast_h += [hz(xx, -5, -27, 2.5, 6) for xx in (-10, 10)]
    mast_h += [hy(13, -7, zz, 2.5, 10) for zz in (30, 46)]
    mast_s = fuse(box(0, 0, -26, 36, 4, 92), box(0, 0, -26, 36, 16, 4))
    mast = m.part("Latch_Mast_36x92_L", drill(mast_s, mast_h), holes=mast_h)
    m.add("latch_mast", mast, (x, pin_y-20, D), "y")
    fork_h = [hz(0, 0, -1, 6.1, 6)] + [hy(a, -19, 2, 2.5, 12) for a in (-8, 8)]
    # Two separated guide cheeks; no 10 mm tongue forced through an 8 mm opening.
    fork_s = box(0, -6, 0, 26, 24, 4)
    fork = m.part("Pin_Guide_Cheek", drill(fork_s, fork_h), "PETG", "print", fork_h,
                  "Ream to steel bushing fit; metal bushings required for wear")
    m.add("pin_lower_guide", fork, (x, pin_y, D+19), "y")
    m.add("pin_upper_guide", fork, (x, pin_y, D+55), "y")
    bush_s = fuse(cyl(0, 0, 0, 3, 4), cyl(0, 0, 4, 3.75, .5)).cut(cyl(0, 0, -1, 2.05, 7))
    bush = m.part("Pin_Flanged_Bushing_4p1x6", bush_s, "purchased", "purchased",
                  note="Replaceable bronze bushing; 6.1 pilot must be fitted/retained, not assumed press fit")
    for zz in (19, 55):
        m.add(f"pin_bushing_{zz}", bush, (x, pin_y, D+zz), "y")
    pin_s = fuse(cq.Solid.makeCone(1, 2, 2), cyl(0, 0, 2, 2, 58))
    pin = m.part("Latch_Pin_D4x60", pin_s, "steel", "purchased",
                  note="Ground steel pin, not printed; released lift 14 mm")
    m.add("latch_pin", pin, (x, pin_y, D+6), "pin")
    servo = m.part("MG90S_Envelope", box(0, 0, 0, 23, 12, 29), "purchased", "purchased",
                   note="Supplier output-shaft datum and >=150 degree usable travel must be verified")
    m.add("latch_servo", servo, (x+31, pin_y-15, D+19), "y")
    servo_holder_h = [hy(13, -27, zz, 3.5, 7) for zz in (30, 46)]
    servo_holder_h += [hz(45.25, yy, 37, 2.05, 13) for yy in (-20, -10)]
    holder_s = fuse(box(28, -24, 15, 40, 4, 37), box(33, -15, 15, 30, 18, 4),
                    box(45.25, -15, 18, 5.5, 18, 30))
    holder = m.part("Servo_Cradle", drill(holder_s, servo_holder_h), "PETG", "print", servo_holder_h,
                    "2x M3x8 to tapped metal mast; separate clamping lid; vendor servo datum still required")
    m.add("servo_cradle", holder, (x, pin_y, D), "y")
    lid_h = [hz(45.25, yy, -1, 2.8, 5) for yy in (-20, -10)]
    lid = m.part("Servo_Cradle_Lid", drill(box(33.75, -14, 0, 28.5, 16, 3), lid_h), "PETG", "print", lid_h)
    m.add("servo_cradle_lid", lid, (x, pin_y, D+48), "y")
    # Slotted yoke: steel roller travels in Y while the pin slider only moves vertically.
    yoke_s = box(0, -6, 0, 12, 22, 5).cut(box(0, -6, .8, 14, 17, 3.4))
    yoke_s = yoke_s.cut(cyl(0, 0, -1, 2.0, 7))
    yoke = m.part("Latch_Scotch_Yoke", yoke_s, "PETG", "print",
                  note="7 mm crank radius; end-to-end vertical stroke 14 mm; bench-test before use")
    m.add("latch_yoke", yoke, (x, pin_y, D+29), "pin")
    pin_collar = m.part("Pin_Collar_4x10x5", cyl(0, 0, 0, 5, 5).cut(cyl(0, 0, -1, 2, 7)),
                        "steel", "purchased", note="Two miniature shaft collars retain the yoke on the ground pin")
    for zz in (24, 34):
        m.add(f"pin_collar_{zz}", pin_collar, (x, pin_y, D+zz), "pin")
    return_spring = m.part("Latch_Return_Spring_Envelope", cyl(0, 0, 0, 3.5, 16).cut(cyl(0, 0, -1, 3.2, 18)),
                          "steel", "purchased",
                          note="Metal return spring, OD7 wire0.3 freeL19, solid<=1.8; target force 0.2..1.2N. Coil envelope only, supplier test mandatory")
    m.add("latch_return_spring", return_spring, (x, pin_y, D+39), "spring")
    crank_s = fuse(cyl(0, 0, 0, 3, 3, (1, 0, 0)), cyl(0, 0, -7, 2.5, 3, (1, 0, 0)),
                   box(1.5, 0, -7, 3, 5, 7))
    crank_h = [hx(-1, 0, 0, 2.2, 5), hx(-1, 0, -7, 3.2, 5)]
    crank = m.part("Latch_Crank_R7", drill(crank_s, crank_h), "PETG", "print", crank_h,
                   "Use supplier metal spline adapter; servo endpoint calibration required")
    m.add("latch_crank", crank, (x+15, pin_y-12, D+38.5), "crank")
    horn = m.part("Servo_Horn_Interface_Envelope", cyl(0, 0, 0, 3.25, 1.5, (1, 0, 0)).cut(
                  cyl(-1, 0, 0, 1.1, 4, (1, 0, 0))), "purchased", "purchased",
                  note="Metal spline horn/interface envelope; MUST match selected MG90S output drawing")
    m.add("servo_horn_interface", horn, (x+18, pin_y-12, D+38.5), "y")
    roller = m.part("Latch_Roller_D3", cyl(0, 0, 0, 1.5, 26, (1, 0, 0)), "steel", "purchased",
                    note="3 mm ground pin with retaining grooves; two DIN6799 E-clips")
    m.add("latch_roller", roller, (x-8, pin_y-12, D+31.5), "roller")
    clip = m.part("Roller_Clip_Envelope", cyl(0, 0, 0, 2.5, .5, (1, 0, 0)).cut(
                  cyl(-1, 0, 0, 1.6, 3, (1, 0, 0))), "steel", "purchased")
    for xx in (-8.5, 18):
        m.add(f"roller_clip_{xx}", clip, (x+xx, pin_y-12, D+31.5), "roller")
    m.add("carried_bin", bin_p, (x, d.tray_y, D), "bin")

    # Mechanical end stops (not software limits), all outside normal trajectories.
    xstop = m.part("X_Stop_24x20x20", box(0, 0, 0, 24, 20, 20), "rubber", "purchased")
    for xx in (-25, 625):
        for yy in (-285, -215):
            m.add(f"x_stop_{xx}_{yy}", xstop, (xx, yy, 43))
    zstop = m.part("Z_Stop_24x15x10", box(0, 0, 0, 24, 15, 10), "rubber", "purchased")
    for xx in (-45, 45):
        for zz in (80, 584):
            m.add(f"z_stop_{xx}_{zz}", zstop, (x+xx, -230, zz), "x")
    ys_s = box(0, 0, 0, 24, 4, 10).cut(box(0, 0, -1, 9.4, 6, 8))
    ystop = m.part("Y_Stop_24x4x10", ys_s, "rubber", "purchased")
    for yy in (-222, -27):
        m.add(f"y_stop_{yy}", ystop, (x-13, yy, D-40), "z")
    # Transparent interlocked enclosure; shown as panels, hardware is in the safety BOM.
    front = m.part("Guard_Front_PC3", box(300, -351.5, 0, 780, 3, 766), "guard", "cut_panel",
                   note="Hinged/interlocked access, contained machine only; impact rating pending")
    m.add("front_interlocked_guard", front)
    for xx in (-91.5, 691.5):
        gp = m.part(f"Guard_Side_{xx}", box(xx, -80, 0, 3, 540, 766), "guard", "cut_panel",
                    note="10 mm panel standoffs to guard frame; no open skirt below base")
        m.add(f"side_guard_{xx}", gp)
    back = m.part("Guard_Rear_PC3", box(300, 191.5, 0, 780, 3, 766), "guard", "cut_panel")
    m.add("rear_guard", back)
    roof = m.part("Guard_Top_PC3", box(300, -80, 766, 786, 546, 3), "guard", "cut_panel")
    m.add("top_guard", roof)
    return m


def bbox(s):
    b = s.BoundingBox()
    return (b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax)


def overlaps(a, b, tol=1e-5):
    return all(min(a[k+3], b[k+3])-max(a[k], b[k]) > tol for k in range(3))


def collisions(items, allowed, *, dx=0, dz=0, q=0, pin_lift=0, volume_tol=.02):
    shapes = [(i, i.located(dx, dz, q, pin_lift)) for i in items]
    bounds = [bbox(s) for _, s in shapes]
    found, accepted = [], []
    for ai, (a, sa) in enumerate(shapes):
        for bi in range(ai+1, len(shapes)):
            b, sb = shapes[bi]
            if not overlaps(bounds[ai], bounds[bi]):
                continue
            v = sa.intersect(sb).Volume()
            if v <= volume_tol:
                continue
            key = tuple(sorted((a.name, b.name)))
            row = {"a": a.name, "b": b.name, "volume_mm3": round(v, 5)}
            if key in allowed:
                row["reason"] = allowed[key]
                accepted.append(row)
            else:
                found.append(row)
    return found, accepted


def dimension_checks(d):
    checks = []
    def add(name, actual, minimum):
        checks.append({"name": name, "actual_mm": round(actual, 4), "minimum_mm": minimum,
                       "pass": actual >= minimum})
    add("x_block_separation", d.x_block_offsets[1]-d.x_block_offsets[0]-45.4, 5)
    add("z_block_separation", d.z_block_offsets[1]-d.z_block_offsets[0]-45.4, 4)
    add("lowest_z_block_end_margin", d.first_deck+d.z_block_offsets[0]-22.7-d.z_rail_min, 10)
    add("highest_z_block_end_margin", d.z_rail_max-(d.decks[-1]+d.z_block_offsets[-1]+22.7), 10)
    pin0 = d.tray_y+d.eye_offset_y
    add("y_retracted_rail_margin", pin0-d.y_block_to_pin-d.y_block_length/2-d.y_rail_min, 8)
    add("y_extended_rail_margin", d.y_rail_max-(pin0-d.y_block_to_pin+d.transfer+d.y_block_length/2), 8)
    add("lowest_plate_to_x_plate", d.first_deck-104-51, 20)
    add("tray_tube_top_below_bin", 4, 3)
    add("transfer_gap", -(d.tray_y+65), 1)
    add("stored_eye_to_retracted_tray", (d.storage_y-76)-(d.tray_y+65), 2)
    add("pin_radial_clearance", (6.2-4)/2, .8)
    add("released_pin_to_eye_top", 6+14-16, 3)
    return checks


def export_model(m, out):
    out.mkdir(parents=True, exist_ok=True)
    (out/"parts").mkdir(exist_ok=True)
    (out/"stl").mkdir(exist_ok=True)
    assy = cq.Assembly(name="ASRS_Modular_V02")
    for i in m.items:
        assy.add(i.part.shape, name=i.name, loc=cq.Location(cq.Vector(*i.origin)),
                 color=cq.Color(*COLORS.get(i.part.material, COLORS["aluminum"])))
    assy.save(str(out/"ASRS_Modular_V02.step"))
    part_rows, hole_rows = [], []
    for p in m.parts.values():
        cq.exporters.export(p.shape, str(out/"parts"/(p.name+".step")))
        b = bbox(p.shape)
        if p.process == "print":
            cq.exporters.export(p.shape, str(out/"stl"/(p.name+".stl")), tolerance=.03, angularTolerance=.10)
        part_rows.append({"name": p.name, "quantity": sum(i.part.name == p.name for i in m.items),
                          "material": p.material, "process": p.process,
                          "extents_mm": [round(b[k+3]-b[k], 4) for k in range(3)],
                          "volume_mm3": round(p.shape.Volume(), 4), "note": p.note,
                          "geometry_valid": p.shape.isValid(), "solids": len(p.shape.Solids())})
        for n, (pos, axis, dia, depth) in enumerate(p.holes, 1):
            hole_rows.append([p.name, n, *pos, *axis, dia, depth])
    with (out/"holes.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["part", "hole", "x", "y", "z", "dx", "dy", "dz", "diameter_mm", "cut_length_mm"])
        w.writerows(hole_rows)
    with (out/"BOM.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["part", "quantity", "material", "process", "note"])
        for p in part_rows:
            w.writerow([p[k] for k in ("name", "quantity", "material", "process", "note")])
    with (out/"Cell_Coordinates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["column", "row", "x_mm", "deck_top_z_mm", "bin_center_y_mm"])
        for c, xx in enumerate(m.d.x_positions, 1):
            for r, z in enumerate(m.d.decks, 1):
                w.writerow([c, r, xx, z, m.d.storage_y])
    manifest = {"units": "mm", "parts": part_rows,
                "generator_sha256": source_sha256(),
                "frozen_design_parameters": asdict(m.d),
                "instances": [{"name": i.name, "part": i.part.name, "origin_mm": i.origin,
                               "motion_group": i.group} for i in m.items],
                "native_parametric_features": False,
                "note": "Code-parametric B-rep parts; native SW conversion does not create sketch feature history."}
    (out/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EXPORTED parts={len(part_rows)} instances={len(m.items)} path={out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args()
    m = build_model()
    if not args.no_export:
        export_model(m, args.out)
    if args.validate:
        bad, accepted = collisions(m.items, m.allowed)
        checks = dimension_checks(m.d)
        report = {"generator_sha256": source_sha256(), "dimensional_checks": checks, "unexpected_static_collisions": bad,
                  "explicit_contact_exceptions": accepted, "review_required": True,
                  "hardware_accepted": False, "native_motion_mates_verified": False}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out/"validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"dimensional_pass": all(c["pass"] for c in checks), "collisions": bad}, indent=2), flush=True)
        return int(bool(bad) or not all(c["pass"] for c in checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
