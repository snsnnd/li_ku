"""E01 discrete geometry/mesh/sizing checks, explicitly not hardware acceptance."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import cadquery as cq
import numpy as np
import trimesh

from powered_mvp import (OUT, ROOT, FINGERPRINT, build_model, export, v2, v3,
                         Item, CELL_X, CELL_Z, IO_X, IO_Z, cyl, box, fuse, hz, drill)
sys.path.insert(0, str(ROOT/'cad/v03_1'))
from validate_v03_1 import mating_area


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def supports(m):
    shapes = {i.name: i.located() for i in m.items}
    rows = []
    for j in m.joints:
        a, b = shapes[j['a']], shapes[j['b']]
        gap = a.distance(b)
        area = mating_area(a, b) if gap < 1e-5 else 0
        rows.append({**j, 'gap_mm': gap, 'opposed_planar_mating_area_mm2': area,
                     'geometric_seat_pass': gap < 1e-5 and area > 2})
    return rows


def poses():
    result = []
    lift = 7*(1-math.cos(math.radians(165)))
    for xx, zz, io in [(CELL_X, CELL_Z, 0), (IO_X, IO_Z, 1)]:
        for j in range(14):
            q = 143*j/13
            result.append(('transfer', xx-CELL_X, zz-CELL_Z, q, 0, None, io))
            result.append(('released_withdraw', xx-CELL_X, zz-CELL_Z, q, lift, 143, io))
        for q in (0, 143):
            for angle in (0, 45, 90, 135, 165):
                result.append(('latch', xx-CELL_X, zz-CELL_Z, q, 7*(1-math.cos(math.radians(angle))), None, io))
    for zz in (IO_Z, CELL_Z):
        for j in range(19):
            result.append(('X_traverse', IO_X-CELL_X+10*j, zz-CELL_Z, 0, 0, 0, 0))
    for xx in (IO_X, CELL_X):
        for j in range(20):
            result.append(('Z_traverse', xx-CELL_X, IO_Z-CELL_Z+5*j, 0, 0, 0, 0))
    for j in range(11):
        result.append(('IO_shutter', IO_X-CELL_X, IO_Z-CELL_Z, 0, 0, 0, j/10))
    return result


def motion(m):
    items = []
    for i in m.items:
        if i.name == 'maintenance_pin':
            continue
        p = i.part
        if p.name.startswith('ZDT_RealMotor'):
            # Conservative complete-body box including rear driver/connectors;
            # invert about X, same orientation as all three actual E01 motors.
            shape = fuse(box(1.325, -10.45, -59, 44.65, 62.9, 59),
                         cyl(0, 0, 0, 11, 2), cyl(0, 0, 2, 2.5, 22))
            shape = drill(shape, [hz(a, b, -6, 2.5, 8) for a in (-15.5, 15.5) for b in (-15.5, 15.5)])
            shape = shape.rotate((0, 0, 0), (1, 0, 0), 180)
            p = replace(p, shape=shape)
        items.append(Item(i.name, p, i.origin, i.group))
    failures, tests = [], 0
    start = time.monotonic()
    for n, pose in enumerate(poses(), 1):
        phase, dx, dz, q, lift, bq, door = pose
        located = [(i, i.located(dx, dz, q, lift, bq, door)) for i in items]
        located = [(i, s, v2.bbox(s)) for i, s in located]
        bad = []
        for k, (a, sa, ba) in enumerate(located):
            for b, sb, bb in located[k+1:]:
                if a.group == b.group or not v2.overlaps(ba, bb):
                    continue
                tests += 1
                vol = sa.intersect(sb).Volume()
                if vol > .02:
                    bad.append({'a': a.name, 'b': b.name, 'volume_mm3': round(vol, 5)})
        if bad:
            failures.append({'pose': pose, 'collisions': bad})
        if n % 20 == 0:
            print(f'MOTION {n}/{len(poses())} failures={len(failures)} seconds={time.monotonic()-start:.1f}', flush=True)
    return {'pose_count': len(poses()), 'boolean_pair_tests': tests, 'failures': failures,
            'sampled_geometry_pass': not failures, 'continuous_collision_detection': False,
            'maintenance_pin_removed': True, 'X_step_mm': 10, 'Z_step_mm': 5,
            'Y_step_mm': 11, 'IO_shutter_samples': 11,
            'method': 'Exact teeth/hubs/fasteners; conservative complete motor body box with flange pilots. Same rigid-group pairs checked at static pose; discrete samples only.'}


def engineering(m):
    rows = []
    density = {'aluminum': 2.7e-6, 'steel': 7.85e-6, 'PETG': 1.27e-6,
               'POM': 1.41e-6, 'purchased': 7.85e-6, 'safety': 7.85e-6,
               'guard': 1.20e-6, 'rubber': 1.2e-6}
    for i in m.items:
        p = i.part
        kg, method = p.shape.Volume()*density[p.material], 'CAD volume x assumed density'
        if p.name.startswith('ZDT_RealMotor'):
            kg, method = .5, 'ASSUMED complete motor+driver; weigh actual motor'
        elif p.name.startswith(('Guard_', '2020_')):
            kg, method = max(p.shape.BoundingBox().xlen, p.shape.BoundingBox().ylen, p.shape.BoundingBox().zlen)*.0006, 'ASSUMED 2020 0.60kg/m'
        elif p.name.startswith('3030_'):
            kg, method = .35, 'ASSUMED 3030 1kg/m x350mm'
        rows.append({'name': i.name, 'group': i.group, 'kg': kg, 'method': method})
    zg = {'z', 'y', 'ygear', 'pin', 'bin', 'roller', 'crank', 'spring'}
    yg = {'y', 'ygear', 'pin', 'bin', 'roller', 'crank', 'spring'}
    masses = {'X': sum(r['kg'] for r in rows if r['group'] not in ('fixed', 'io_shutter', 'maintenance'))+1+.9,
              'Z': sum(r['kg'] for r in rows if r['group'] in zg)+1+.45,
              'Y': sum(r['kg'] for r in rows if r['group'] in yg)+1+.2}
    targets = []
    for axis, speed, accel, friction, drag, eta in [('X', 10, 30, .03, 4, .8), ('Y', 4, 20, .35, 4, .8), ('Z', 2, 10, 0, 8, .25)]:
        kg = masses[axis]
        force = kg*accel/1000 + friction*kg*9.80665 + drag + (kg*9.80665 if axis == 'Z' else 0)
        arm = .002/(2*math.pi) if axis == 'Z' else .015
        targets.append({'axis': axis, 'moving_mass_with_1kg_payload_and_allowance_kg': kg,
                        'candidate_initial_speed_mm_s': speed, 'candidate_accel_mm_s2': accel,
                        'force_N': force, 'assumed_efficiency': eta,
                        'required_motor_torque_SF2_Nm': 2*force*arm/eta,
                        'motor_rpm': 60*speed/(2 if axis == 'Z' else 2*math.pi*15),
                        'motor_performance_verified': False})
    fz = next(t['force_N'] for t in targets if t['axis'] == 'Z')
    return {'fingerprint': FINGERPRINT, 'target_payload_kg': 1, 'mass_breakdown': rows,
            'motor_targets': targets,
            'screw_axial_screen': {'assumed_root_diameter_mm': 5.5, 'unsupported_length_mm': 258,
                'steel_E_MPa': 200000, 'load_SF2_N': 2*fz,
                'ideal_pin_pin_Euler_N': math.pi**2*200000*(math.pi*5.5**4/64)/258**2,
                'axial_stress_SF2_MPa': 2*fz/(math.pi*5.5**2/4),
                'note': 'Conservative compression screen only; no thread, pin-hole, fatigue or bearing/catch rating acceptance.'},
            'self_locking_claimed': False, 'hardware_accepted': False, 'loaded_operation_allowed': False,
            'blockers': ['Actual motor torque-speed/current/voltage/temperature and measured masses',
                         'Vendor screw/nut accuracy, journal fits, thrust preload and cross-pin/collar proof',
                         'Independent automatic brake not selected: maintenance pin and second nut are NOT automatic fall arrest',
                         '5x6 coupling and custom clamp hubs torque/axial-retention acceptance',
                         'Fastener engagement, assembly tools, frame/bench anchors and actual rail ratings',
                         'Printed XY teeth, bin creep/endurance, full-stroke harness, E-stop/door/limits and firmware']}


def exports_check():
    manifest = json.loads((OUT/'manifest.json').read_text())
    mesh_rows = []
    for p in manifest['parts']:
        if p['process'] != 'print':
            continue
        path = OUT/'stl'/(p['code']+'.stl')
        mesh = trimesh.load_mesh(path, process=True)
        ext = mesh.extents.tolist()
        mesh_rows.append({'code': p['code'], 'name': p['name'], 'sha256': sha(path),
                          'watertight': bool(mesh.is_watertight), 'winding_consistent': bool(mesh.is_winding_consistent),
                          'bodies': mesh.body_count, 'extents_mm': ext,
                          'fits_256': max(ext) <= 256 and bool(np.isfinite(mesh.vertices).all())})
    path = OUT/'viewing/Powered_MVP_E01_SOLIDS_AP203.step'
    shape = cq.importers.importStep(str(path)).val()
    original = cq.importers.importStep(str(OUT/'Powered_MVP_E01_ASSEMBLY.step')).val()
    text = path.read_text()
    flat = {'valid': shape.isValid(), 'solids': len(shape.Solids()), 'assembly_solids': len(original.Solids()),
            'bounds_mm': v2.bbox(shape), 'relative_volume_error': abs(shape.Volume()-original.Volume())/original.Volume(),
            'assembly_occurrences': text.count('NEXT_ASSEMBLY_USAGE_OCCURRENCE'), 'sha256': sha(path),
            'solidworks_gui_import_verified': False}
    return {'mesh_checks': mesh_rows, 'flat_STEP': flat,
            'export_readback_pass': all(r['watertight'] and r['winding_consistent'] and r['bodies'] == 1 and r['fits_256'] for r in mesh_rows)
                and flat['valid'] and flat['solids'] == flat['assembly_solids'] and flat['relative_volume_error'] < 1e-6 and not flat['assembly_occurrences']}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--motion', action='store_true'); ap.add_argument('--export', action='store_true')
    args = ap.parse_args()
    m = build_model()
    OUT.mkdir(parents=True, exist_ok=True)
    static, accepted = v2.collisions(m.items, m.allowed)
    joints = supports(m)
    result = {'fingerprint': FINGERPRINT, 'validator_sha256': sha(Path(__file__)),
              'static_collisions': static, 'static_pass': not static, 'accepted_contacts': accepted,
              'support_checks': joints, 'support_pass': all(r['geometric_seat_pass'] for r in joints),
              'hardware_accepted': False, 'loaded_operation_allowed': False}
    print(json.dumps({'static': static, 'failed_seats': [r for r in joints if not r['geometric_seat_pass']]}, indent=2), flush=True)
    (OUT/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (OUT/'engineering_checks.json').write_text(json.dumps(engineering(m), ensure_ascii=False, indent=2))
    if args.motion:
        result['motion'] = motion(m)
        (OUT/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    if args.export and result['static_pass'] and result['support_pass'] and result.get('motion', {}).get('sampled_geometry_pass'):
        export(m)
        result.update(exports_check())
    result['geometry_deliverable_pass'] = bool(result['static_pass'] and result['support_pass']
        and result.get('motion', {}).get('sampled_geometry_pass') and result.get('export_readback_pass'))
    (OUT/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('GEOMETRY DELIVERABLE PASS', result['geometry_deliverable_pass'], flush=True)
    passed = result['static_pass'] and result['support_pass']
    if args.motion:
        passed = passed and result['motion']['sampled_geometry_pass']
    if args.export:
        passed = passed and result['geometry_deliverable_pass']
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
