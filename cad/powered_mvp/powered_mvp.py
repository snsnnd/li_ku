"""E01: one storage cell + IO, three actual ZDT motors, XY racks, TR8x2 Z.

1 kg is a design input, NOT an accepted operating load. Motor electrical/torque
data, independent rail brake and control hardware remain explicit release gates.
Previous manual and V03.1 deliveries are never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'cad/v03_1'))
import asrs_v03_1 as prior

v3, v2 = prior.baseline, prior.v2
box, cyl, fuse, drill, hz, hy, hx = prior.box, prior.cyl, prior.fuse, prior.drill, prior.hz, prior.hy, prior.hx
OUT = ROOT/'model/Powered_1Cell_MVP'
DEPENDENCIES = [Path(__file__), *prior.DEPENDENCIES]
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
CELL_X, CELL_Z, IO_X, IO_Z = 90., 295., -90., 200.
SCREW_LEAD = 2.
RACK_START = -2*v3.SEGMENT_LENGTH
X_FEET = (-200, -100, 0, 100, 200)
ROTATING_Z = {'z_screw', 'z_shaft_collar', 'z_thrust_cross_pin', 'z_coupling'}


@dataclass(frozen=True)
class Design(v3.Design):
    columns: int = 1
    rows: int = 1
    first_deck: float = CELL_Z
    z_rail_max: float = 335.
    x_block_offsets: tuple = (-45., 45.)


class Item(v3.Item):
    def located(self, dx=0, dz=0, q=0, pin_lift=0, bin_q=None, io_open=0):
        group = 'x' if self.group == 'maintenance' else self.group
        base = v3.Item(self.name, self.part, self.origin, group)
        shape = base.located(dx, dz, q, pin_lift, bin_q, io_open)
        if self.name in ROTATING_Z:
            shape = shape.rotate((CELL_X+dx, -268, 0), (CELL_X+dx, -268, 1), 360*dz/SCREW_LEAD)
        return shape


def change(m, name, p, origin=None):
    i = next(i for i in m.items if i.name == name)
    i.part = p
    if origin is not None:
        i.origin = origin
    return i


def add_joint(m, a, b, purpose):
    m.joints.append({'a': a, 'b': b, 'purpose': purpose, 'strength_verified': False})


def bolt(m, size, length, head=3):
    # Threads are shown at their minor-diameter envelope so geometrical thread
    # overlap with tapped pilots is not misreported as an unintended collision.
    minor = {3: 2.4, 4: 3.1, 5: 3.9, 8: 6.6}[size]
    diameter = {3: 5.5, 4: 7, 5: 8.5, 8: 13}[size]
    return m.part(f'M{size}x{length}_Head{head}_ThreadMinor',
                  fuse(cyl(0, 0, -length, minor/2, length), cyl(0, 0, 0, diameter/2, head)),
                  'steel', 'purchased', note=f'Nominal M{size}x{length}; head OD{diameter} h{head}. Thread shown at minor envelope, NOT a manufacturing thread definition.')


def split_hub(m):
    # Shaft seat 5H7, 12 mm register in original printed pinion. Upper clamp
    # starts ABOVE the attachment screw heads instead of intersecting them.
    s = fuse(cyl(0, 0, -3, 12, 3), cyl(0, 0, 0, 6, 16), cyl(0, 0, 16, 7, 7))
    s = s.cut(cyl(0, 0, -4, 2.5, 29)).cut(box(0, 4, 0, .8, 8, 24))
    hh = [hz(a, 0, -4, 3.4, 5) for a in (-9, 9)]
    hh += [hx(-9, 5, 19, 2.5, 18), hx(-9, 5, 19, 3.4, 9)]
    return m.part('E01_Metal_SplitHub_D5', drill(s, hh), 'aluminum', 'machined', holes=hh,
        note='CUSTOM METAL, not printed: bore 5H7; register OD12, flange OD24x3, upper clamp OD14 Z16..23; slit0.8; M3 clamp at Y5 Z19. Pinion attachment 2xM3 at X+/-9. Validate clamp torque and axial retention on actual shaft before use.')


def build_model():
    m = prior.build_model()
    m.joints = []
    # Keep one column, its Z295 shelf, the separate IO, and the existing real
    # metal guide/head interfaces. Drop wireless batteries and BOTH reducers.
    removed = {'z_real_motor', 'z_motor_plate', 'z_motor_module_link', 'z_pinion', 'z_pinion_hub',
               'z_reduction_candidate', 'z_reducer_output_candidate', 'y_reduction_candidate',
               'y_reducer_output_candidate', 'y_motor_leg_outboard', 'x_motor_leg_-22', 'x_motor_leg_22',
               'tool_camera_candidate', 'tool_camera_mount', 'y_power_z_support'}
    def obsolete(i):
        if i.name in removed or i.name.startswith(('base_panel_', 'base_splice_', 'guard_', 'x_beam_', 'x_track_', 'x_stop_',
            'x_rack_', 'z_rack_', 'column_1_', 'column_2_', 'column_3_', 'stored_bin_', 'column_0_reference')):
            return True
        if i.name.startswith(('cell_', 'shelf_angle_')) and not i.name.startswith(('cell_0_1', 'shelf_angle_0_1_')):
            return True
        if any(t in i.name for t in ('power_', 'battery_candidate', 'esp32_candidate')):
            return True
        return i.name.endswith('_marker') or i.part.material == 'guard' and not i.name.startswith('io_')
    v3.remove(m, obsolete)
    for i in m.items:
        xx, yy, zz = i.origin
        if i.group not in ('fixed', 'io_shutter'):
            xx -= 180
        if i.group in ('z', 'zgear', 'y', 'ygear', 'pin', 'bin', 'crank', 'roller', 'spring'):
            zz -= 95
        if i.name.startswith('io_'):
            xx += 60
        i.origin = (xx, yy, zz)
    m.x, m.deck, m.d = CELL_X, CELL_Z, Design()
    x, D = m.x, m.deck

    # Continuous, anchored metal base (not a printed 1 kg load path).
    base = m.part('E01_Base_610x650x6', box(15, -105, 0, 610, 650, 6),
                  note='Continuous 6061/steel base on continuously supporting bench; all anchor/receiving pilots in this CAD. Four bench anchors require actual bench design.')
    m.add('base', base)

    # Reuse the proven 400 mm rail/500 mm screw concept at reduced heights.
    post = m.part('3030_E01_Z350', v2.extrusion(30, 350, 'Z'), process='purchased',
                  note='Two real 3030 metal extrusions. Verify actual slot, straightness and end M8 taps.')
    for off in (-45, 45):
        change(m, f'z_post_{off}', post)
    zh = [hz(a, 0, -1, 8.5, 14) for a in (-45, 45)]
    zh += [hz(a, b, -1, 3.5, 14) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    zh += [hz(a, b, -1, 6, 4.1) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
    zh += [hz(0, 0, -1, 23, 14)] + [hz(a, 0, -1, 4.5, 14) for a in (-23, 23)]
    top = m.part('E01_Z_Top_130x60x12', drill(box(0, 0, 0, 130, 60, 12), zh), holes=zh,
                 note='Z401..413. Motor screws are recessed from underside by3.1 mm to avoid the bearing hanger. M3x12 gives about3.1 mm motor engagement; verify actual blind depth.')
    change(m, 'z_top_plate', top, (x, -268, 401))
    # Rear extension separates X motor from the screw's lower support. Shift
    # the X blocks outward5 mm so their screws clear the tower countersinks.
    carriage = next(i for i in m.items if i.name == 'x_carriage')
    xholes = [h for h in carriage.part.holes if h[2] not in (3.5, 6.2)]
    xholes += [hz(off+a, yy+b, -1, 3.5, 10) for off in (-45, 45) for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    xholes += [hz(off+a, yy+b, 4.8, 6.2, 4.2) for off in (-45, 45) for yy in (-35, 35) for a in (-10, 10) for b in (-10, 10)]
    carriage.part = m.part('E01_X_Carriage_160x160', drill(box(0, -25, 0, 160, 160, 8), xholes), holes=xholes)
    for i in m.items:
        if i.name.startswith('x_block_'):
            xx, yy, zz = i.origin
            i.origin = (xx + (5 if xx > x else -5), yy, zz)
    # Countersunk tower bolts avoid the rear X-bearing blocks under the plate.
    for off in (-45, 45):
        item = next(i for i in m.items if i.name == 'x_carriage')
        local_x, local_y = off, -18
        cut = cq.Solid.makeCone(8.25, 4.25, 4, cq.Vector(local_x, local_y, 0))
        item.part = m.part('E01_X_Carriage_CountersunkM8' + ('_done' if off > 0 else '_first'), item.part.shape.cut(cut),
                           holes=item.part.holes, note='Metal 160x160x8, including rear motor-support extension. Two underside countersinks OD16.5x90deg for M8 tower bolts; head must not protrude into X blocks.')

    # True recessed rail-head geometry, not cap heads protruding into sliders.
    r, rh = v2.rail_shape(12, 8, 400, 25)
    r = drill(r, [hz(0, h[0][1], 4.5, 6, 5) for h in rh])
    xr = m.part('MGN12_E01_X400', r.rotate((0, 0, 0), (0, 0, 1), -90), 'steel', 'purchased',
                note='Supplier MGN12 L400, pitch25/end10 assumption; counterbores shown for M3 cap heads. Confirm actual supplier drawing.')
    bh = [hz(-190+25*j, 0, 15, 2.5, 11) for j in range(16)]
    bh += [hz(xx, 0, -1, 5.5, 27) for xx in (-175, -75, 25, 125)]
    bh += [hz(xx, 0, 20, 9.5, 6) for xx in (-175, -75, 25, 125)]
    beam = m.part('E01_X_Datum_400x30x24', drill(box(0, 0, 0, 400, 30, 24), bh), holes=bh)
    stop = m.part('E01_X_Stop', box(0, 0, 0, 24, 20, 8), 'rubber', 'purchased', note='Backed, retained bumper; not a replacement for a physical end-limit switch.')
    for yy in (-285, -215):
        m.add(f'x_beam_{yy}', beam, (0, yy, 6))
        m.add(f'x_track_{yy}', xr, (0, yy, 30))
        for end in (-190, 190):
            m.add(f'x_stop_{end}_{yy}', stop, (end, yy, 43))
        add_joint(m, f'x_beam_{yy}', 'base', 'M5 base bolts, rail screws recessed below the rail face')

    r, rhz = v2.rail_shape(12, 8, 250, 25)
    r = drill(r, [hz(0, h[0][1], 4.5, 6, 5) for h in rhz])
    zr = m.part('MGN12_E01_Z250', r.rotate((0, 0, 0), (1, 0, 0), 90).rotate((0, 0, 0), (0, 0, 1), 180), 'steel', 'purchased')
    strip_h = [hy(0, -1, -115+25*j, 2.5, 7) for j in range(10)]
    strip_h += [hy(0, -1, z, 5.5, 7) for z in (-102.5, -2.5, 97.5)]
    strip_s = drill(box(0, 2, -125, 20, 4, 250), strip_h)
    for zz in (-102.5, -2.5, 97.5):
        strip_s = strip_s.cut(cq.Solid.makeCone(2.75, 5.2, 2.45, cq.Vector(0, 1.55, zz), cq.Vector(0, 1, 0)))
    strip = m.part('E01_Z_Rail_Datum_250', strip_s, holes=strip_h)
    for off in (-45, 45):
        change(m, f'z_strip_{off}', strip, (x+off, -253, 210))
        change(m, f'z_rail_{off}', zr, (x+off, -249, 210))
        add_joint(m, f'z_strip_{off}', f'z_post_{off}', 'Three flush M5 slot-nut joints')
    for i in m.items:
        if i.name.startswith('z_stop_') and i.origin[2] == 584:
            xx, yy, zz = i.origin; i.origin = (xx, yy, 299)
    yr0, yrh = v2.rail_shape(9, 6.5, 200, 20)
    yr0 = drill(yr0, [hz(0, h[0][1], 3, 6, 4.5) for h in yrh])
    yr = m.part('MGN9_E01_Y200', yr0, 'steel', 'purchased')
    change(m, 'y_rail', yr); change(m, 'y_rail_right', yr)

    # X: integer-pitch rack row with five positively seated metal feet.
    rack = next(p for p in m.parts.values() if p.name == 'Rack_M1p5_24T_X')
    for j in range(4):
        m.add(f'x_rack_{j}', rack, (RACK_START+j*v3.SEGMENT_LENGTH, -322, 66))
    xh = [hy(RACK_START+j*v3.SEGMENT_LENGTH+t, -4, z, 2.5, 8)
          for j in range(4) for t in (6*v3.PITCH, 18*v3.PITCH) for z in (4, 26)]
    xh += [hy(xx+off, -4, z-51, 3.3, 8) for xx in X_FEET for off in (-8, 8) for z in (56, 76)]
    backbone = m.part('E01_X_Rack_Backbone_470', drill(box(0, 0, 0, 470, 6, 30), xh), holes=xh)
    m.add('x_rack_backbone', backbone, (0, -325, 51))
    foot = next(p for p in m.parts.values() if p.name == 'X_Rack_Bolted_Adjustable_Foot')
    for xx in X_FEET:
        m.add(f'x_rack_foot_{xx}', foot, (xx, 0, 0))
        add_joint(m, f'x_rack_foot_{xx}', 'base', 'Four M5, +/-1 mm Y alignment slots; lock the whole row straight')
        add_joint(m, f'x_rack_foot_{xx}', 'x_rack_backbone', 'Four M4 into backing')
    phase_x = -math.degrees((x-RACK_START)/v3.RADIUS)
    xp = m.part('E01_Pinion_X_M1p5_20T', v3.pinion().rotate((0, 0, 0), (0, 0, 1), phase_x), 'PETG', 'print',
                note='Horizontal X only; original 20T m1.5 20deg. Experimental printed tooth endurance still needs proof.')
    change(m, 'x_pinion', xp)

    # Three user-supplied complete motors. Z shaft DOWN, no 10:1 gearbox.
    motor = next(p for p in m.parts.values() if p.name == 'ZDT_RealMotor_X')
    mz = v2.Part('ZDT_RealMotor_E01_Z', motor.shape, 'purchased', 'purchased', [],
                 'Actual user 24-solid motor CAD, inverted for vertical TR8x2. Torque/electrical/thermal data NOT inferred from CAD.')
    m.parts[mz.name] = mz
    m.add('z_real_motor', mz, (x, -268, 413), 'x')
    change(m, 'y_real_motor', next(p for p in m.parts.values() if p.name == 'ZDT_RealMotor_Y'), (x+93, -196, D+1))
    # Motor flange and module attachment holes are separate patterns.
    mh = [hz(a, b, -1, 3.5, 6) for a in (-15.5, 15.5) for b in (-15.5, 15.5)] + [hz(0, 0, -1, 23, 6)]
    xmh = mh+[hz(a, b, -1, 3.4, 6) for a in (-28, 28) for b in (-4.5, 4.5)]
    xplate = m.part('E01_X_Motor_Plate_62x50', drill(box(0, 0, 0, 62, 50, 4), xmh), holes=xmh,
                    note='Outer module bolts kept outside the 42 mm motor face; motor pattern31x31/Ø23 pilot.')
    change(m, 'x_motor_plate', xplate)
    leg_h = [hz(0, yy, -1, 3.4, 33) for yy in (-4.5, 4.5)]
    xleg = m.part('E01_X_Motor_Leg', drill(box(0, 0, 0, 6, 16, 31), leg_h), holes=leg_h)
    for off in (-28, 28):
        m.add(f'x_motor_leg_{off}', xleg, (x+off, -299, 51), 'x')
        add_joint(m, f'x_motor_leg_{off}', 'x_carriage', 'M3x40 through plate/leg into metal X plate')
        add_joint(m, f'x_motor_leg_{off}', 'x_motor_plate', 'Seated motor module')
    prior.cut_world(m, 'x_carriage', [hz(x+off, -341+yy, 44, 2.5, 8) for off in (-28, 28) for yy in (-4.5, 4.5)])
    ymh = mh+[hz(28, yy, -1, 3.4, 6) for yy in (-4.5, 4.5)]
    yplate = m.part('E01_Y_Motor_Plate_62x50', drill(box(0, 0, 0, 62, 50, 4), ymh), holes=ymh)
    change(m, 'y_motor_plate', yplate)
    yl = m.part('E01_Y_Motor_Leg', drill(box(0, 0, 0, 8, 40, 32),
                 [hz(0, yy, -1, 3.4, 34) for yy in (-4.5, 4.5)]), holes=[hz(0, yy, -1, 3.4, 34) for yy in (-4.5, 4.5)])
    m.add('y_motor_leg_outboard', yl, (x+121, -196, D-35), 'y')
    # Recover the full V03 base, trim to128 instead of120, add a lower outboard rib.
    hbase = next(i for i in m.items if i.name == 'y_puller_plate')
    short = fuse(hbase.part.shape, box(122, 0, -9, 12, 16, 4))
    short = short.fuse(box(85, 0, -15, 86, 12, 6))  # X42..128, below the bridge, outside Y-spine edge
    yh = [hz(121, yy, -16, 3.4, 16) for yy in (-4.5, 4.5)]
    hbase.part = m.part('E01_Y_Module_Base_Ribbed', drill(short, yh), holes=yh,
                       note='Metal head bridge, X-28..128; outboard underside rib X42..128. M3x50 motor module through-bolts below the added rib; minor-thread envelopes shown.')
    add_joint(m, 'y_motor_leg_outboard', 'y_puller_plate', 'Two M3x50 with underside nuts, not a printed motor clamp')
    add_joint(m, 'y_motor_leg_outboard', 'y_motor_plate', 'Motor face seated on machined plate')
    hub = split_hub(m)
    for axis, phase in [('x', phase_x), ('y', math.degrees((-196+242)/v3.RADIUS))]:
        hp = m.part('E01_Hub_'+axis.upper(), hub.shape.rotate((0, 0, 0), (0, 0, 1), phase), 'aluminum', 'machined',
                    holes=hub.holes, note=hub.note)
        change(m, axis+'_pinion_hub', hp)

    # Restore the complete metal TR8x2 support path from frozen V02, shortened
    # 250 mm at the top. Real threads are supplier interfaces, not smooth bores.
    donor = v2.build_model()
    screw_names = {'z_working_nut', 'z_safety_nut', 'z_nut_bridge', 'z_safety_cage',
        'safety_nut_key_-8', 'safety_nut_key_8', 'z_fixed_bearing_housing', 'z_thrust_end_cap', 'z_bearing_hanger',
        'z_fixed_radial_bearing', 'z_thrust_abutment', 'z_shaft_collar', 'z_thrust_cross_pin',
        'z_floating_bearing', 'z_floating_bearing_cap', 'z_floating_radial_bearing', 'z_floating_pedestal', 'z_coupling'}
    for i in donor.items:
        if i.name not in screw_names and not i.name.startswith('z_thrust_bearing_'):
            continue
        xx, yy, zz = i.origin
        xx += x-donor.x
        if i.group == 'z':
            zz += D-donor.deck
        elif i.name not in ('z_floating_bearing', 'z_floating_bearing_cap', 'z_floating_radial_bearing', 'z_floating_pedestal'):
            zz -= 250
        m.parts[i.part.name] = i.part
        m.add(i.name, i.part, (xx, yy, zz), i.group)
    screw = fuse(cyl(0, 0, 110, 4, 228), cyl(0, 0, 90, 3, 20), cyl(0, 0, 338, 3, 50))
    screw = screw.cut(cyl(-4, 0, 362.5, 1.25, 8, (1, 0, 0)))
    p = m.part('E01_TR8x2_CustomEnds_L298', screw, 'steel', 'purchased',
        note='TR8x2, NOT TR8x8. Overall Z90..388=L298; working thread Z110..338; journalsØ6 x20/50; matched Ø2.5 cross-hole atZ362.5. Shaft/nut thread accuracy and heat-treated shaft strength supplier-verified before fabrication.')
    m.add('z_screw', p, (x, -268, 0), 'x')
    # Do not reuse the old lower upright holes through the horizontal nut seat:
    # their bolt heads would be buried in the base. Widen the upright and put
    # both rows ABOVE the seat, outside the twin Y rails for nut access.
    nh = [hz(a, b, -1, 2.5, 10) for a, b in ((-8, 0), (8, 0), (0, -8), (0, 8))]
    nh += [hz(0, 0, -1, 11, 10)]
    nh += [hz(a, b, -1, 2.5, 10) for a in (-16, 16) for b in (-9, 9)]
    nh += [hy(a, 23, z, 4.5, 11) for a in (-23, 23) for z in (16, 48)]
    ns = fuse(box(0, 10, 0, 40, 44, 8), box(0, 28, 8, 56, 8, 48))
    npart = m.part('E01_Z_Nut_Bridge_Accessible', drill(ns, nh), 'steel', holes=nh,
        note='Steel nut seat 40x44x8; upright 56x8 toZ56. Four accessible M4 through-bolts at X+/-23,Z16/48, ABOVE the seat and OUTSIDE Y rails. Upper row clears Y end stop. Four M3 nut-flange taps, secondary-cage taps retained.')
    change(m, 'z_nut_bridge', npart)
    prior.cut_world(m, 'z_carriage', [hy(x+a, -237, D+z, 4.5, 10) for a in (-23, 23) for z in (-54, -22)])
    coupling = next(i for i in m.items if i.name == 'z_coupling')
    coupling.part = m.part('E01_Coupler_5x6_CANDIDATE', coupling.part.shape, 'purchased', 'candidate',
        note='Purchase a real positively clamped 5x6 coupler within Ø19x25. CAD is only fit allocation; clamp screws/compliance/rating must be replaced by vendor drawing.')
    add_joint(m, 'z_nut_bridge', 'z_carriage', 'Steel bridge to Z plate, not polymer; four accessible M4 through-bolts/nuts')
    add_joint(m, 'z_working_nut', 'z_nut_bridge', 'Bronze flange seats on steel bridge at deck-62')
    add_joint(m, 'z_safety_cage', 'z_nut_bridge', 'Independent captive second nut; not a self-locking guarantee')
    add_joint(m, 'z_floating_pedestal', 'x_carriage', 'Lower bearing support sits on X plate')
    add_joint(m, 'z_fixed_bearing_housing', 'z_thrust_end_cap', 'Positive thrust package cap sits on housing')
    add_joint(m, 'z_thrust_end_cap', 'z_bearing_hanger', 'Cap transfers axial load to the metal hanger; inspect through-bolt stack')
    add_joint(m, 'z_bearing_hanger', 'z_top_plate', 'Top bearing hanger seated under metal cross plate')

    # Real steel maintenance prop, separate from the unselected automatic brake.
    track_h = [hx(-4, 0, z, 4.2, 9) for z in (13, 108)]
    track_h += [hx(-4, 0, z, 4.2, 9) for z in (40, 65, 140, 165, 190, 215, 240, 265, 290)]
    track = m.part('E01_Independent_Steel_Track_300', drill(box(0, 0, 0, 6, 30, 300), track_h), 'steel', holes=track_h,
        note='Separate from screw. Maintenance pin holes at globalZ98/193; other holes are not an automatic ratchet. Commercial brake interface is still unselected.')
    change(m, 'z_independent_safety_track', track)
    for i in m.items:
        if i.name.startswith('safety_track_link_') and i.origin[2] == 625:
            i.origin = (i.origin[0], i.origin[1], 365)
    shoe = fuse(box(68, -232, -104, 6, 8, 34), box(73, -241.5, -100, 4, 27, 5),
                box(90, -268, -100, 30, 34, 5).cut(box(90, -268, -101, 6.4, 30.4, 8)))
    shoe_h = [hx(64, -232, z, 3.4, 9) for z in (-98, -78)]
    shoe = m.part('E01_Maintenance_Prop_Shoe_STEEL', drill(shoe, shoe_h), 'steel', holes=shoe_h,
        note='Manual maintenance prop only: M3 edge bolts at deck-98/-78; U shoe bears on retained D4 steel pin at Z98 for deck200 / Z193 for deck295. Remove pin before Z motion; NOT automatic fall arrest.')
    m.add('maintenance_shoe', shoe, (x, 0, D), 'z')
    prior.cut_world(m, 'z_carriage', [hx(x+54, -232, D+zz, 2.5, 12) for zz in (-98, -78)])
    add_joint(m, 'maintenance_shoe', 'z_carriage', 'Steel maintenance prop, two M3 edge taps; test before servicing')
    pin = m.part('E01_Maintenance_Pin_D4x40', cyl(0, 0, 0, 2, 40, (1, 0, 0)), 'steel', 'purchased',
        note='Retained steel pin, shown at Z193. Remove and confirm sensor BEFORE powered Z travel. No printed substitution.')
    m.add('maintenance_pin', pin, (x+70, -268, 193), 'maintenance')

    # One storage column and IO; empty cell at start, one bin on the transporter.
    colpost = m.part('2020_E01_Column_Z350', v2.extrusion(20, 350, 'Z'), process='purchased')
    for i in m.items:
        if i.name.startswith('column_0_post_'):
            i.part = colpost
        if i.name.startswith('column_0_rear_standoff_') and i.origin[2] == 655:
            i.origin = (i.origin[0], i.origin[1], 355)
    ch = [hy(a, -1, z, 5.5, 5) for a in (-75, 75) for z in (20, 310)]
    cp = m.part('E01_Column_Rear_170x330', drill(box(0, 1.5, 0, 170, 3, 330), ch), holes=ch)
    change(m, 'column_0_rear_panel', cp)
    # The adjacent single-cell layout is closer than V03's IO bay. Reduce the
    # RIGHT shutter edge by12 without shifting the nest or narrowing bin access.
    # Both the sliding panel and its upper shield/header follow the new guide.
    right = next(i for i in m.items if i.name == 'io_shutter_guide_right')
    right.origin = (IO_X+113, -7, 186)
    gate = m.part('E01_IO_Inner_Shutter_238', box(-6, 0, 0, 238, 3, 104), 'guard', 'cut_panel',
                  note='Right edge shortened12 to clear adjacent storage-bin sweep; opens upward90. Actual interlocks/actuator not implemented.')
    change(m, 'io_inner_shutter', gate)
    upper = box(-6, 0, 0, 238, 3, 100)
    for a in (-125, 113):
        upper = upper.cut(box(a, 0, 96, 8, 5, 6))
    change(m, 'io_upper_fixed_shield', m.part('E01_IO_Upper_Shield_238', upper, 'guard', 'cut_panel'))
    header = fuse(box(-6, 4, 0, 248, 8, 4), box(-125, -1.5, 0, 8, 19, 4), box(113, -1.5, 0, 8, 19, 4))
    change(m, 'io_shutter_header', m.part('E01_IO_Header_248', header))
    # Flush the actual bin sliding surfaces, not cap heads under the bin.
    for name in ('cell_0_1', 'io_deck', 'carrier_tray'):
        i = next(i for i in m.items if i.name == name)
        p = i.part; s = p.shape
        holes = [(a, b) for a in (-52, 52) for b in (-50, 50)]
        if name == 'carrier_tray':
            holes += [(a, b) for a in (-44, 44) for b in (-43, 47, -32, 28)]
        for a, b in holes:
            s = s.cut(cq.Solid.makeCone(2.25, 4.5, 2.25, cq.Vector(a, b, 1.75)))
        i.part = m.part(p.name+'_E01_FlushHeads', s, p.material, p.process, p.holes,
                       p.note+' M4 90deg heads must be flush/below sliding surface; countersinks OD9.')
    spreader = m.part('E01_Bin_LoadSpreader_100x110x1p5', box(0, 0, 0, 100, 110, 1.5),
                      note='Metal insert distributes payload over the bin floor; no 1 kg creep/endurance acceptance implied.')
    m.add('bin_load_spreader', spreader, (x, -78, D+2.4), 'bin')

    # Single full-height guard around powered axes. Door latches and safety
    # chain are separate selected hardware, not certified by these clear panels.
    add_guards(m)
    drill_base(m)
    add_fasteners(m, rh, rhz, yrh)
    add_limits(m)
    # Move complete X drive package aft42, including the actual driver body.
    for i in m.items:
        if i.name.startswith(('x_rack_', 'x_motor_', 'x_hub_')) or i.name in ('x_real_motor', 'x_pinion', 'x_pinion_hub', 'limit_x_min_candidate', 'limit_x_max_candidate'):
            xx, yy, zz = i.origin
            i.origin = (xx, yy-42, zz)
    # Internal source registry only retains actual parts in this delivery.
    m.items = [Item(i.name, i.part, i.origin, i.group) for i in m.items]
    used = {i.part.name for i in m.items}
    m.parts = {k: p for k, p in m.parts.items() if k in used}
    return m


def add_guards(m):
    post = m.part('Guard_Post_E01_488', v2.extrusion(20, 488, 'Z'), process='purchased')
    cross = m.part('Guard_Cross_E01_560', v2.extrusion(20, 560, 'X'), process='purchased')
    side = m.part('Guard_Side_E01_580', v2.extrusion(20, 580, 'Y'), process='purchased')
    fh = [hz(a, b, -1, 4.5, 8) for a in (-14, 14) for b in (-14, 14)] + [hz(0, 0, -1, 5.5, 8)]
    fs = drill(box(0, 0, 0, 40, 40, 6), fh).cut(cq.Solid.makeCone(4.75, 2.75, 2, cq.Vector(0, 0, 0)))
    foot = m.part('E01_Guard_Foot_40x40', fs, holes=fh)
    for xx in (-265, 295):
        for yy in (-405, 195):
            m.add(f'guard_foot_{xx}_{yy}', foot, (xx, yy, 6))
            m.add(f'guard_post_{xx}_{yy}', post, (xx, yy, 12))
            add_joint(m, f'guard_foot_{xx}_{yy}', 'base', 'Four M4, matched base pilots; guard is not the axis load frame')
        m.add(f'guard_side_{xx}', side, (xx, -105, 500))
    for yy in (-405, 195):
        m.add(f'guard_cross_{yy}', cross, (15, yy, 500))
    for yy in (-431.5, 221.5):
        p = m.part('E01_Guard_Panel_Y'+str(yy), box(15, yy, 0, 610, 3, 520), 'guard', 'cut_panel',
                   note='PC3 cut panel; retain/hinge/interlock hardware must be selected and tested before powering.')
        m.add('guard_panel_y'+str(yy), p)
    for xx in (-291.5, 321.5):
        s = box(xx, -105, 0, 3, 650, 520)
        if xx < 0:
            s = s.cut(box(xx, 69, 190, 5, 138, 100))
        p = m.part('E01_Guard_Panel_X'+str(xx), s, 'guard', 'cut_panel')
        m.add('guard_panel_x'+str(xx), p)
    p = m.part('E01_Guard_Roof', box(15, -105, 520, 616, 656, 3), 'guard', 'cut_panel')
    m.add('guard_roof', p)


def drill_base(m):
    hh = []
    for xx in X_FEET:
        hh += [hz(xx+a, yy, -1, 4.2, 8) for a in (-8, 8) for yy in (-391, -382)]
    hh += [hz(xx, yy, -1, 4.2, 8) for xx in (-175, -75, 25, 125) for yy in (-285, -215)]
    hh += [hz(CELL_X+a, yy, -1, 5, 8) for a in (-45, 45) for yy in (20, 130)]
    hh += [hz(CELL_X+a, 75, -1, 6, 8) for a in (-75, 75)]
    hh += [hz(IO_X+a+b, yy+c, -1, 4.2, 8) for a in (-65, 65) for b in (-14, 14)
           for yy in (10, 140) for c in (-14, 14)]
    hh += [hz(xx+a, yy+b, -1, 3.3, 8) for xx in (-265, 295) for yy in (-405, 195) for a in (-14, 14) for b in (-14, 14)]
    hh += [hz(xx, yy, -1, 8.5, 8) for xx in (-240, 270) for yy in (-320, 170)]
    prior.cut_world(m, 'base', hh)


def add_fasteners(m, rh, rhz, yrh):
    b8, b10 = bolt(m, 3, 8), bolt(m, 3, 10)
    b12, b40, b50 = bolt(m, 3, 12), bolt(m, 3, 40), bolt(m, 3, 50)
    pos_y = lambda s: s.rotate((0, 0, 0), (1, 0, 0), -90)
    bp8 = m.part('M3x8_Y_ThreadMinor', pos_y(b8.shape), 'steel', 'purchased', note=b8.note)
    for yy in (-285, -215):
        for j, h in enumerate(rh):
            m.add(f'x_rail_bolt_{yy}_{j}', b10, (h[0][1], yy, 34.5))
    for off in (-45, 45):
        for j, h in enumerate(rhz):
            m.add(f'z_rail_bolt_{off}_{j}', bp8, (CELL_X+off, -244.5, 210+h[0][1]), 'x')
    for off in (-13, 13):
        for j, h in enumerate(yrh):
            m.add(f'y_rail_bolt_{off}_{j}', b8, (CELL_X+off, -125+h[0][1], CELL_Z-37), 'z')
    # All four X blocks and all four Z blocks, with recessed head positions.
    for off in (-45, 45):
        for yy in (-285, -215):
            for a in (-10, 10):
                for b in (-10, 10):
                    m.add(f'x_block_bolt_{off}_{yy}_{a}_{b}', b8, (CELL_X+off+a, yy+b, 47.9), 'x')
    for off in (-45, 45):
        for zz in (-79, -29):
            for a in (-10, 10):
                for b in (-10, 10):
                    m.add(f'z_block_bolt_{off}_{zz}_{a}_{b}', bp8, (CELL_X+off+a, -231.1, CELL_Z+zz+b), 'z')
    for off in (-13, 13):
        for a in (-7.5, 7.5):
            for b in (-8, 8):
                m.add(f'y_block_bolt_{off}_{a}_{b}', b8, (CELL_X+off+a, -196+b, CELL_Z-26), 'y')
    # Actual motor flange bolts, not just hole patterns.
    b6 = bolt(m, 3, 6)
    inv8 = m.part('M3x6_Motor_Inverted', b6.shape.rotate((0, 0, 0), (1, 0, 0), 180), 'steel', 'purchased', note=b6.note)
    inv12 = m.part('M3x12_Motor_Inverted', b12.shape.rotate((0, 0, 0), (1, 0, 0), 180), 'steel', 'purchased', note=b12.note)
    for name in ('x_motor_plate', 'y_motor_plate'):
        i = next(i for i in m.items if i.name == name)
        holes = [hz(a, b, -1, 6, 3.1) for a in (-15.5, 15.5) for b in (-15.5, 15.5)]
        i.part = m.part(i.part.name+'_Recess', drill(i.part.shape, holes), holes=[*i.part.holes, *holes], note='Underside motor screw counterbores depth2.1; M3x6 about4.1mm engagement, verify actual motor blind holes.')
    for axis, xx, yy, zz, p, group in [('x', CELL_X, -299, 84.1, inv8, 'x'),
        ('y', CELL_X+93, -196, CELL_Z-.9, inv8, 'y'), ('z', CELL_X, -268, 404.1, inv12, 'x')]:
        for a in (-15.5, 15.5):
            for b in (-15.5, 15.5):
                m.add(f'{axis}_motor_flange_bolt_{a}_{b}', p, (xx+a, yy+b, zz), group)
    for off in (-28, 28):
        for yy in (-4.5, 4.5):
            m.add(f'x_motor_module_bolt_{off}_{yy}', b40, (CELL_X+off, -299+yy, 86), 'x')
    nut_s = cq.Workplane('XY').polygon(6, 5.5*2/math.sqrt(3)).extrude(2.4).val().rotate((0, 0, 0), (0, 0, 1), 30)
    nut_s = nut_s.cut(cyl(0, 0, -1, 1.6, 5))
    nut = m.part('E01_M3_Nut', nut_s, 'steel', 'purchased')
    for yy in (-4.5, 4.5):
        m.add(f'y_motor_module_bolt_{yy}', b50, (CELL_X+121, -196+yy, CELL_Z+1), 'y')
        m.add(f'y_motor_module_nut_{yy}', nut, (CELL_X+121, -196+yy, CELL_Z-47.4), 'y')
    # Accessible steel nut bridge; washer and nut positions deliberately avoid
    # the Y-spine and rail ends, unlike the frozen V02 hole arrangement.
    b425 = bolt(m, 4, 25, 4)
    by425 = m.part('M4x25_Y_ThreadMinor', b425.shape.rotate((0, 0, 0), (1, 0, 0), 90), 'steel', 'purchased', note=b425.note)
    w = cyl(0, 0, 0, 4.5, 1).cut(cyl(0, 0, -1, 2.15, 3))
    wy = m.part('E01_M4_Washer_Y', pos_y(w), 'steel', 'purchased')
    n4 = cq.Workplane('XY').polygon(6, 7*2/math.sqrt(3)).extrude(3.2).val().rotate((0, 0, 0), (0, 0, 1), 30)
    n4 = n4.cut(cyl(0, 0, -1, 2.1, 6))
    n4y = m.part('E01_M4_Nut_Y', pos_y(n4), 'steel', 'purchased')
    for a in (-23, 23):
        for z in (-54, -22):
            m.add(f'z_bridge_bolt_{a}_{z}', by425, (CELL_X+a, -245, CELL_Z+z), 'z')
            m.add(f'z_bridge_washer_{a}_{z}', wy, (CELL_X+a, -245, CELL_Z+z), 'z')
            m.add(f'z_bridge_nut_{a}_{z}', n4y, (CELL_X+a, -228, CELL_Z+z), 'z')
    # Custom hub attachment and the visible M3 clamp bolt rotate with each pinion.
    cap20 = bolt(m, 3, 20)
    clamp = bolt(m, 3, 12)
    # Canonical hub z0 sits at the printed pinion's lower face.
    for axis, phase, origin in [('x', -math.degrees((CELL_X-RACK_START)/v3.RADIUS), (CELL_X, -299, 60)),
                                 ('y', math.degrees(46/v3.RADIUS), (CELL_X+93, -196, CELL_Z-25))]:
        for off in (-9, 9):
            s = cap20.shape.translate((off, 0, 12)).rotate((0, 0, 0), (0, 0, 1), phase)
            p = m.part(f'E01_{axis}_Hub_Bolt_{off}', s, 'steel', 'purchased', note='M3x20, minor thread envelope')
            m.add(f'{axis}_hub_bolt_{off}', p, origin, axis+'gear')
            s = nut.shape.translate((off, 0, -5.4)).rotate((0, 0, 0), (0, 0, 1), phase)
            p = m.part(f'E01_{axis}_Hub_Nut_{off}', s, 'steel', 'purchased')
            m.add(f'{axis}_hub_nut_{off}', p, origin, axis+'gear')
        # Shaft from negative X towards positive X, head outside the split collar.
        s = clamp.shape.rotate((0, 0, 0), (0, 1, 0), -90).translate((-7.1, 5, 19))
        s = s.rotate((0, 0, 0), (0, 0, 1), phase)
        p = m.part('E01_'+axis+'_Hub_Clamp_Bolt', s, 'steel', 'purchased')
        m.add(axis+'_hub_clamp_bolt', p, origin, axis+'gear')
    b8top = bolt(m, 8, 25, 8)
    for off in (-45, 45):
        m.add(f'z_top_M8_{off}', b8top, (CELL_X+off, -268, 413), 'x')
    cs = fuse(cq.Solid.makeCone(8, 3.3, 4.7), cyl(0, 0, 4.7, 3.3, 15.3))
    cs = m.part('E01_M8x20_Countersunk_ThreadMinor', cs, 'steel', 'purchased', note='M8x20 countersunk, headOD<=16, 90deg; must be recessed above X blocks')
    for off in (-45, 45):
        m.add(f'z_base_M8_{off}', cs, (CELL_X+off, -268, 43.1), 'x')


def add_limits(m):
    # Explicit interface allocations, not a fabricated safety certification.
    h = [hy(a, -4, 0, 2.2, 8) for a in (-4.75, 4.75)]
    s = drill(box(0, 0, -3.2, 20, 6.5, 6.4), h)
    p = m.part('E01_NC_Limit_Switch_CANDIDATE', s, 'purchased', 'candidate', holes=h,
        note='Small NC switch body allocation. Actual lever travel, repeatability, bracket and independent hard-limit circuit must be selected; not an implemented safety sensor.')
    for name, origin, group in [('x_min', (-178, -310, 56), 'fixed'), ('x_max', (178, -310, 56), 'fixed'),
        ('z_min', (CELL_X-80, -232, 98), 'x'), ('z_max', (CELL_X-80, -232, 292), 'x'),
        ('y_min', (CELL_X-54, -219, CELL_Z-46), 'z'), ('y_max', (CELL_X-54, -30, CELL_Z-46), 'z')]:
        m.add('limit_'+name+'_candidate', p, origin, group)


def export(m):
    for sub in ('parts', 'stl', 'viewing', 'drawings', 'previews'):
        (OUT/sub).mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name='POWERED_ONE_CELL_E01_NOT_LOAD_ACCEPTED')
    for i in m.items:
        color = (.95, .56, .12) if i.part.process == 'candidate' else v2.COLORS.get(i.part.material, (.6, .6, .6))
        assembly.add(i.located(), name=i.name, color=cq.Color(*color))
    assembly.save(str(OUT/'Powered_MVP_E01_ASSEMBLY.step'))
    # Default viewing file: flat AP203 solid part, avoiding the previous blank
    # assembly-tree import; all geometry, including three complete motors.
    compound = cq.Compound.makeCompound([s for i in m.items for s in i.located().Solids()])
    STEPControl_Writer()
    old_schema = Interface_Static.CVal_s('write.step.schema')
    old_asm = Interface_Static.IVal_s('write.step.assembly')
    try:
        if not Interface_Static.SetCVal_s('write.step.schema', 'AP203'):
            raise RuntimeError('Cannot select AP203 schema')
        if not Interface_Static.SetIVal_s('write.step.assembly', 0):
            raise RuntimeError('Cannot disable STEP assembly hierarchy')
        writer = STEPControl_Writer()
        if writer.Transfer(compound.wrapped, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError('Flat STEP transfer failed')
        if writer.Write(str(OUT/'viewing/Powered_MVP_E01_SOLIDS_AP203.step')) != IFSelect_RetDone:
            raise RuntimeError('Flat STEP write failed')
    finally:
        Interface_Static.SetCVal_s('write.step.schema', old_schema)
        Interface_Static.SetIVal_s('write.step.assembly', old_asm)
    rows = []
    for k, p in enumerate(sorted(m.parts.values(), key=lambda p: (p.process, p.name)), 1):
        code = f'E{k:03}'
        cq.exporters.export(p.shape, str(OUT/'parts'/(code+'.step')))
        b = p.shape.BoundingBox()
        row = {'code': code, 'name': p.name, 'quantity': sum(i.part.name == p.name for i in m.items),
               'material': p.material, 'process': p.process, 'solids': len(p.shape.Solids()),
               'volume_mm3': p.shape.Volume(), 'bounds_mm': v2.bbox(p.shape), 'extents_mm': [b.xlen, b.ylen, b.zlen],
               'holes': p.holes, 'note': p.note}
        if p.process == 'print':
            # Explicit flat orientation for vertical Y racks; no standing tall teeth.
            s = p.shape
            if p.name == 'Rack_M1p5_24T_Y':
                s = v3.rack()
            if p.name == 'Rack_M1p5_24T_X':
                s = v3.rack()
            bb = s.BoundingBox()
            s = s.translate((-bb.xmin, -bb.ymin, -bb.zmin))
            cq.exporters.export(s, str(OUT/'stl'/(code+'.stl')), tolerance=.03, angularTolerance=.1)
            row['print_orientation'] = 'rack back face down' if p.name.startswith('Rack_') else 'as exported; inspect support and bed contact'
        rows.append(row)
    manifest = {'version': 'E01', 'fingerprint': FINGERPRINT, 'units': 'mm', 'parts': rows,
        'instances': [{'name': i.name, 'part': i.part.name, 'origin_mm': i.origin, 'group': i.group} for i in m.items],
        'joints': m.joints, 'motor_model': 'User ZDT_X42_L48Motor.STEP, 3 complete motors',
        'axes': {'X': 'printed m1.5 rack/pinion direct motor', 'Y': 'printed m1.5 rack/pinion direct motor',
                 'Z': 'METAL TR8x2, two METAL nuts, fixed/floating bearings, 5x6 coupler'},
        'target_payload_kg': 1, 'storage_cell': [CELL_X, 65, CELL_Z], 'io_cell': [IO_X, 65, IO_Z],
        'motion_limits': {'X_mm': [IO_X, CELL_X], 'Z_deck_mm': [IO_Z, CELL_Z], 'Y_transfer_mm': [0, 143]},
        'screw_lead_mm': SCREW_LEAD, 'maintenance_pin_shown_installed': True,
        'motors_included': True, 'control_firmware_implemented': False, 'motor_torque_curve_verified': False,
        'independent_brake_selected': False, 'hardware_accepted': False, 'loaded_operation_allowed': False}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    with (OUT/'BOM.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['code', 'name', 'quantity', 'material', 'process', 'note'])
        for r in rows:
            w.writerow([r[k] for k in ('code', 'name', 'quantity', 'material', 'process', 'note')])
    print('EXPORTED E01', len(rows), 'part types,', len(m.items), 'instances', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--export', action='store_true'); args = ap.parse_args()
    model = build_model()
    if args.export:
        export(model)
    bad, _ = v2.collisions(model.items, model.allowed)
    print(json.dumps({'parts': len(model.parts), 'instances': len(model.items), 'static_collisions': bad}, indent=2), flush=True)
