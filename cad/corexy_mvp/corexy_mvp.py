"""C03 whole-architecture redesign: fixed A/B CoreXY + moving metal Z + fork.

Reference EP V3 topology only. New load-bearing dimensions, no reuse of its
light pen carriage. Design-review geometry, NOT manufacturing/safety release.
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
OUT = ROOT/'model/CoreXY_Fork_MVP_C03'
DEPENDENCIES = [Path(__file__), *e01.DEPENDENCIES, BASE/'manifest.json', *sorted((BASE/'parts').glob('*.step'))]
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
W, REAR_A, REAR_B, FRONT = 260., -330., -285., 150.
R = 40/(2*math.pi)
INNER, OUTER, WIDTH = R-.7, R+.7, 6.
BELT_Z = {'A': 91.5, 'B': 103.5}
HOME_X, HOME_Y, SHIFT_Z = 90., -140., 85.
CELL_X, IO_X, BIN_Y = 90., -90., 158.
CELL_Z, IO_Z = 380., 293.
LIFT, APPROACH = 4., 8.
TOWER = {'z_real_motor', 'z_screw', 'z_working_nut', 'z_safety_nut', 'z_nut_bridge', 'z_safety_cage',
    'z_carriage', 'z_top_plate', 'z_fixed_bearing_housing', 'z_thrust_end_cap', 'z_bearing_hanger',
    'z_fixed_radial_bearing', 'z_thrust_abutment', 'z_shaft_collar', 'z_thrust_cross_pin',
    'z_floating_bearing', 'z_floating_bearing_cap', 'z_floating_radial_bearing', 'z_floating_pedestal',
    'z_coupling', 'z_independent_safety_track', 'z_brake_candidate', 'z_brake_link',
    'maintenance_shoe', 'maintenance_pin', 'brake_module_link'}
TOWER_PREFIXES = ('z_post_', 'z_foot_', 'z_strip_', 'z_rail_', 'z_block_', 'z_stop_',
    'z_thrust_bearing_', 'z_top_M8_', 'z_base_M8_', 'z_motor_flange_bolt_', 'z_bridge_',
    'safety_nut_key_', 'safety_track_link_')


@dataclass
class Item:
    name: str
    part: v2.Part
    origin: tuple
    group: str = 'fixed'

    def located(self, dx=0, dy=0, dz=0, door=0, bin_pose=None):
        x, y, z = self.origin
        if self.group in ('gantry', 'xy', 'lift', 'pin'):
            y += dy
        if self.group in ('xy', 'lift', 'pin'):
            x += dx
        if self.group == 'lift': z += dz
        if self.group == 'bin' and bin_pose is not None:
            x, y, z = bin_pose
        if self.group == 'door': z += 90*door
        s = self.part.shape
        if self.name in e01.ROTATING_Z:
            ax, ay = HOME_X-self.origin[0], HOME_Y-self.origin[1]
            s = s.rotate((ax, ay, 0), (ax, ay, 1), 360*dz/2)
        if self.name in ('motor_A_pulley', 'motor_B_pulley'):
            advance = dx+dy if self.name.startswith('motor_A') else -dx+dy
            s = s.rotate((0, 0, 0), (0, 0, 1), 360*advance/40)
        if self.group == 'belt':
            s = belt_shape(self.name[-1], HOME_X+dx, HOME_Y+dy)
        return s.translate((x, y, z))


class Model(v2.Model):
    def __init__(self):
        super().__init__(); self.items = []; self.parts = {}; self.joints = []

    def add(self, name, p, origin=(0, 0, 0), group='fixed'):
        if any(i.name == name for i in self.items): raise ValueError('Duplicate '+name)
        i = Item(name, p, origin, group); self.items.append(i); return i


def joint(m, a, b, note):
    m.joints.append({'a': a, 'b': b, 'purpose': note, 'strength_verified': False})


def find(m, name):
    return next(i for i in m.items if i.name == name)


def cut_world(m, name, holes):
    i = find(m, name); ox, oy, oz = i.origin
    local = [((x-ox, y-oy, z-oz), axis, d, length) for (x, y, z), axis, d, length in holes]
    p = i.part
    i.part = m.part(p.name+'_C03holes', drill(p.shape, local), p.material, p.process, [*p.holes, *local], p.note)


def source_parts():
    manifest = json.loads((BASE/'manifest.json').read_text())
    if manifest['fingerprint'] != e01.FINGERPRINT: raise RuntimeError('Stale E01 donor')
    return manifest, {r['name']: r for r in manifest['parts']}


def rail(m, width, h, length, pitch, along_x=False):
    s, holes = v2.rail_shape(width, h, length, pitch)
    s = drill(s, [hz(0, p[0][1], h-3.5, 6, 5) for p in holes])
    if along_x: s = s.rotate((0, 0, 0), (0, 0, 1), -90)
    return m.part(f'C03_MGN{width}_Rail_L{length}_'+('X' if along_x else 'Y'), s, 'steel', 'purchased',
        note=f'Vendor MGN{width} L{length}, pitch{pitch}/end10 assumed; counterbores included. Actual rail/block dimensions/ratings supplier-confirmed.')


def bolt(m, size, length, orient=None, head=3):
    p = e01.bolt(m, size, length, head)
    if orient is None: return p
    ax, ang = {'up': ((1, 0, 0), 180), 'forward': ((1, 0, 0), -90), 'backward': ((1, 0, 0), 90)}[orient]
    return m.part(p.name+'_'+orient, p.shape.rotate((0, 0, 0), ax, ang), 'steel', 'purchased', note=p.note)


def segment(a, b, width=1.4):
    dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
    return box(0, 0, 0, length+.02, width, WIDTH).rotate((0, 0, 0), (0, 0, 1), math.degrees(math.atan2(dy, dx))).translate(((a[0]+b[0])/2, (a[1]+b[1])/2, 0))


def sector(c, a, b):
    n = max(8, math.ceil(abs(b-a)/5)); angles = [math.radians(a+(b-a)*j/n) for j in range(n+1)]
    pts = [(c[0]+OUTER*math.cos(t), c[1]+OUTER*math.sin(t)) for t in angles]
    pts += [(c[0]+INNER*math.cos(t), c[1]+INNER*math.sin(t)) for t in reversed(angles)]
    return cq.Workplane('XY').polyline(pts).close().extrude(WIDTH).val()


def belt_centres(axis, y):
    if axis == 'A': return [(-W, y), (-W, REAR_A), (W+2*R, REAR_A), (W+2*R, FRONT), (W, y)]
    return [(W, y), (W, REAR_B), (-W-2*R, REAR_B), (-W-2*R, FRONT), (-W, y)]


def belt_shape(axis, x=HOME_X, y=HOME_Y):
    """Two separate OPEN belts, anchored at both ends to carriage, no fake loop."""
    if axis == 'A':
        a, b, c, d, e = belt_centres(axis, y)
        pieces = [segment((x-15, y+R), (-W, y+R)), sector(a, 90, 180),
            segment((-W-R, y), (-W-R, REAR_A)), sector(b, 180, 270),
            segment((-W, REAR_A-R), (W+2*R, REAR_A-R)), sector(c, 270, 360),
            segment((W+3*R, REAR_A), (W+3*R, FRONT)), sector(d, 0, 180),
            segment((W+R, FRONT), (W+R, y)), sector(e, 0, -90),
            segment((W, y-R), (x+15, y-R))]
    else:
        a, b, c, d, e = belt_centres(axis, y)
        pieces = [segment((x+15, y+R), (W, y+R)), sector(a, 90, 0),
            segment((W+R, y), (W+R, REAR_B)), sector(b, 0, -90),
            segment((W, REAR_B-R), (-W-2*R, REAR_B-R)), sector(c, 270, 180),
            segment((-W-3*R, REAR_B), (-W-3*R, FRONT)), sector(d, 180, 0),
            segment((-W-R, FRONT), (-W-R, y)), sector(e, 180, 270),
            segment((-W, y-R), (x-15, y-R))]
    return fuse(*pieces)


def belt_length(axis, x, y):
    rear = REAR_A if axis == 'A' else REAR_B
    # Straight tangent lengths plus 4 quarter-wraps + one half-wrap.
    return (x-15+W)+(W-x-15)+(y-rear)+(2*W+2*R)+(FRONT-rear)+(FRONT-y)+3*math.pi*R


def drive_partition(axis, x, y):
    rear = REAR_A if axis == 'A' else REAR_B
    return (x-15+W if axis == 'A' else W-x-15)+(y-rear)+math.pi*R/2


def build_model():
    m = Model(); manifest, rows = source_parts(); cache = {}
    def imported(name):
        if name not in cache:
            r = rows[name]; s = cq.importers.importStep(str(BASE/'parts'/(r['code']+'.step'))).val()
            cache[name] = v2.Part(name, s, r['material'], r['process'], r['holes'], r['note'])
        return cache[name]
    for i in manifest['instances']:
        n = i['name']
        if n not in TOWER and not n.startswith(TOWER_PREFIXES): continue
        ox, oy, oz = i['origin_mm']; p = imported(i['part']); m.parts[p.name] = p
        group = 'pin' if n == 'maintenance_pin' else 'lift' if i['group'] == 'z' else 'xy'
        m.add(n, p, (ox, oy+128, oz+SHIFT_Z), group)
    for j in manifest['joints']:
        names = {i.name for i in m.items}
        if j['a'] in names and j['b'] in names: m.joints.append(j)
    base = m.part('C03_Base_660x680x8', box(0, -60, -2, 660, 680, 8), note='Continuous metal plate, undersideZ-2/top6; fully supported bench. Anchors and supplier T-nut interfaces need physical engineering review.')
    m.add('base', base)
    # Two Y guides, four blocks: a stable two-beam gantry, not the plotter pen rail.
    yr = rail(m, 12, 8, 400, 25)
    yh = [hz(0, -190+25*j, 14, 2.5, 12) for j in range(16)]
    yh += [hz(0, yy, -1, 5.5, 27) for yy in (-175, -75, 25, 125)]
    datum = m.part('C03_Y_Datum_30x400x24', drill(box(0, 0, 0, 30, 400, 24), yh), holes=yh)
    bs, _ = v2.block_shape(27, 45.4, 3, 13, 12, 8, 20)
    yblock = m.part('C03_MGN12H_Y_Block', bs, 'steel', 'purchased')
    xr = rail(m, 12, 8, 440, 25, True)
    xblock = m.part('C03_MGN12H_X_Block', bs.rotate((0, 0, 0), (0, 0, 1), 90), 'steel', 'purchased')
    for side in (-1, 1):
        m.add(f'y_datum_{side}', datum, (side*205, -100, 6)); m.add(f'y_rail_{side}', yr, (side*205, -100, 30))
        joint(m, f'y_datum_{side}', 'base', 'Four M5, metal datum seated on continuous base')
        ph = [hz(a, b+c, -1, 3.5, 10) for a in (-10, 10) for b in (-55, 55) for c in (-10, 10)]
        ph += [hz(a, b+c, 4.8, 6.2, 4.2) for a in (-10, 10) for b in (-55, 55) for c in (-10, 10)]
        ph += [hz(a, b, -1, 4.2, 10) for a in (-10, 10) for b in (-55, 55)]
        end = m.part('C03_Gantry_EndPlate_44x160x8', drill(box(0, 0, 0, 44, 160, 8), ph), holes=ph)
        m.add(f'gantry_end_{side}', end, (side*205, HOME_Y, 43), 'gantry')
        for off in (-55, 55):
            m.add(f'y_block_{side}_{off}', yblock, (side*205, HOME_Y+off, 30), 'gantry')
            joint(m, f'gantry_end_{side}', f'y_block_{side}_{off}', '4xM3 guide attachment; actual blind depths and tool access unverified')
    for off in (-55, 55):
        s = box(0, 0, 0, 500, 40, 60).cut(box(0, 0, 4, 502, 32, 52))
        holes = [hz(-210+25*j, 0, 54, 2.5, 8) for j in range(17)]
        holes += [hz(xx, 0, -1, 3.3, 10) for xx in (-215, -195, 195, 215)]
        beam = m.part('C03_Gantry_BoxBeam_500x40x60x4', drill(s, holes), holes=holes,
            note='Metal rectangular tube60high x40deep, wall4. TWO beams separated110; actual flat rail faces and M4 end attachment must be machined/verified, not a1020 pen crossbar.')
        m.add(f'gantry_beam_{off}', beam, (0, HOME_Y+off, 51), 'gantry')
        m.add(f'x_rail_{off}', xr, (0, HOME_Y+off, 111), 'gantry')
        for side in (-1, 1): joint(m, f'gantry_beam_{off}', f'gantry_end_{side}', 'Two M4 upward through endplate into metal beam lower wall; threaded wall proof required')
        for xx in (-45, 45):
            m.add(f'x_block_{off}_{xx}', xblock, (HOME_X+xx, HOME_Y+off, 111), 'xy')
    holes = [hz(a+b, yy+c, -1, 3.5, 14) for a in (-45, 45) for b in (-10, 10) for yy in (-55, 55) for c in (-10, 10)]
    holes += [hz(a, 0, -1, 8.5, 14) for a in (-45, 45)]
    holes += [hz(a+b, yy, -1, 5, 14) for a in (-45, 45) for b in (-8, 8) for yy in (-27, 27)]
    holes += [hz(a, yy, -1, 3.3, 14) for a in (-15, 15) for yy in (-R, R)]
    s = drill(box(0, 0, 0, 180, 156, 12), holes)
    for xx in (-45, 45): s = s.cut(cq.Solid.makeCone(8.25, 4.25, 4, cq.Vector(xx, 0, 0)))
    plate = m.part('C03_XY_Tower_Plate_180x156x12', s, holes=holes,
        note='Metal tower plate, four X blocks and90mm block-centre span, double rails110 apart. Lower countersinks for3030 base bolts. CoreXY clamp receiver pilots. No printed plate substitution.')
    m.add('xy_plate', plate, (HOME_X, HOME_Y, 124), 'xy')
    # The old M8 tower base bolts need the thicker plate stack accommodated.
    for i in m.items:
        if i.name.startswith('z_base_M8_'): i.origin = (i.origin[0], i.origin[1], 124.1)
    joint(m, 'z_post_-45', 'xy_plate', 'Metal3030 seated on12mm XY plate; M8 countersunk stack must be length-selected')
    joint(m, 'z_post_45', 'xy_plate', 'Metal3030 seated on12mm XY plate; M8 countersunk stack must be length-selected')
    joint(m, 'z_floating_pedestal', 'xy_plate', 'Lower screw support seated on XY plate, not on belt')
    for off in (-55, 55):
        for xx in (-45, 45): joint(m, 'xy_plate', f'x_block_{off}_{xx}', '4xM3 each long block, under-plate stack and actual screw length review')
    # Fork root seats against lift plate front; holes avoid guide bores and
    # provide clearance/access to the existing nut-bridge nuts.
    s = fuse(box(0, 44, -76, 130, 8, 76), box(-28, 130.5, -8, 18, 165, 8), box(28, 130.5, -8, 18, 165, 8))
    fh = [hy(a, 39, zz, 4.5, 10) for a in (-45, 45) for zz in (-54, -12)]
    fh += [hy(a, 39, zz, 10, 10) for a in (-23, 23) for zz in (-54, -22)]
    fork = m.part('C03_Welded_Steel_Fork_2x18x8_L165', drill(s, fh), 'steel', holes=fh,
        note='Steel welded fork: two18wide x8 thick fingers, centres56 apart, reach165 from rootY48 to213. Tips stop2mm before bin-back stop when inserted. Root130x8x76 atY40..48. M4 mounting, bridge-nut tool reliefsØ10. Weld, stiffness and loaded seating must be verified.')
    m.add('fork', fork, (HOME_X, HOME_Y, CELL_Z), 'lift')
    cut_world(m, 'z_carriage', [hy(HOME_X+a, HOME_Y+31, CELL_Z+zz, 3.3, 10) for a in (-45, 45) for zz in (-54, -12)])
    for a in (-45, 45):
        for zz in (-54, -12): m.add(f'fork_bolt_{a}_{zz}', bolt(m, 4, 16, 'forward', 4), (HOME_X+a, HOME_Y+48, CELL_Z+zz), 'lift')
    joint(m, 'fork', 'z_carriage', 'Four M4x16 into metal Z plate; verify thread depth and weld/root stress')
    # New plain full-size bin, no tow eye, servo, drop-pin or release head.
    bin_shape = box(0, 0, 0, 110, 120, 60).cut(box(0, 0, 2.4, 105.2, 115.2, 60))
    bp = m.part('C03_Bin_110x120x60_ForkBase', bin_shape, 'PETG', 'print',
        note='Full size bin, no tow eye. Bottom sits on two outer shelf rails or two inner forks. Do not infer1kg creep acceptance from geometry; print and load-test with internal metal spreader.')
    m.add('bin', bp, (HOME_X, HOME_Y+155, CELL_Z), 'bin')
    insert = m.part('C03_Bin_Metal_Insert_100x110x1p5', box(0, 0, 2.4, 100, 110, 1.5), note='Loose metal payload spreader inside bin; mass/creep tests still required.')
    m.add('bin_insert', insert, (HOME_X, HOME_Y+155, CELL_Z), 'bin')
    add_cells(m)
    # Bring only IO enclosure, NOT the old solid nest, legs, actuator or tray.
    for i in manifest['instances']:
        n = i['name']
        if not n.startswith('io_') or any(t in n for t in ('deck', 'leg_', 'back_stop', 'presence_sensor')): continue
        p = imported(i['part']); m.parts[p.name] = p
        ox, oy, oz = i['origin_mm']
        m.add(n, p, (ox, oy+93, oz+IO_Z-200), 'door' if i['group'] == 'io_shutter' else 'fixed')
    gate = find(m, 'io_inner_shutter')
    gate.part = m.part('C03_IO_Fork_Clearance_Shutter', box(-6,0,-14,238,3,118), 'guard', 'cut_panel',
        note='Closed loweredge=IOlevel-20, top=IOlevel+98;90mm lift leaves6mm above IOloaded bin. Lowerextension closes fork underpass while doorclosed. Actual clearance/interlocks must be tested.')
    low = find(m, 'io_lower_fixed_shield')
    low.origin = (low.origin[0],low.origin[1],IO_Z-28)
    for i in m.items:
        if i.name.startswith('io_tunnel_'):
            p = i.part
            if 'horizontal' in i.name: s = box(0, 0, 0, 153.5, 138, 3)
            else: s = box(0, 0, 0, 153.5, 3, 106)
            i.part = m.part('C03_'+p.name, s, p.material, p.process, note='Extended human-access tunnel to new outer enclosure; actual doors/interlocks/edge retention unimplemented.')
            i.origin = (-253.25, i.origin[1], i.origin[2])
    if any(i.name == 'io_external_reference_tag' for i in m.items):
        i = find(m, 'io_external_reference_tag'); i.origin = (-333.2, i.origin[1], i.origin[2])
    add_corexy(m, imported(rows_motor_name(manifest, 'x_real_motor')))
    add_guard(m)
    add_fasteners_limits(m)
    # Match foot/datums to real base receiving pilots; not a blank plate with
    # unsupported screws. Full anchor sizing and countersink process still pending.
    receiving=[]
    for i in m.items:
        if i.group!='fixed' or i.name=='base':continue
        ox,oy,oz=i.origin
        if abs(oz-6)>1e-6:continue
        for (xx,yy,zz),axis,d,length in i.part.holes:
            if tuple(axis)==(0,0,1) and zz<0 and d in (3.4,4.5,5.5):
                receiving.append(hz(ox+xx,oy+yy,-3,{3.4:2.5,4.5:3.3,5.5:4.2}[d],10))
        if i.name.startswith(('cell_post_','io_post_','guard_post_')):receiving.append(hz(ox,oy,-3,5.5,10))
    receiving += [hz(xx,yy,-3,8.5,10) for xx in (-310,310) for yy in (-350,230)]
    cut_world(m,'base',receiving)
    used = {i.part.name for i in m.items}; m.parts = {n: p for n, p in m.parts.items() if n in used}
    names = {i.name for i in m.items}
    m.joints = [j for j in m.joints if j['a'] in names and j['b'] in names]
    return m


def rows_motor_name(manifest, instance):
    return next(i['part'] for i in manifest['instances'] if i['name'] == instance)


def add_cells(m):
    for label, xx, level in [('cell', CELL_X, CELL_Z), ('io', IO_X, IO_Z)]:
        rail_part = m.part('C03_Cell_Outer_Rail_18x120x8', box(0, 0, 0, 18, 120, 8),
            holes=[], note='Two outer METAL supports, centreX+/-50. Inner edgesX+/-41 leave fork outeredgesX+/-37 clear by4mm. Bin nominal underside at support top.')
        post = m.part('C03_Cell_Post_'+label, v2.extrusion(20, level-22, 'Z'), process='purchased')
        bracket_h = [hz(25, 0, -1, 5.5, 10)]
        bracket = m.part('C03_Cell_Seat_Bracket_42x20x8', drill(box(12, 0, 0, 42, 20, 8), bracket_h), holes=bracket_h,
            note='Metal bracket from rail innerX41 to postX83, keeps IO door clear; receivingM5 atpostX75. Rail attachment needs actual flathead/pilot detail; no printed load path.')
        for side in (-1, 1):
            m.add(f'{label}_rail_{side}', rail_part, (xx+side*50, BIN_Y, level-8))
            for end in (-55, 55):
                m.add(f'{label}_post_{side}_{end}', post, (xx+side*75, BIN_Y+end, 6))
                shape = bracket if side == 1 else m.part('C03_Cell_Seat_Bracket_Left', bracket.shape.rotate((0,0,0),(0,0,1),180), holes=bracket.holes, note=bracket.note)
                m.add(f'{label}_bracket_{side}_{end}', shape, (xx+side*50, BIN_Y+end, level-16))
                joint(m, f'{label}_bracket_{side}_{end}', f'{label}_post_{side}_{end}', 'M5 top receiver, real profile end-tap and head geometry review')
                joint(m, f'{label}_rail_{side}', f'{label}_bracket_{side}_{end}', 'Outer support rail seated on metal bracket, positive fastening not complete')
                joint(m, f'{label}_post_{side}_{end}', 'base', 'Metal post end seated onbase, foot/anchors must be selected')
        stop = m.part('C03_Cell_Back_Stop_120x8x10', box(0, 0, 0, 120, 8, 10), 'PETG', 'print', note='Bin locating stop, not primary vertical support; mounting pilots and retention require final vendor/fit review.')
        m.add(f'{label}_back_stop', stop, (xx, BIN_Y+64, level))


def metal_pulley(m, drive=False):
    s = fuse(cyl(0, 0, 0, 9, 1.5), cyl(0, 0, 1.5, INNER-.12, 6), cyl(0, 0, 7.5, 9, 1.5))
    if drive:
        s = s.fuse(cyl(0, 0, -6, 8, 6)).cut(cyl(0, 0, -7, 2.55, 18))
    else: s = s.cut(cyl(0, 0, -1, 5, 11))
    return m.part('C03_GT2_20T_'+('LowerHub_D5' if drive else 'Idler_TwinMR105'), s, 'purchased', 'candidate',
        note='Purchased metal GT2/20T/6mm allocation, NOT a tooth-manufacturing model. '+
        ('Lower hub clamp/bore5/axial retention and engagement supplier-verified before machining. No printed substitute.' if drive else 'TwinMR105 bearing space, actual vendor shoulder, inner-ring spacer and retention required.'))


def add_corexy(m, motor_down):
    # Motors both faceUP atZ78; same shaft datum, drive pulleys at different
    # heights using a LOWER hub. RearY separation avoids a tall support in motor.
    up = motor_down.shape.rotate((0, 0, 0), (1, 0, 0), 180)
    motor = v2.Part('ZDT_RealMotor_C03_AB_Up', up, 'purchased', 'purchased', [], 'Two complete user24-solid ZDT motors, both fixed. FaceUP Z78, shaft tip~102. A/B coordination required; no electrical assumptions.')
    m.parts[motor.name] = motor
    for axis, xx, yy in [('A', -W, REAR_A), ('B', W, REAR_B)]:
        m.add('motor_'+axis, motor, (xx, yy, 78))
        s = fuse(box(0, 0, 0, 76, 76, 6), box(-32, 0, 6, 8, 64, 66), box(32, 0, 6, 8, 64, 66), box(0, 0, 72, 76, 64, 4))
        h = [hz(a, b, -1, 5.5, 8) for a in (-28, 28) for b in (-26, 26)]
        h += [hz(a, b, 71, 3.5, 7) for a in (-15.5, 15.5) for b in (-15.5, 15.5)] + [hz(0, 0, 71, 23, 7)]
        p = m.part('C03_AB_Metal_Motor_Stand', drill(s, h), holes=h, note='Fixed metal standZ6..82, motor face seats underplateZ78. Both same flange height, shafttip~102; lower-hub pulleys stagger12mm. UpperB hub engagement~6mm only, supplier clamp proof mandatory.')
        m.add('motor_stand_'+axis, p, (xx, yy, 6)); joint(m, 'motor_stand_'+axis, 'base', 'Four M5 stand bolts, full base receiving pilots need final hardware selection')
        m.add('motor_'+axis+'_pulley', metal_pulley(m, True), (xx, yy, BELT_Z[axis]-1.5))
        for a in (-15.5, 15.5):
            for b in (-15.5, 15.5): m.add(f'motor_{axis}_flange_{a}_{b}', bolt(m, 3, 8), (xx+a, yy+b, 82))
    bearing = m.part('C03_MR105ZZ_5x10x4', cyl(0,0,0,5,4).cut(cyl(0,0,-1,2.55,6)), 'steel', 'purchased')
    for axis in ('A', 'B'):
        centres = belt_centres(axis, HOME_Y)
        for k, (xx, yy) in enumerate(centres):
            if k == 1: continue  # drive pulley, not an idler
            group = 'gantry' if k in (0,4) else 'fixed'
            base_z = BELT_Z[axis]-1.5
            n = f'idler_{axis}_{k}'
            m.add(n, metal_pulley(m), (xx, yy, base_z), group)
            for j in (0, 1): m.add(n+f'_bearing_{j}', bearing, (xx, yy, base_z+4*j), group)
            # Small diameter stem passes the other belt layer without engulfing
            # it. Full support below is a separate metal bracket, not a floating axle.
            stem = cyl(0,0,0,3,base_z-80).cut(cyl(0,0,-1,2.55,base_z-78))
            if group == 'fixed' or axis == 'A':
                m.add(n+'_stem', m.part('C03_Idler_Stem_'+axis, stem, 'steel'), (xx,yy,80), group)
            shoulder = fuse(cyl(0,0,-8,1.95,8),cyl(0,0,0,2.5,base_z-80+9),cyl(0,0,base_z-80+9,4.5,3))
            if group == 'fixed':
                m.add(n+'_axle', m.part('C03_Idler_Shoulder_'+axis, shoulder, 'steel', 'candidate', note='D5 shoulder plusM5 threaded minor envelope. Vendor axle/washer/inner-ring stack and retention must replace allocation before fabrication.'), (xx,yy,80), group)
            elif axis == 'A':
                shoulder = fuse(cyl(0,0,-8,1.95,8),cyl(0,0,0,2.5,31),cyl(0,0,31,4.5,3))
                m.add(n+'_axle',m.part('C03_Gantry_Common_Shoulder_Axle',shoulder,'steel','candidate',note='One D5 shoulder31 axle carries BOTH A/B idlers, not overlapping separate axles. Actual shoulder/preload/retention supplier-selected.'),(xx,yy,80),group)
                for tag,z,height in [('middle',98,4),('top',110,1)]:
                    washer=cyl(0,0,0,4,height).cut(cyl(0,0,-1,2.55,height+2))
                    m.add(n+'_'+tag,m.part('C03_Idler_InnerSpacer_'+tag,washer,'steel'),(xx,yy,z),group)
            if group == 'fixed':
                # Stand below all belts, feet clear of the nearest motor body.
                support = fuse(box(0, 0, 0, 18, 12, 6), box(0, 0, 6, 10, 10, 68))
                h = [hz(a,b,-1,3.4,8) for a in (-6,6) for b in (-3,3)] + [hz(0,0,60,4.2,16)]
                p = m.part('C03_Fixed_Idler_Stand', drill(support,h), holes=h,
                    note='Metal floor stand toZ80, upperthinD6 stem sets pulley height. FourM3 foot pilots. Needs slotted foot/top receiver, tension screw and locking hardware final detail. Working belt tension NOT selected.')
                m.add(n+'_stand', p, (xx,yy,6)); joint(m,n+'_stand','base','Four M3 locking mounts; tension travel and positive stop not yet fully detailed')
            else:
                side = -1 if xx < 0 else 1
                support = fuse(box(-side*30,0,0,80,20,8), box(-side*55,0,-21,20,20,21))
                h = [hz(0,0,-1,4.2,10)] + [hz(-side*55,b,-22,3.3,31) for b in (-5,5)]
                p = m.part('C03_Gantry_Idler_Arm_'+str(side),drill(support,h),holes=h,
                    note='Metal arm from gantry endplateZ51 to top80. Two stacked idler heights, stem widths avoid other belt. A/B share sidearm, load and alignment need measured proof.')
                # One physical arm for both layers, not overlapping duplicates.
                arm_name = f'gantry_idler_arm_{side}'
                if not any(i.name == arm_name for i in m.items):
                    m.add(arm_name,p,(xx,yy,72),'gantry'); joint(m,arm_name,f'gantry_end_{side}','TwoM4 into gantryend receiver; metal stepped arm')
    for axis in ('A', 'B'):
        p = m.part('C03_CoreXY_Open_Belt_'+axis, belt_shape(axis), 'rubber', 'purchased',
            note='OPEN GT2/6mm belt, both ends fixed on XY carriage; opposite-layer independent belt. Path evolves withY, no false rigid closedloop. Cut length includes actual clamp engagement/tension allowance; supplier strength/stiffness unverified.')
        m.add('belt_'+axis,p,(0,0,BELT_Z[axis]),'belt')
        for end in (-1,1):
            xx = HOME_X+end*15
            yy = HOME_Y+(R if (axis=='A' and end==-1) or (axis=='B' and end==1) else -R)
            # Suspension bolt is behind belt, not piercing load-carrying strand.
            h = [hz(0,0,-1,3.4,34)]
            block = box(0,0,0,12,6,124-(BELT_Z[axis]-2))
            # Cable/timing teeth clamp pocket faces the correct tangent line.
            block = block.cut(box(0,0,1.8,14,1.6,6.4))
            p = m.part('C03_Belt_Clamp_Column_'+axis,drill(block,h),holes=h,
                note='Metal open-belt end clamp allocation suspended from XYplate. Real GT2 mating jaw/teeth, adjuster/locking and pull-out proof pending; no friction-only safety claim.')
            n=f'clamp_{axis}_{end}'; m.add(n,p,(xx,yy,BELT_Z[axis]-2),'xy')
            m.allow(n,'belt_'+axis,'Intentional terminal belt-clamp contact, tooth form/compression/pullout not accepted')
            joint(m,n,'xy_plate','Metal clamp top seats on XYplate underside; final tooth jaw and threaded adjuster incomplete')


def add_guard(m):
    post = m.part('C03_Guard_2020_L620',v2.extrusion(20,620,'Z'),process='purchased')
    cross = m.part('C03_Guard_2020_X610',v2.extrusion(20,610,'X'),process='purchased')
    side = m.part('C03_Guard_2020_Y615',v2.extrusion(20,615,'Y'),process='purchased')
    for xx in (-315,315):
        for yy in (-385,250):m.add(f'guard_post_{xx}_{yy}',post,(xx,yy,6))
        m.add(f'guard_side_{xx}',side,(xx,-67.5,626))
    for yy in (-385,250):m.add(f'guard_cross_{yy}',cross,(0,yy,626))
    for xx in (-331.5,331.5):
        s=box(xx,-60,-2,3,680,648)
        if xx<0:s=s.cut(box(xx,162,IO_Z-10,5,138,100))
        m.add(f'guard_panel_x{xx}',m.part('C03_Guard_PC_X'+str(xx),s,'guard','cut_panel'))
    for yy in (-401.5,281.5):m.add(f'guard_panel_y{yy}',m.part('C03_Guard_PC_Y'+str(yy),box(0,yy,-2,660,3,648),'guard','cut_panel'))
    m.add('guard_roof',m.part('C03_Guard_PC_Roof',box(0,-60,646,666,686,3),'guard','cut_panel'))


def add_fasteners_limits(m):
    # Explicit rail and block fasteners; no claim every production screw exists.
    for side in (-1,1):
        for j in range(16):m.add(f'y_rail_bolt_{side}_{j}',bolt(m,3,10),(side*205,-290+25*j,34.5))
        for off in (-55,55):
            for a in (-10,10):
                for b in (-10,10):m.add(f'y_block_bolt_{side}_{off}_{a}_{b}',bolt(m,3,8),(side*205+a,HOME_Y+off+b,47.9),'gantry')
    for off in (-55,55):
        for j in range(17):m.add(f'x_rail_bolt_{off}_{j}',bolt(m,3,10),(-210+25*j,HOME_Y+off,115.5),'gantry')
        for xx in (-45,45):
            for a in (-10,10):
                for b in (-10,10):m.add(f'x_block_bolt_{off}_{xx}_{a}_{b}',bolt(m,3,16),(HOME_X+xx+a,HOME_Y+off+b,136),'xy')
    p=m.part('C03_NC_Limit_CANDIDATE',box(0,0,0,20,6.5,6.4),'purchased','candidate',note='NC switch allocation only; actual bracket/trigger/overtravel/wiring and independent hard limits not designed.')
    for n,o,g in [('x_min',(-172,HOME_Y-75,140),'gantry'),('x_max',(172,HOME_Y-75,140),'gantry'),
        ('y_min',(-290,-235,55),'fixed'),('y_max',(-290,80,55),'fixed'),
        ('z_min',(HOME_X-80,HOME_Y+36,175),'xy'),('z_max',(HOME_X-80,HOME_Y+36,405),'xy')]:m.add('limit_'+n,p,o,g)


def export(m):
    for sub in ('parts','stl','viewing','drawings','previews'):(OUT/sub).mkdir(parents=True,exist_ok=True)
    asm=cq.Assembly(name='COREXY_FORK_C03_NOT_LOAD_ACCEPTED')
    for i in m.items:
        color=(.95,.56,.12) if i.part.process=='candidate' else v2.COLORS.get(i.part.material,(.6,.6,.6))
        asm.add(i.located(),name=i.name,color=cq.Color(*color))
    asm.save(str(OUT/'CoreXY_Fork_C03_ASSEMBLY.step'))
    comp=cq.Compound.makeCompound([s for i in m.items for s in i.located().Solids()]);STEPControl_Writer()
    schema=Interface_Static.CVal_s('write.step.schema');mode=Interface_Static.IVal_s('write.step.assembly')
    try:
        if not Interface_Static.SetCVal_s('write.step.schema','AP203') or not Interface_Static.SetIVal_s('write.step.assembly',0):raise RuntimeError('flatSTEP writer unavailable')
        w=STEPControl_Writer()
        if w.Transfer(comp.wrapped,STEPControl_AsIs)!=IFSelect_RetDone:raise RuntimeError('STEP transfer')
        if w.Write(str(OUT/'viewing/CoreXY_Fork_C03_SOLIDS_AP203.step'))!=IFSelect_RetDone:raise RuntimeError('STEP write')
    finally:
        Interface_Static.SetCVal_s('write.step.schema',schema);Interface_Static.SetIVal_s('write.step.assembly',mode)
    rows=[]
    for k,p in enumerate(sorted(m.parts.values(),key=lambda p:(p.process,p.name)),1):
        code=f'C{k:03}';b=p.shape.BoundingBox();cq.exporters.export(p.shape,str(OUT/'parts'/(code+'.step')))
        r={'code':code,'name':p.name,'quantity':sum(i.part.name==p.name for i in m.items),'material':p.material,'process':p.process,
           'solids':len(p.shape.Solids()),'volume_mm3':p.shape.Volume(),'bounds_mm':v2.bbox(p.shape),'extents_mm':[b.xlen,b.ylen,b.zlen],'holes':p.holes,'note':p.note}
        if p.process=='print':cq.exporters.export(p.shape.translate((-b.xmin,-b.ymin,-b.zmin)),str(OUT/'stl'/(code+'.stl')),tolerance=.03,angularTolerance=.1)
        rows.append(r)
    manifest={'version':'C03','fingerprint':FINGERPRINT,'units':'mm','parts':rows,
        'instances':[{'name':i.name,'part':i.part.name,'origin_mm':i.origin,'group':i.group} for i in m.items],
        'joints':m.joints,'allowed_contacts':[{'a':a,'b':b,'reason':reason} for (a,b),reason in m.allowed.items()],
        'architecture':'Fixed two-motor CoreXY base + travelling metal TR8x2 Z tower + rigid fork, slotted support cells',
        'motor_quantity':3,'AB_fixed':True,'independent_Y_pusher':False,'payload_target_kg':1,'screw_lead_mm':2,
        'home_xy_mm':[HOME_X,HOME_Y],'transfer_mm':143,'X_centres_mm':[-90,90],
        'cell': [CELL_X,BIN_Y,CELL_Z],'io':[IO_X,BIN_Y,IO_Z],'fork_approach_below_mm':APPROACH,'fork_lift_above_mm':LIFT,
        'base_mm':[660,680,8],'belt_layers_bottom_mm':BELT_Z,'belt_pitch_mm':2,'pulley_teeth':20,
        'kinematics':'A=dx+dy; B=-dx+dy; dx=(A-B)/2; dy=(A+B)/2; advance40mm/rev. Actual wiring sign must be bench verified.',
        'hardware_accepted':False,'loaded_operation_allowed':False,'machining_release_allowed':False,
        'automatic_brake_selected':False,'control_firmware_implemented':False,'maintenance_pin_shown_installed':True}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    with (OUT/'BOM.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['code','name','quantity','material','process','note'],extrasaction='ignore');w.writeheader();w.writerows(rows)
    print('EXPORTED C03',len(rows),'types',len(m.items),'instances',flush=True)


if __name__=='__main__':
    m=build_model();bad,accepted=v2.collisions(m.items,m.allowed)
    print(json.dumps({'static':bad,'accepted':accepted,'types':len(m.parts),'instances':len(m.items)},indent=2),flush=True)
