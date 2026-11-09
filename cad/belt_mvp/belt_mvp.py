"""E02 structural optimization: fixed X motor, Z-mounted Y motor, XY GT2.

Derives immutable, readback-tested E01 part geometry; never rewrites E01 files.
1kg is payload design input, not a safe-working-load or permission to power.
"""
from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import cadquery as cq
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'cad/powered_mvp'))
import powered_mvp as e01

v2 = e01.v2
box, cyl, fuse, drill, hz, hy, hx = e01.box, e01.cyl, e01.fuse, e01.drill, e01.hz, e01.hy, e01.hx
BASE = e01.OUT
OUT = ROOT/'model/Belt_1Cell_MVP_E02'
DEPENDENCIES = [Path(__file__), *e01.DEPENDENCIES, BASE/'manifest.json',
                *sorted((BASE/'parts').glob('*.step'))]
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
PITCH, TEETH, BELT_WIDTH = 2., 20, 6.
ADVANCE = PITCH*TEETH
RADIUS = ADVANCE/(2*math.pi)
INNER, OUTER = RADIUS-.75, RADIUS+.65
X_LEFT, X_RIGHT, X_Y, X_Z = -240., 240., -308., 60.
Y_REAR, Y_FRONT, Y_AXIS_X = -220., -40., 85.
CELL_X, CELL_Z, IO_X, IO_Z = e01.CELL_X, e01.CELL_Z, e01.IO_X, e01.IO_Z


@dataclass(frozen=True)
class Design(e01.Design):
    y_guide_spacing: float = 52.


class Item(e01.Item):
    def located(self, dx=0, dz=0, q=0, pin_lift=0, bin_q=None, io_open=0):
        shape = super().located(dx, dz, q, pin_lift, bin_q, io_open)
        if self.name in ('x_drive_pulley', 'x_idler_pulley', 'y_drive_pulley', 'y_idler_pulley'):
            xx, yy, zz = self.origin
            if self.group != 'fixed': xx += dx
            phi = -360*dx/ADVANCE if self.name.startswith('x_') else 360*q/ADVANCE
            shape = shape.rotate((xx, yy, 0), (xx, yy, 1), phi)
        return shape


def part_at(m, name):
    return next(i for i in m.items if i.name == name)


def joint(m, a, b, purpose):
    m.joints.append({'a': a, 'b': b, 'purpose': purpose, 'strength_verified': False})


def load_baseline():
    manifest = json.loads((BASE/'manifest.json').read_text())
    audit = json.loads((BASE/'delivery_audit.json').read_text())
    if not audit['design_geometry_package_pass'] or manifest['fingerprint'] != e01.FINGERPRINT:
        raise RuntimeError('E01 geometry baseline missing, stale or failed')
    m = v2.Model(); m.x, m.deck, m.d = CELL_X, CELL_Z, Design()
    for r in manifest['parts']:
        shape = cq.importers.importStep(str(BASE/'parts'/(r['code']+'.step'))).val()
        m.parts[r['name']] = v2.Part(r['name'], shape, r['material'], r['process'], r['holes'], r['note'])
    for i in manifest['instances']:
        m.add(i['name'], m.parts[i['part']], tuple(i['origin_mm']), i['group'])
    m.joints = list(manifest['joints'])
    return m


def belt_loop(distance):
    """Smooth effective rubber envelope, NOT a manufacturable GT2 tooth form."""
    h = BELT_WIDTH
    a = box(-(INNER+OUTER)/2, distance/2, 1.5, OUTER-INNER, distance, h)
    b = box((INNER+OUTER)/2, distance/2, 1.5, OUTER-INNER, distance, h)
    ring = cyl(0, 0, 1.5, OUTER, h).cut(cyl(0, 0, 1, INNER, h+1))
    lower = ring.intersect(box(0, -OUTER, 1, 2*OUTER+2, 2*OUTER, h+1))
    upper = ring.intersect(box(0, OUTER, 1, 2*OUTER+2, 2*OUTER, h+1)).translate((0, distance, 0))
    return fuse(a, b, lower, upper)


def pulley(m, idler=False):
    s = fuse(cyl(0, 0, 0, 9, 1.5), cyl(0, 0, 1.5, INNER-.1, 6), cyl(0, 0, 7.5, 9, 1.5))
    if not idler: s = s.fuse(cyl(0, 0, 9, 8, 6))
    s = s.cut(cyl(0, 0, -1, 5 if idler else 2.55, 18))
    return m.part('E02_GT2_20T_'+('TwinBearing_Idler' if idler else 'Metal_Drive_D5'), s, 'purchased', 'candidate',
        note='Purchase metal GT2/2mm/20T, belt6; flange OD<=18. Smooth effective tooth envelope ONLY, not printable/machinable tooth data. '+
             ('Twin MR105ZZ 5x10x4 allocation; verify actual assembled idler bearing/shoulder/retention drawing.' if idler else 'Bore5, positive clamp or dual screw retention. Actual hub/clamp/rating/axial shaft engagement must be vendor-verified.'))


