"""V03.1 load-path revision. V03 sources and deliverables remain untouched.

Geometry and simple elastic screens are not hardware acceptance. Printed lift
teeth, candidate reducers, hubs and the independent catch remain unreleased.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'cad'/'v03'))
import asrs_v03 as baseline
import cadquery as cq

v2 = baseline.v2
box, cyl, fuse, drill, hz, hy, hx = baseline.box, baseline.cyl, baseline.fuse, baseline.drill, baseline.hz, baseline.hy, baseline.hx
OUT = ROOT/'model'/'V03_1'
DEPENDENCIES = [Path(__file__), *baseline.DEPENDENCIES]
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
X_SUPPORTS = (-210, -60, 90, 240, 390, 540, 750)
Z_SUPPORTS = (100, 230, 360, 490, 625)


def change(m, name, part):
    next(i for i in m.items if i.name == name).part = part


def cut_world(m, name, holes):
    """Cut receiving holes in the same world coordinates as their mating parts."""
    item = next(i for i in m.items if i.name == name)
    local = [((p[0]-item.origin[0], p[1]-item.origin[1], p[2]-item.origin[2]), axis, dia, length)
             for p, axis, dia, length in holes]
    old = item.part
    item.part = m.part(old.name+'_R1', drill(old.shape, local), old.material, old.process,
                       [*old.holes, *local], old.note)


def add_connection(m, a, b, kind, fasteners, holes=()):
    m.connections.append({'a': a, 'b': b, 'kind': kind, 'fasteners': fasteners,
                          'hole_axes_world': list(holes), 'hardware_accepted': False})


def build_model():
    m = baseline.build_model()
    m.connections = []
    x, D = m.x, m.deck

    # X: a real row of bolted feet closes the rack -> base reaction path.
    # Slots move the entire aligned rack in Y by +/-1 mm; never shim individual teeth.
    foot = fuse(box(0, -342, 6, 32, 28, 6), box(0, -331, 12, 32, 6, 69))
    for xx in (-8, 8):
        for yy in (-349, -340):
            foot = foot.cut(v2.slot_y(xx, yy, 5, 7.5, 5.5, 8))
    upright_holes = [hy(xx, -335, zz, 4.5, 8) for xx in (-8, 8) for zz in (56, 76)]
    foot = m.part('X_Rack_Bolted_Adjustable_Foot', drill(foot, upright_holes), holes=upright_holes,
                  note='Metal welded/machined L foot. Four M5 base slots (+/-1 mm Y); four M4 to rack backing. Align as ONE straight datum, lock after coupon setup.')
    back_holes = []
    base_holes = []
    for xx in X_SUPPORTS:
        name = f'x_rack_foot_{xx}'
        m.add(name, foot, (xx, 0, 0))
        bh = [hy(xx+off, -329, zz, 3.3, 8) for off in (-8, 8) for zz in (56, 76)]
        back_holes.extend(bh)
        add_connection(m, name, 'x_rack_backbone', 'bolted_face', '4x M4; backing tapped 3.3 pilot', bh)
        for a in (-8, 8):
            for yy in (-349, -340):
                base_holes.append(hz(xx+a, yy, -1, 4.2, 8))
        # A seam-straddling foot is deliberately attached to both panels.
        for panel in [i for i in m.items if i.name.startswith('base_panel_')]:
            b = panel.located().BoundingBox()
            if b.xmin < xx+16 and b.xmax > xx-16:
                add_connection(m, name, panel.name, 'bolted_seat', 'M5 into 6 mm base; screw lengths/torque to be specified')
    cut_world(m, 'x_rack_backbone', back_holes)
    for panel in [i for i in m.items if i.name.startswith('base_panel_')]:
        b = panel.located().BoundingBox()
        cut_world(m, panel.name, [h for h in base_holes if b.xmin < h[0][0] < b.xmax])

    # Z: keep the original tooth pitch plane and phase. Thicken backwards, and
    # shorten unsupported spans from 525 mm to at most 135 mm.
    baseline.remove(m, lambda i: i.name.startswith('z_rack_standoff_'))
    old = next(i for i in m.items if i.name == 'z_rack_backbone')
    rack_holes = [hx(-7, yy, j*baseline.SEGMENT_LENGTH+t, 2.5, 14)
                  for j in range(5) for t in (6*baseline.PITCH, 18*baseline.PITCH) for yy in (-11, 11)]
    mount_holes = [hy(0, -16, zz+off-85, 2.5, 8)
                   for zz in Z_SUPPORTS for off in (3, 9)]
    old.origin = (x-128, -268, 85)
    old.part = m.part('Z_Rack_Backbone_12x30', drill(box(0, 0, 0, 12, 30, 566), rack_holes+mount_holes),
                     holes=rack_holes+mount_holes,
                     note='12 mm metal backing, same rack mating face X=machine X-122. Five bolted rear supports; no printed member credited as composite stiffening.')
    sh = [hy(-46, -5, zz, 3.4, 10) for zz in (3, 9)] + [hy(37, -5, 6, 5.5, 10)]
    support = m.part('Z_Rack_Support_104x8x12', drill(box(0, 0, 0, 104, 8, 12), sh), holes=sh,
                     note='Two M3 into backing, one M5 at actual centreline of left 3030 rear slot. Five spaced brackets act together; supplier T-nut and tool access require physical check.')
    for zz in Z_SUPPORTS:
        name = f'z_rack_standoff_{zz}'
        m.add(name, support, (x-82, -287, zz), 'x')
        add_connection(m, name, 'z_rack_backbone', 'bolted_face', '2x M3, matched backing pilots')
        add_connection(m, name, 'z_post_-45', 'slot_nut_face', 'M5 at slot centreline plus actual 3030 T-nut; not solid-profile blind tapping')

    # Y: replace two disconnected blocks and the right spine spacers by real
    # saddles seated on the spine and under both the tube and the rack backing.
    baseline.remove(m, lambda i: i.name.startswith('y_rack_standoff_') or i.name.startswith('y_spine_spacer_1_'))
    saddle = fuse(box(51, 0, -40, 38, 12, 6), box(45, 0, -34, 26, 12, 5),
                  box(63, 0, -34, 6, 12, 8))
    saddle_h = [hz(xx, 0, -41, 3.3, 14) for xx in (35, 44)] + [hx(59, 0, -30, 3.4, 8)]
    saddle = m.part('Y_Rack_Tube_Saddle', drill(saddle, saddle_h), holes=saddle_h,
                    note='Metal combined support: seated on spine, tube on top, rack backing on outer ledge. M4 spine/tube attachment; M3 lateral backing clamp.')
    yh = []
    for label, yy in (('rear', -217), ('front', -25)):
        name = 'y_rack_saddle_'+label
        m.add(name, saddle, (x, yy, D), 'z')
        yh.append(hx(x+65, yy, D-30, 2.5, 6))
        add_connection(m, name, 'y_spine', 'bolted_seat', 'M4 at X+35')
        add_connection(m, name, 'tray_tube_44', 'bolted_seat', 'M4 through tube with metal compression sleeve at X+44')
        add_connection(m, name, 'y_rack_backbone', 'bolted_saddle', 'M3 lateral screw plus positive bottom seat')
    cut_world(m, 'y_rack_backbone', yh)

    # Remove the moving battery platform and its long thin lateral overhang.
    plate = next(i for i in m.items if i.name == 'y_puller_plate')
    trimmed = plate.part.shape.intersect(box(46, 0, -15, 148, 200, 25))  # local X -28..120
    plate.part = m.part('Y_Module_Base_Short', trimmed, holes=plate.part.holes,
                       note='Moving head/motor bridge only, shortened from X+256 to X+120. Power node no longer rides on this cantilever.')
    baseline.remove(m, lambda i: i.name.startswith('y_power_leg_'))

    # Y retains a dedicated local power node, but it rides Z, not the Y slider.
    # Rotate by 90 degrees: 85 mm transverse width, clear of motor/reducer sweep.
    power_origin = (x+175, -135, D-20)
    for name, dz in [('y_power_case', 0), ('y_power_lid', 50), ('y_battery_candidate', 4), ('y_esp32_candidate', 4)]:
        item = next(i for i in m.items if i.name == name)
        local_x = -26.5 if name == 'y_battery_candidate' else 43 if name == 'y_esp32_candidate' else 0
        p = item.part
        item.part = m.part(p.name+'_Y_Stationary_Rotated', p.shape.rotate((0, 0, 0), (0, 0, 1), 90), p.material, p.process,
                           note=p.note+' Y node rides on Z; requires a local flexible 143 mm Y-stroke harness.')
        item.origin = (power_origin[0], power_origin[1]+local_x, power_origin[2]+dz)
        item.group = 'z'
    tray_h = [hz(xx, yy, -1, 3.3, 6) for xx in (-25, 25) for yy in (-60, 60)]
    # Flush top heads under the case; pilot holes in the support are a separate part.
    for yy in (-76, -67):
        tray_h.extend([hz(-30, yy, -1, 4.5, 6), hz(-30, yy, 1.5, 8, 4)])
    tray = m.part('Y_Power_Tray_On_Z', drill(box(0, 0, 0, 90, 165, 4), tray_h), holes=tray_h,
                  note='Dedicated Y battery, fixed on Z platform. Two flush low-head M4 at X-30 into support; four case M4 taps. Verify real screw/head and flexible harness.')
    change(m, 'y_power_tray', tray)
    tray_i = next(i for i in m.items if i.name == 'y_power_tray')
    tray_i.origin = (power_origin[0], power_origin[1], D-24)
    tray_i.group = 'z'
    # Offset from the inherited guide mounting bores at deck-69/deck-39;
    # an edge tap at deck-66 would break into the lower guide counterbore.
    bracket_h = [hx(64, -232, zz, 4.5, 18) for zz in (-63, -53)]
    bracket_h += [hz(145, yy, -35, 3.3, 12) for yy in (-211, -202)]
    bracket = fuse(box(107.5, -232, -72, 85, 8, 24), box(145, -214, -48, 10, 36, 24))
    bp = m.part('Y_Power_Z_Support', drill(bracket, bracket_h), holes=bracket_h,
                note='Metal stepped bracket. Two M4 into carriage right edge, two flush tray M4. No Y-slider attachment; inspect edge thread and weld/machining route.')
    m.add('y_power_z_support', bp, (x, 0, D), 'z')
    cut_world(m, 'z_carriage', [hx(x+54, -232, D+zz, 3.3, 12) for zz in (-63, -53)])
    add_connection(m, 'y_power_z_support', 'z_carriage', 'bolted_face', '2x M4 edge taps, 10 mm nominal engagement')
    add_connection(m, 'y_power_z_support', 'y_power_tray', 'bolted_seat', '2x flush low-head M4; 8 mm counterbores')

    # IO: base -> flanged legs -> metal frame -> polymer nest, all mating faces
    # coincide, and screw pilots are present on both sides of each joint.
    # +/-14 keeps a standard OD10 M5 washer clear of the 20 mm post corners.
    leg_h = [hz(a, b, -1, 5.5, 8) for a in (-14, 14) for b in (-14, 14)]
    leg_h += [hz(0, 0, 174, 4.2, 12)]
    leg = m.part('IO_Flanged_Leg_BaseToFrame', drill(fuse(box(0, 0, 0, 40, 40, 6), box(0, 0, 6, 20, 20, 178)), leg_h),
                 holes=leg_h, note='Metal integral/welded flange. Bottom Z6, frame seat Z190. Four M5 to base; one M5 frame bolt into top pilot.')
    frame = fuse(box(0, 15, 0, 150, 20, 6), box(0, 115, 0, 150, 20, 6),
                 box(-65, 75, 0, 10, 150, 6), box(65, 75, 0, 10, 150, 6))
    fh = [hz(a, yy, -1, 5.5, 8) for a in (-65, 65) for yy in (10, 140)]
    fh += [hz(a, yy, -1, 3.3, 8) for a in (-52, 52) for yy in (15, 115)]
    fp = m.part('IO_Frame_Matched_Fasteners', drill(frame, fh), holes=fh,
                note='Metal frame; four M5 to leg tops, four M4 nest attachment taps at actual nest hole positions.')
    change(m, 'io_deck_frame', fp)
    io_base_h = []
    for a in (-65, 65):
        for yy in (10, 140):
            name = f'io_leg_{a}_{yy}'
            change(m, name, leg)
            next(i for i in m.items if i.name == name).origin = (-150+a, yy, 6)
            io_base_h += [hz(-150+a+off, yy+b, -1, 4.2, 8) for off in (-14, 14) for b in (-14, 14)]
            add_connection(m, name, 'base_panel_0', 'bolted_seat', '4x M5 into base')
            add_connection(m, name, 'io_deck_frame', 'bolted_seat', 'M5 into leg top, frame clearance 5.5')
    cut_world(m, 'base_panel_0', io_base_h)
    add_connection(m, 'io_deck_frame', 'io_deck', 'bolted_seat', '4x M4, matched nest holes')

    # Explicit bench anchor positions, not a claim about an unspecified bench.
    for name, xx in [('base_panel_0', -315), ('base_panel_2', 855)]:
        cut_world(m, name, [hz(xx, yy, -1, 8.5, 8) for yy in (-320, 165)])

    m.items = [baseline.Item(i.name, i.part, i.origin, i.group) for i in m.items]
    used = {i.part.name for i in m.items}
    m.parts = {k: p for k, p in m.parts.items() if k in used}
    return m


def export(m):
    """Separate exports: never overwrite a V03 model or its evidence."""
    for sub in ('parts', 'stl', 'viewing'):
        (OUT/sub).mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name='ASRS_V03_1_LoadPath_Prototype')
    for i in m.items:
        color = (.95, .56, .12) if i.part.process == 'candidate' else v2.COLORS.get(i.part.material, (.6, .6, .6))
        assembly.add(i.located(), name=i.name, color=cq.Color(*color))
    assembly.save(str(OUT/'ASRS_Modular_V03_1.step'))
    interior = cq.Compound.makeCompound([s for i in m.items if i.part.material != 'guard' for s in i.located().Solids()])
    cq.exporters.export(interior, str(OUT/'viewing'/'ASRS_V03_1_INTERIOR_VIEW.step'))
    rows = []
    for p in m.parts.values():
        cq.exporters.export(p.shape, str(OUT/'parts'/(p.name+'.step')))
        if p.process == 'print':
            cq.exporters.export(p.shape, str(OUT/'stl'/(p.name+'.stl')), tolerance=.03, angularTolerance=.10)
        b = p.shape.BoundingBox()
        rows.append({'name': p.name, 'quantity': sum(i.part.name == p.name for i in m.items), 'material': p.material,
                     'process': p.process, 'solids': len(p.shape.Solids()), 'volume_mm3': p.shape.Volume(),
                     'extents_mm': [b.xlen, b.ylen, b.zlen], 'note': p.note})
    manifest = {'version': 'V03.1', 'fingerprint': FINGERPRINT, 'units': 'mm', 'parts': rows,
                'instances': [{'name': i.name, 'part': i.part.name, 'origin_mm': i.origin, 'group': i.group} for i in m.items],
                'connections': m.connections, 'hardware_accepted': False, 'manufacturing_release_allowed': False,
                'note': 'Geometry prototype only. Candidate hubs, reducers, printed Z teeth and independent fall protection NOT accepted.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    with (OUT/'BOM.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['part', 'quantity', 'material', 'process', 'note'])
        for p in rows:
            w.writerow([p[k] for k in ('name', 'quantity', 'material', 'process', 'note')])
    print(f'EXPORTED V03.1 {len(rows)} types / {len(m.items)} instances', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--export', action='store_true')
    args = ap.parse_args()
    m = build_model()
    if args.export:
        export(m)
    bad, _ = v2.collisions(m.items, m.allowed)
    report = {'fingerprint': FINGERPRINT, 'unexpected_static_collisions': bad, 'static_pass': not bad,
              'hardware_accepted': False, 'manufacturing_release_allowed': False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'static_validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    return int(bool(bad))


if __name__ == '__main__':
    raise SystemExit(main())