def bolt(m, size, length, axis=None, head=3):
    p = e01.bolt(m, size, length, head)
    if not axis: return p
    rotations = {'+X': ((0, 1, 0), -90), '-X': ((0, 1, 0), 90),
                 '+Y': ((1, 0, 0), 90), '-Y': ((1, 0, 0), -90), '+Z': ((1, 0, 0), 180)}
    line, angle = rotations[axis]
    return m.part(p.name+'_shaft'+axis, p.shape.rotate((0, 0, 0), line, angle), 'steel', 'purchased', note=p.note)


def cut_world(m, name, holes):
    e01.prior.cut_world(m, name, holes)


def build_model():
    m = load_baseline(); x, D = m.x, m.deck
    def obsolete(i):
        return (i.name.startswith(('x_rack_', 'y_rack_', 'x_motor_', 'y_motor_', 'x_hub_', 'y_hub_',
                                  'y_spine_spacer_', 'y_block_bolt_', 'y_stop_', 'guard_'))
                or i.name in ('x_pinion', 'y_pinion', 'x_pinion_hub', 'y_pinion_hub'))
    m.items = [i for i in m.items if not obsolete(i)]
    names = {i.name for i in m.items}
    m.joints = [j for j in m.joints if j['a'] in names and j['b'] in names]

    # Remove rear motor overhang and all abandoned motor holes from the X plate.
    hh = [hz(off+a, yy+b, -1, 3.5, 10) for off in (-45, 45) for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    hh += [hz(off+a, yy+b, 4.8, 6.2, 4.2) for off in (-45, 45) for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    hh += [hz(a, -18, -1, 8.5, 10) for a in (-45, 45)]
    hh += [hz(a+b, yy, -1, 5, 10) for a in (-45, 45) for b in (-8, 8) for yy in (-45, 9)]
    hh += [hz(a, X_Y+OUTER+255, -1, 2.5, 10) for a in (-8, 8)]
    s = drill(box(0, 0, 0, 160, 120, 8), hh)
    for a in (-45, 45): s = s.cut(cq.Solid.makeCone(8.25, 4.25, 4, cq.Vector(a, -18, 0)))
    part_at(m, 'x_carriage').part = m.part('E02_X_Carriage_160x120x8', s, holes=hh,
        note='Metal X plate, no motor rides here. Two M8 countersinks retained; central M3 receiver pattern supports belt clamp. Smaller depth160->120, never print.')

    # Fresh Y platform removes the old rack saddle, outboard motor arm and pilots.
    sh = [hz(side*26, -215+20*j, -1, 2.5, 8) for side in (-1, 1) for j in range(10)]
    sh += [hz(side*44, yy, -1, 4.5, 8) for side in (-1, 1) for yy in (-217, -31)]
    sh += [hz(Y_AXIS_X+a, Y_FRONT+b, -1, 3.5, 8) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    sh += [hz(Y_AXIS_X, Y_FRONT, -1, 23, 8)]
    sh += [hz(Y_AXIS_X+a, Y_FRONT+b, 3, 6, 5) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    s = fuse(box(0, -118.5, 0, 104, 209, 6), box(81, Y_FRONT, 0, 64, 50, 6),
             box(81, -211.5, 0, 64, 23, 6), box(90, -215, 0, 46, 30, 6))
    s = drill(s, sh)  # main Y -223..-14; front wing stops at-15
    for xx, dia, length in ((0, 5.5, 7.5), (-12, 3.4, 5.5), (12, 3.4, 5.5)):
        s = s.cut(v2.slot_y(Y_AXIS_X+xx, Y_REAR-1, -1, length, dia, 8))
    part_at(m, 'y_spine').part = m.part('E02_Y_Spine_Winged_209x6', s, holes=sh,
        note='Metal main plate104x209, Y-223..-14, Zdeck-52..-46. Fixed motor/idler wings atX+85, aisle entirelyY<-14. Guide spacing52 (was26). Rear wing relieved around Z carriage. Rear slots allow idler -2mm; supplier rail pattern must be checked.')
    part_at(m, 'y_spine').origin = (x, 0, D-52)
    for name, side in [('y_rail', -1), ('y_rail_right', 1)]:
        part_at(m, name).origin = (x+side*26, -125, D-46)
    for name, side in [('y_block', -1), ('y_block_right', 1)]:
        part_at(m, name).origin = (x+side*26, -196, D-46)
    for i in m.items:
        if i.name.startswith('y_rail_bolt_'):
            xx, yy, zz = i.origin
            i.origin = (x+(-26 if xx < x else 26), yy, zz-6)

    # Tube support stays outside the complete guide-block sweep (X16..36),
    # not merely outside the narrower rail. End plugs carry rear compression;
    # separate sleeves are used only at the empty front tube sections.
    for side in (-1, 1):
        cut_world(m, f'tray_tube_{side*44}', [hz(x+side*44, yy, D-30, 4.5, 28) for yy in (-217, -31)])
        holes = [hz(-side*3, 0, -1, 4.5, 19)]
        spacer = m.part('E02_Y_Tube_Spacer_'+str(side), drill(box(0, 0, 0, 18, 12, 17), holes), holes=holes,
            note='Metal END spacer atY-217/-31, never midstroke across moving tab. Inner edgeX38 clears guide block outerX36. Partly overhangs spine but14mm seated width; through bolt at worldX+/-44. Verify joint stiffness.')
        for yy in (-217, -31):
            n = f'y_tube_spacer_{side}_{yy}'
            m.add(n, spacer, (x+side*47, yy, D-46), 'z')
            joint(m, n, 'y_spine', 'Seated metal END spacer; rear M3x55 with fitted solid plug, front M4x60 with separate sleeve; underside nuts')
            joint(m, n, f'tray_tube_{side*44}', 'Spacer top touches metal tube underside; no printed bending path')
    sleeve = m.part('E02_Compression_Sleeve_6x4p5x21', cyl(0, 0, 0, 3, 21).cut(cyl(0, 0, -1, 2.25, 23)), 'steel',
                    note='Metal sleeve inside hollow tube between its two2mm walls; do not omit or crush the tube with bolt preload.')
    # Rear tube already contains a solid end plug. Do NOT insert a second
    # sleeve through it and break into the axial M5 end taps. Fit its vertical
    # height to21 and use a smaller M3 through-hole between those two taps.
    for side in (-1, 1):
        plug = part_at(m, f'tray_tube_plug_{side*44}'); old = plug.part
        s = fuse(old.shape, box(0, 15, -10.5, 20.8, 30, .1), box(0, 15, 10.4, 20.8, 30, .1))
        holes = [hz(0, 11, -12, 3.4, 24)]
        plug.part = m.part('E02_Tube_EndPlug_Compression_21H', drill(s, holes), old.material, old.process,
            [*old.holes, *holes], 'Metal end plug, width20.8 and fitted vertical height21, no extra sleeve inside it. Rear M3 clearance atlocalY11 lies between retained axial M5 taps atX+/-5; verify tap web/fit and preload. Do not enlarge it to a6.2 sleeve bore.')
    csk = fuse(cq.Solid.makeCone(4.4, 1.55, 2.85, cq.Vector(0, 0, -.1), cq.Vector(0, 0, -1)), cyl(0, 0, -60, 1.55, 57.05))
    csk = m.part('E02_M4x60_Countersunk_Minor', csk, 'steel', 'purchased', note='M4x60 steel, 90deg head<=8.8; minor thread envelope. Head below tray surface, check actual DIN screw and stack.')
    washer = m.part('E02_M4_Washer_Z', cyl(0, 0, 0, 4.5, 1).cut(cyl(0, 0, -1, 2.15, 3)), 'steel', 'purchased')
    nutshape = cq.Workplane('XY').polygon(6, 7*2/math.sqrt(3)).extrude(3.2).val().cut(cyl(0, 0, -1, 2.1, 6))
    nut = m.part('E02_M4_Nut_Z', nutshape, 'steel', 'purchased')
    w3 = m.part('E02_M3_Washer_Z', cyl(0, 0, 0, 3.5, 1).cut(cyl(0, 0, -1, 1.7, 3)), 'steel', 'purchased')
    n3 = cq.Workplane('XY').polygon(6, 5.5*2/math.sqrt(3)).extrude(2.4).val().cut(cyl(0, 0, -1, 1.7, 5))
    n3 = m.part('E02_M3_Nut_Z', n3, 'steel', 'purchased')
    for side in (-1, 1):
        for yy in (-217, -31):
            o = (x+side*44, yy)
            if yy == -217:
                m.add(f'tube_top_washer_{side}', w3, (*o, D-4), 'z')
                m.add(f'tube_bolt_{side}_{yy}', bolt(m, 3, 55), (*o, D-3), 'z')
                m.add(f'tube_washer_{side}_{yy}', w3, (*o, D-53), 'z')
                m.add(f'tube_nut_{side}_{yy}', n3, (*o, D-55.4), 'z')
            else:
                m.add(f'tube_sleeve_{side}_{yy}', sleeve, (*o, D-27), 'z')
                m.add(f'tube_bolt_{side}_{yy}', csk, (*o, D), 'z')
                m.add(f'tube_washer_{side}_{yy}', washer, (*o, D-53), 'z')
                m.add(f'tube_nut_{side}_{yy}', nut, (*o, D-56.2), 'z')

    # A compact central head, raised only at the inherited locating interface.
    holes = [hz(a+b, yy, -1, 3.5, 6) for a in (-26, 26) for b in (-7.5, 7.5) for yy in (-8, 8)]
    holes += [hz(a+b, yy, 2.9, 6.2, 3) for a in (-26, 26) for b in (-7.5, 7.5) for yy in (-8, 8)]
    holes += [hz(a, yy, 3, dia, 9) for a in (-10, 10) for yy, dia in ((25, 2.5), (35, 3))]
    holes += [hx(Y_AXIS_X+7, yy, 2, 2.5, 10) for yy in (-11, -5)]
    head = fuse(box(0, 12, 0, 74, 56, 4), box(0, 30, 4, 36, 20, 6),
        box(66.5, -5, 1.5, 67, 18, 2.5), box(Y_AXIS_X+(OUTER+15)/2, -8, -9, 15-OUTER, 12, 13))
    head = head.cut(box(Y_AXIS_X+(-2+OUTER)/2, -8, -1, OUTER+2, 12.4, 6))
    part_at(m, 'y_puller_plate').part = m.part('E02_Y_Head_74x56_LightTab', drill(head, holes), holes=holes,
        note='Metal head, no moving motor arm. BaseZdeck-36..-32; locating pad reachesdeck-26. Side tab2.5mm thick carries clamp only, Y-14..4; clamp centredY-8 behind head datum. End spacers leave moving tab clear. Split jaw atX+85; check stiffness and vendor profile.')
    part_at(m, 'y_puller_plate').origin = (x, -196, D-36)
    for side in (-1, 1):
        for a in (-7.5, 7.5):
            for b in (-8, 8):
                m.add(f'y_block_bolt_{side}_{a}_{b}', bolt(m, 3, 6), (x+side*26+a, -196+b, D-33.1), 'y')
    for side in (-1, 1):
        for yy in (-222, -28):
            stop = m.part('E02_Y_Backed_Stop', box(0, 0, 0, 20, 6, 2.5), 'rubber', 'candidate',
                          note='End stop allocation above rail, below head. Needs retained metal backing; not a substitute for limit switch.')
            m.add(f'y_stop_{side}_{yy}', stop, (x+side*26, yy, D-39), 'z')

    # Existing complete motors, X fixed on base, Y face UP under Z platform.
    part_at(m, 'x_real_motor').origin = (X_LEFT, X_Y, 82); part_at(m, 'x_real_motor').group = 'fixed'
    old = part_at(m, 'y_real_motor')
    p = v2.Part('ZDT_RealMotor_E02_Y_Up', old.part.shape.rotate((0, 0, 0), (1, 0, 0), 180), 'purchased', 'purchased', [],
                'Complete actual motor CAD, mounting faceUP under Y spine. Fixed relative to Z; no longer travels143mm with the head. Verify rear connector/harness clearance.')
    m.parts[p.name] = p; old.part = p; old.origin = (x+Y_AXIS_X, Y_FRONT, D-52); old.group = 'z'
    add_x_drive(m)
    add_y_drive(m)
    compact_base_guard(m)
    for n in ('limit_x_min_candidate', 'limit_x_max_candidate'):
        i = part_at(m, n); i.origin = (i.origin[0], -327, 56)
    for n in ('limit_y_min_candidate', 'limit_y_max_candidate'):
        i = part_at(m, n); i.origin = (x-70, i.origin[1], D-46)
    m.items = [Item(i.name, i.part, i.origin, i.group) for i in m.items]
    used = {i.part.name for i in m.items}; m.parts = {n: p for n, p in m.parts.items() if n in used}
    return m


def add_x_drive(m):
    # One metal U stand: base, two legs and the flange plate share seated faces.
    s = fuse(box(0, 0, 0, 62, 20, 6), box(-27, 0, 6, 8, 16, 66), box(27, 0, 6, 8, 16, 66), box(0, 0, 72, 62, 50, 4))
    for yy in (-(INNER+OUTER)/2, (INNER+OUTER)/2):
        s = s.cut(box(27, yy, 53.5, 10, 3.4, 11))
    holes = [hz(a, b, -1, 4.5, 8) for a in (-18, 18) for b in (-5, 5)]
    holes += [hz(a, b, 71, 3.5, 6) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    holes += [hz(a, b, 71, 6, 3.1) for a in (-15.5, 15.5) for b in (-15.5, 15.5)] + [hz(0, 0, 71, 23, 6)]
    stand = m.part('E02_X_Fixed_Motor_UStand', drill(s, holes), holes=holes,
        note='Metal U stand, bottomZ6, flangeZ78..82. Belt passage notches in right leg, never block return strand. Fixed motor; base M4x12. Inspect leg/plate deflection and weld quality; do not print.')
    m.add('x_fixed_motor_stand', stand, (X_LEFT, X_Y, 6))
    joint(m, 'x_fixed_motor_stand', 'base', 'Four M4 through6mm foot into base')
    for a in (-18, 18):
        for b in (-5, 5):
            m.add(f'x_stand_bolt_{a}_{b}', bolt(m, 4, 12, head=4), (X_LEFT+a, X_Y+b, 12))
    for a in (-15.5, 15.5):
        for b in (-15.5, 15.5):
            m.add(f'x_motor_flange_{a}_{b}', bolt(m, 3, 6, '+Z'), (X_LEFT+a, X_Y+b, 80.1))
    m.add('x_drive_pulley', pulley(m), (X_LEFT, X_Y, X_Z))
    loop = belt_loop(X_RIGHT-X_LEFT).rotate((0, 0, 0), (0, 0, 1), -90)
    m.add('x_belt', m.part('E02_GT2_1000_6_Belt', loop, 'rubber', 'purchased',
        note='Purchased endless GT2, 2mm pitch, 6mm width, pitch length1000=500T. Nominal pulley centres480. Smooth envelope only; supplier tension/stiffness/rating pending.'), (X_LEFT, X_Y, X_Z))
    add_idler(m, 'x', (X_RIGHT, X_Y, X_Z), 'fixed')
    # Clamp teeth mesh intentionally into belt; only that named pair is exempt.
    face = X_Y+OUTER
    main = box(0, face+4, 0, 24, 8, 22.5)
    holes = [hz(a, face+5, -1, 3.4, 25) for a in (-8, 8)]
    holes += [hy(a, face-1, 20.5, 2.5, 11) for a in (-4, 4)]
    m.add('x_belt_clamp_main', m.part('E02_X_Clamp_Metal_Main', drill(main, holes), holes=holes,
        note='Metal block on X plate, Z51..73.5; two M3x30 vertical anchors, two M3x12 pinch bolts above belt. Must use matched GT2 jaw tooth form, not friction alone.'), (CELL_X, 0, 51), 'x')
    jaw = box(0, X_Y+INNER-1.8, 0, 20, 3.6, 14)
    # Shallow surrogate ribs indicate positive tooth engagement; actual GT2
    # tooth contour, belt compression and clamp proof remain supplier work.
    for k in range(10): jaw = jaw.fuse(box(-9+2*k, X_Y+INNER+.15, 1.5, .8, .3, 6))
    holes = [hy(a, X_Y+INNER-4, 11.5, 3.4, 5) for a in (-4, 4)]
    m.add('x_belt_pressure_jaw', m.part('E02_X_Clamp_Metal_Jaw', drill(jaw, holes), holes=holes,
        note='Metal GT2 clamp jaw, 2mm rib spacing illustrative ONLY; verify tooth profile and belt compression with actual belt. No printed structural clamp.'), (CELL_X, 0, 60), 'x')
    m.allow('x_belt_pressure_jaw', 'x_belt', 'Intentional GT2 tooth/pressure-jaw engagement; compression and pull-out NOT accepted')
    for a in (-8, 8): m.add(f'x_clamp_anchor_{a}', bolt(m, 3, 30), (CELL_X+a, face+5, 73.5), 'x')
    for a in (-4, 4): m.add(f'x_clamp_pinch_{a}', bolt(m, 3, 12, '+Y'), (CELL_X+a, X_Y+INNER-3.6, 71.5), 'x')
    joint(m, 'x_belt_clamp_main', 'x_carriage', 'Two M3x30, metal receiver, verify engagement')


def add_y_drive(m):
    x, D = m.x, m.deck
    for a in (-15.5, 15.5):
        for b in (-15.5, 15.5):
            m.add(f'y_motor_flange_{a}_{b}', bolt(m, 3, 6), (x+Y_AXIS_X+a, Y_FRONT+b, D-49), 'z')
    m.add('y_drive_pulley', pulley(m), (x+Y_AXIS_X, Y_FRONT, D-45), 'z')
    m.add('y_belt', m.part('E02_GT2_400_6_Belt', belt_loop(Y_FRONT-Y_REAR), 'rubber', 'purchased',
        note='Purchased endless GT2, 2mm pitch, 6mm wide, pitch length400=200T; pulley centres180. Side route atX+85 clears full guide blocks, tubes and the storage/IO aisle.'), (x+Y_AXIS_X, Y_REAR, D-45), 'z')
    add_idler(m, 'y', (x+Y_AXIS_X, Y_REAR, D-45), 'z')
    jaw = box((2+INNER)/2, -8, 0, INNER-2, 12, 13)
    for k in range(6): jaw = jaw.fuse(box(INNER+.15, -13+2*k, 1.5, .3, .8, 6))
    holes = [hx(1, yy, 11, 3.4, 6) for yy in (-11, -5)]
    m.add('y_belt_pressure_jaw', m.part('E02_Y_Clamp_Metal_Jaw', drill(jaw, holes), holes=holes,
        note='Metal pressure jaw in head side-tab pocket. GT2 profile indicative; matched tooth form and retention proof required. Pinch bolts above belt, nothing extends through fixed spine.'), (x+Y_AXIS_X, -196, D-45), 'y')
    for yy in (-11, -5): m.add(f'y_clamp_pinch_{yy}', bolt(m, 3, 12, '+X'), (x+Y_AXIS_X+2, -196+yy, D-34), 'y')
    m.allow('y_belt_pressure_jaw', 'y_belt', 'Intentional GT2 tooth/pressure-jaw engagement; compression and pull-out NOT accepted')


def add_idler(m, axis, origin, group):
    x, y, z = origin
    m.add(axis+'_idler_pulley', pulley(m, True), origin, group)
    bearing = m.part('E02_MR105ZZ_5x10x4', cyl(0, 0, 0, 5, 4).cut(cyl(0, 0, -1, 2.55, 6)), 'steel', 'purchased',
                     note='MR105ZZ bearing envelope; race construction/fit/load rating supplier-confirmed. Two per idler; do not print.')
    for k in (0, 1): m.add(f'{axis}_idler_bearing_{k}', bearing, (x, y, z+4*k), group)
    washer = m.part('E02_Idler_Inner_Washer', cyl(0, 0, 0, 4, 1).cut(cyl(0, 0, -1, 2.55, 3)), 'steel', 'purchased')
    m.add(axis+'_idler_top_washer', washer, (x, y, z+8), group)
    axle = fuse(cyl(0, 0, -16, 1.95, 16), cyl(0, 0, 0, 2.5, 15), cyl(0, 0, 15, 4.5, 3))
    # Head at pulleyZ+9, shoulder starts6mm below pulley.
    shaft = m.part('E02_M5_Idler_Shoulder_Axle', axle, 'steel', 'candidate',
        note='Custom/vendor shoulder axle: D5x15 shoulder, M5 minor-envelope threadx16, headOD9x3. Actual thread length, retention and seating must be selected, not a loose M5 screw.')
    m.add(axis+'_idler_axle', shaft, (x, y, z-6), group)
    if axis == 'x':
        s = fuse(box(0, 0, 0, 56, 24, 6), box(0, 0, 6, 16, 16, 42))
        holes = [hz(0, 0, 30, 4.2, 20)]
        for a in (-18, 18):
            for b in (-6, 6):
                slot = v2.slot_y(0, 0, -1, 8.5, 4.5, 8).rotate((0, 0, 0), (0, 0, 1), 90).translate((a, b, 0))
                s = s.cut(slot)
        support = m.part('E02_X_Idler_Slotted_Stand', drill(s, holes), holes=holes,
            note='Metal standZ6..54, base6. Slots permit idler+2mm alongX. Four M4x12 lock bolts plus M3 pusher; tension from belt vendor, not arbitrary high preload.')
        m.add('x_idler_stand', support, (x, y, 6))
        spacer = cyl(0, 0, 0, 4, 6).cut(cyl(0, 0, -1, 2.55, 8))
        m.add('x_idler_spacer', m.part('E02_X_Idler_Spacer_D8x6', spacer, 'steel'), (x, y, z-6))
        joint(m, 'x_idler_stand', 'base', 'Four M4 in X slots, M3 pusher; lock after measured belt tension')
        for a in (-18, 18):
            for b in (-6, 6): m.add(f'x_idler_lock_{a}_{b}', bolt(m, 4, 12, head=4), (x+a, y+b, 12))
        ah = [hz(0, a, -1, 3.4, 15) for a in (-5, 5)] + [hx(-5, 0, 3, 2.5, 10)]
        adj = m.part('E02_X_Tension_Pusher_Base', drill(box(0, 0, 0, 8, 16, 12), ah), holes=ah)
        m.add('x_tension_base', adj, (x-36, y, 6))
        joint(m, 'x_tension_base', 'base', 'Two M3x16 anchors; M3x16 pusher contacts stand, head stays outside threaded block at full adjustment')
        for a in (-5, 5): m.add(f'x_tension_mount_{a}', bolt(m, 3, 16), (x-36, y+a, 18))
        m.add('x_tension_pusher', bolt(m, 3, 16, '+X'), (x-44, y, 9))
    else:
        D = m.deck
        carrier_h = [hz(0, 0, -1, 4.2, 8)] + [hz(a, 0, -1, 2.5, 8) for a in (-12, 12)]
        carrier = m.part('E02_Y_Idler_Underside_Carrier', drill(box(0, 0, 0, 32, 12, 6), carrier_h), 'steel', holes=carrier_h,
                         note='Steel tension carrier under spine, Zdeck-58..-52; slots permit rearward2mm. Central M5 axle thread; two M3x10 locking screws from above.')
        m.add('y_idler_carrier', carrier, (x, y, D-58), 'z')
        # Replace generic shoulder by an appropriate shorter axial stack. Its
        # thread passes the spine clearance slot into the underside steel tap.
        sa = fuse(cyl(0, 0, -13, 1.95, 13), cyl(0, 0, 0, 2.5, 15), cyl(0, 0, 15, 4.5, 3))
        part_at(m, 'y_idler_axle').part = m.part('E02_Y_M5_Shoulder_Axle', sa, 'steel', 'candidate',
            note='D5 shoulder15 + M5 minor-envelope13; shaft shoulder startsdeck-51, headdeck-36..-33. Supplier thread/shoulder stack to be verified.')
        part_at(m, 'y_idler_axle').origin = (x, y, D-51)
        spacer = cyl(0, 0, 0, 4, 1).cut(cyl(0, 0, -1, 2.55, 3))
        m.add('y_idler_spacer', m.part('E02_Y_Idler_Spacer_D8x1', spacer, 'steel'), (x, y, D-46), 'z')
        joint(m, 'y_idler_carrier', 'y_spine', 'Carrier top seats on spine underside, two M3 lock bolts')
        for a in (-12, 12): m.add(f'y_idler_lock_{a}', bolt(m, 3, 10), (x+a, y, D-46), 'z')
        ah = [hz(a, 0, -1, 3.4, 16) for a in (-6, 6)] + [hy(0, -4, 11, 2.5, 9)]
        adj = m.part('E02_Y_Tension_Pusher_Base', drill(box(0, 0, 0, 20, 6, 14), ah), holes=ah)
        m.add('y_tension_base', adj, (x, y+13, D-66), 'z')
        cut_world(m, 'y_spine', [hz(x+a, y+13, D-53, 2.5, 8) for a in (-6, 6)])
        for a in (-6, 6): m.add(f'y_tension_mount_{a}', bolt(m, 3, 18, '+Z'), (x+a, y+13, D-66), 'z')
        m.add('y_tension_pusher', bolt(m, 3, 12, '-Y'), (x, y+18, D-55), 'z')
        joint(m, 'y_tension_base', 'y_spine', 'Two M3 underside anchors, pusher contacts carrier front')


def compact_base_guard(m):
    # E01's rear drive package is gone: restore590 depth but keep full enclosure.
    e01.add_guards(m)
    for i in m.items:
        if i.name.startswith(('guard_foot_', 'guard_post_')) and i.origin[1] == -405:
            i.origin = (i.origin[0], -345, i.origin[2])
        elif i.name == 'guard_cross_-405': i.origin = (15, -345, 500)
        elif i.name.startswith('guard_side_'):
            i.part = m.part('Guard_Side_E02_520', v2.extrusion(20, 520, 'Y'), process='purchased')
            i.origin = (i.origin[0], -75, 500)
        elif i.name == 'guard_panel_y-431.5':
            i.part = m.part('E02_Guard_Rear_PC3', box(15, -371.5, 0, 610, 3, 520), 'guard', 'cut_panel')
        elif i.name.startswith('guard_panel_x'):
            xx = -291.5 if '-' in i.name.split('x')[-1] else 321.5
            s = box(xx, -75, 0, 3, 590, 520)
            if xx < 0: s = s.cut(box(xx, 69, 190, 5, 138, 100))
            i.part = m.part('E02_Guard_Side_'+str(xx), s, 'guard', 'cut_panel')
        elif i.name == 'guard_roof':
            i.part = m.part('E02_Guard_Roof', box(15, -75, 520, 616, 596, 3), 'guard', 'cut_panel')
    holes = [hz(xx, yy, -1, 4.2, 8) for xx in (-175, -75, 25, 125) for yy in (-285, -215)]
    holes += [hz(CELL_X+a, yy, -1, 5, 8) for a in (-45, 45) for yy in (20, 130)]
    holes += [hz(CELL_X+a, 75, -1, 6, 8) for a in (-75, 75)]
    holes += [hz(IO_X+a+b, yy+c, -1, 4.2, 8) for a in (-65, 65) for b in (-14, 14) for yy in (10, 140) for c in (-14, 14)]
    holes += [hz(xx+a, yy+b, -1, 3.3, 8) for xx in (-265, 295) for yy in (-345, 195) for a in (-14, 14) for b in (-14, 14)]
    holes += [hz(xx, yy, -1, 8.5, 8) for xx in (-230, 270) for yy in (-345, 170)]
    holes += [hz(X_LEFT+a, X_Y+b, -1, 3.3, 8) for a in (-18, 18) for b in (-5, 5)]
    holes += [hz(X_RIGHT+a, X_Y+b, -1, 3.3, 8) for a in (-18, 18) for b in (-6, 6)]
    holes += [hz(X_RIGHT-36, X_Y+a, -1, 2.5, 8) for a in (-5, 5)]
    part_at(m, 'base').part = m.part('E02_Base_610x590x6', drill(box(15, -75, 0, 610, 590, 6), holes), holes=holes,
        note='Continuous metal base, depth650->590. Rack supports and abandoned holes removed. Fully supporting bench + anchors must be designed/verified separately.')


def export(m):
    for sub in ('parts', 'stl', 'viewing', 'drawings', 'previews'): (OUT/sub).mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name='BELT_ONE_CELL_E02_NOT_LOAD_ACCEPTED')
    for i in m.items:
        color = (.95, .56, .12) if i.part.process == 'candidate' else v2.COLORS.get(i.part.material, (.6, .6, .6))
        assembly.add(i.located(), name=i.name, color=cq.Color(*color))
    assembly.save(str(OUT/'Belt_MVP_E02_ASSEMBLY.step'))
    compound = cq.Compound.makeCompound([s for i in m.items for s in i.located().Solids()])
    STEPControl_Writer(); schema = Interface_Static.CVal_s('write.step.schema'); mode = Interface_Static.IVal_s('write.step.assembly')
    try:
        if not Interface_Static.SetCVal_s('write.step.schema', 'AP203') or not Interface_Static.SetIVal_s('write.step.assembly', 0):
            raise RuntimeError('Cannot select flat AP203 writer')
        writer = STEPControl_Writer()
        if writer.Transfer(compound.wrapped, STEPControl_AsIs) != IFSelect_RetDone: raise RuntimeError('STEP transfer failed')
        if writer.Write(str(OUT/'viewing/Belt_MVP_E02_SOLIDS_AP203.step')) != IFSelect_RetDone: raise RuntimeError('STEP write failed')
    finally:
        Interface_Static.SetCVal_s('write.step.schema', schema); Interface_Static.SetIVal_s('write.step.assembly', mode)
    rows = []
    for k, p in enumerate(sorted(m.parts.values(), key=lambda p: (p.process, p.name)), 1):
        code = f'B{k:03}'; b = p.shape.BoundingBox()
        cq.exporters.export(p.shape, str(OUT/'parts'/(code+'.step')))
        row = {'code': code, 'name': p.name, 'quantity': sum(i.part.name == p.name for i in m.items),
               'material': p.material, 'process': p.process, 'solids': len(p.shape.Solids()), 'volume_mm3': p.shape.Volume(),
               'bounds_mm': v2.bbox(p.shape), 'extents_mm': [b.xlen, b.ylen, b.zlen], 'holes': p.holes, 'note': p.note}
        if p.process == 'print':
            s = p.shape.translate((-b.xmin, -b.ymin, -b.zmin))
            cq.exporters.export(s, str(OUT/'stl'/(code+'.stl')), tolerance=.03, angularTolerance=.1)
        rows.append(row)
    manifest = {'version': 'E02', 'fingerprint': FINGERPRINT, 'units': 'mm', 'parts': rows,
        'instances': [{'name': i.name, 'part': i.part.name, 'origin_mm': i.origin, 'group': i.group} for i in m.items],
        'joints': m.joints, 'allowed_contacts': [{'a': a, 'b': b, 'reason': reason} for (a, b), reason in m.allowed.items()],
        'motor_quantity': 3, 'target_payload_kg': 1, 'screw_lead_mm': 2,
        'axes': {'X': 'GT2/20T/6mm fixed motor', 'Y': 'GT2/20T/6mm motor on Z, not on head', 'Z': 'METAL TR8x2'},
        'belts': {'X': {'pitch_length_mm': 1000, 'centres_mm': 480}, 'Y': {'pitch_length_mm': 400, 'centres_mm': 180}},
        'belt_pitch_mm': 2, 'pulley_teeth': 20, 'advance_mm_rev': 40, 'Y_guide_spacing_mm': 52,
        'motion_limits': {'X_mm': [-90, 90], 'Z_deck_mm': [200, 295], 'Y_transfer_mm': [0, 143]},
        'base_mm': [610, 590, 6], 'maintenance_pin_shown_installed': True,
        'hardware_accepted': False, 'loaded_operation_allowed': False, 'control_firmware_implemented': False,
        'independent_brake_selected': False, 'motor_torque_curve_verified': False}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    with (OUT/'BOM.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['code', 'name', 'quantity', 'material', 'process', 'note'], extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    print('EXPORTED E02', len(rows), 'parts', len(m.items), 'instances', flush=True)


if __name__ == '__main__':
    m = build_model()
    bad, accepted = v2.collisions(m.items, m.allowed)
    print(json.dumps({'static_collisions': bad, 'accepted_contacts': accepted, 'parts': len(m.parts), 'instances': len(m.items)}, indent=2), flush=True)
