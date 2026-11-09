"""E02 exact static/sample geometry, export readback and honest engineering screens."""
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

from belt_mvp import (OUT, ROOT, BASE, FINGERPRINT, build_model, export, v2, e01, Item,
                      RADIUS, INNER, OUTER, box, cyl, fuse, drill, hz, belt_loop,
                      X_LEFT, X_RIGHT, Y_REAR, Y_FRONT)
sys.path.insert(0, str(ROOT/'cad/powered_mvp'))
import validate_powered as previous


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def motion(m):
    items = []
    for i in m.items:
        if i.name == 'maintenance_pin': continue
        p = i.part
        if p.name.startswith('ZDT_RealMotor'):
            s = fuse(box(1.325, -10.45, -59, 44.65, 62.9, 59), cyl(0, 0, 0, 11, 2), cyl(0, 0, 2, 2.5, 22))
            s = drill(s, [hz(a, b, -6, 2.5, 8) for a in (-15.5, 15.5) for b in (-15.5, 15.5)])
            if not p.name.endswith('_Y_Up'): s = s.rotate((0, 0, 0), (1, 0, 0), 180)
            p = replace(p, shape=s)
        items.append(Item(i.name, p, i.origin, i.group))
    failures, tests = [], 0; start = time.monotonic()
    for n, pose in enumerate(previous.poses(), 1):
        phase, dx, dz, q, lift, bq, door = pose
        rows = [(i, i.located(dx, dz, q, lift, bq, door)) for i in items]
        rows = [(i, s, v2.bbox(s)) for i, s in rows]
        bad = []
        for k, (a, sa, ba) in enumerate(rows):
            for b, sb, bb in rows[k+1:]:
                if a.group == b.group or tuple(sorted((a.name, b.name))) in m.allowed or not v2.overlaps(ba, bb): continue
                tests += 1; vol = sa.intersect(sb).Volume()
                if vol > .02: bad.append({'a': a.name, 'b': b.name, 'volume_mm3': round(vol, 5)})
        if bad: failures.append({'pose': pose, 'collisions': bad})
        if n % 20 == 0: print(f'MOTION {n}/165 failures={len(failures)} elapsed={time.monotonic()-start:.1f}s', flush=True)
    return {'pose_count': len(previous.poses()), 'failures': failures, 'boolean_pair_tests': tests,
            'sampled_geometry_pass': not failures, 'maintenance_pin_removed': True,
            'X_step_mm': 10, 'Z_step_mm': 5, 'Y_step_mm': 11, 'IO_shutter_samples': 11,
            'continuous_collision_detection': False,
            'method': 'Exact structural BReps + conservative complete motor body envelopes, correct Y face-up orientation. Only named jaw/belt contact pairs excluded. Belts smooth, no tooth dynamics or stretch simulation.'}


def engineering(m):
    r = previous.engineering(m); r['fingerprint'] = FINGERPRINT
    for t in r['motor_targets']:
        if t['axis'] != 'Z':
            t['required_motor_torque_SF2_Nm'] = 2*t['force_N']*RADIUS/1000/t['assumed_efficiency']
            t['motor_rpm'] = 60*t['candidate_initial_speed_mm_s']/40
    old = json.loads((BASE/'engineering_checks.json').read_text())
    old_targets = {t['axis']: t for t in old['motor_targets']}
    r['comparison_to_E01'] = [{'axis': t['axis'],
        'E01_mass_kg': old_targets[t['axis']]['moving_mass_with_1kg_payload_and_allowance_kg'],
        'E02_mass_kg': t['moving_mass_with_1kg_payload_and_allowance_kg'],
        'E01_torque_SF2_Nm': old_targets[t['axis']]['required_motor_torque_SF2_Nm'],
        'E02_torque_SF2_Nm': t['required_motor_torque_SF2_Nm']} for t in r['motor_targets']]
    # Belt pretension can INCREASE motor bearing load compared with a rack.
    # This is an illustrative check, not a tension-setting instruction.
    t0 = 15.
    r['belt_screen'] = {'pitch_mm': 2, 'pulley_teeth': 20, 'advance_mm_rev': 40,
        'illustrative_pretension_N': t0, 'pretension_instruction': False,
        'approx_motor_radial_load_N': 2*t0,
        'shaft_bending_moment_X_Nm': 2*t0*(82-64.5)/1000,
        'shaft_bending_moment_Y_Nm': 2*t0*11.5/1000,
        'strands': [{'axis': t['axis'], 'tight_at_SF2_N': t0+t['force_N'], 'slack_at_SF2_N': t0-t['force_N']}
                    for t in r['motor_targets'] if t['axis'] != 'Z'],
        'belt_strength_stiffness_and_motor_bearing_rating_verified': False,
        'note': 'Supplier belt width, cord, pulley minimum teeth, clamp tooth profile, bearing radial rating and tension must be confirmed; lower drive torque does not imply lower shaft radial load.'}
    inertia = (16+(2*INNER-2))*8**3/12
    r['X_stand_screen'] = {'assumed_aluminium_E_MPa': 69000, 'height_mm': 72,
        'conservative_parallel_leg_I_mm4': inertia,
        'ideal_cantilever_deflection_at_30N_mm': 30*72**3/(3*69000*inertia),
        'note': 'Isolated-leg ideal screen only; top/base bending, welded joints and actual belt direction excluded. Measure under selected tension.'}
    I = (25**4-21**4)/12
    moving = next(t for t in r['motor_targets'] if t['axis'] == 'Y')['moving_mass_with_1kg_payload_and_allowance_kg']
    r['tray_tube_screen'] = {'section_mm': [25, 25, 2], 'assumed_E_MPa': 69000,
        'conservative_cantilever_length_mm': 227,
        'ideal_two_tube_tip_deflection_mm': moving*9.80665/2*227**3/(3*69000*I),
        'note': 'Assumes equal load sharing, ideal clamp and all head/payload mass at tip. No joint, guide or creep acceptance.'}
    r['blockers'] = ['Motor actual torque-speed/electrical/thermal data, weighed masses and radial bearing capacity under belt pretension',
        'Vendor GT2 belt/pulley/idler/axle selection, positive drive-hub retention and matched metal clamp tooth form/pull-out proof',
        'Spine/head/tube clearances, compression sleeves, fastener engagement, tensioner locking and bench anchors',
        'Independent automatic fall protection still unselected; TR8x2/secondary nut/maintenance pin are not a safety system',
        'Actual limits/door/E-stop/earthing/protection, flexible Z/servo wiring and control firmware',
        'Screw/nut/journal fits, thrust preload, cross-pin/collar ratings and printed bin/latch endurance']
    return r


def tension_limits(m):
    """Maximum nominal adjuster positions; belt stretch/rating NOT accepted."""
    items = []
    for i in m.items:
        xx, yy, zz = i.origin; p = i.part
        if (i.name.startswith('x_idler_') and not i.name.startswith('x_idler_lock_')) or i.name == 'x_tension_pusher':
            xx += 2
        if i.name.startswith('y_idler_') or i.name == 'y_tension_pusher':
            yy -= 2
        if i.name == 'x_belt':
            p = replace(p, shape=belt_loop(X_RIGHT-X_LEFT+2).rotate((0, 0, 0), (0, 0, 1), -90))
        if i.name == 'y_belt':
            p = replace(p, shape=belt_loop(Y_FRONT-Y_REAR+2)); yy -= 2
        items.append(Item(i.name, p, (xx, yy, zz), i.group))
    wrong, accepted = v2.collisions(items, m.allowed)
    return {'X_idler_shift_mm': 2, 'Y_idler_shift_mm': -2, 'unexpected_collisions': wrong,
            'geometry_pass': not wrong, 'belt_effective_loop_regenerated': True,
            'belt_extension_is_an_instruction': False,
            'note': 'Hardware/package clearance at both nominal stroke ends only. Not permitted belt elongation or selected working tension.'}


def readback():
    manifest = json.loads((OUT/'manifest.json').read_text()); meshes = []
    for r in manifest['parts']:
        if r['process'] != 'print': continue
        path = OUT/'stl'/(r['code']+'.stl'); mesh = trimesh.load_mesh(path, process=True)
        meshes.append({'code': r['code'], 'name': r['name'], 'sha256': sha(path),
            'watertight': bool(mesh.is_watertight), 'winding_consistent': bool(mesh.is_winding_consistent),
            'bodies': mesh.body_count, 'extents_mm': mesh.extents.tolist(),
            'fits_256': max(mesh.extents) <= 256 and bool(np.isfinite(mesh.vertices).all())})
    path = OUT/'viewing/Belt_MVP_E02_SOLIDS_AP203.step'
    flat = cq.importers.importStep(str(path)).val(); asm = cq.importers.importStep(str(OUT/'Belt_MVP_E02_ASSEMBLY.step')).val()
    text = path.read_text()
    data = {'valid': flat.isValid(), 'solids': len(flat.Solids()), 'assembly_solids': len(asm.Solids()),
        'bounds_mm': v2.bbox(flat), 'relative_volume_error': abs(flat.Volume()-asm.Volume())/asm.Volume(),
        'assembly_occurrences': text.count('NEXT_ASSEMBLY_USAGE_OCCURRENCE'), 'sha256': sha(path), 'solidworks_gui_import_verified': False}
    passed = all(r['watertight'] and r['winding_consistent'] and r['bodies'] == 1 and r['fits_256'] for r in meshes)
    passed = passed and data['valid'] and data['solids'] == data['assembly_solids'] and data['relative_volume_error'] < 1e-6 and not data['assembly_occurrences']
    return {'mesh_checks': meshes, 'flat_STEP': data, 'export_readback_pass': bool(passed)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--motion', action='store_true'); ap.add_argument('--export', action='store_true'); args = ap.parse_args()
    m = build_model(); OUT.mkdir(parents=True, exist_ok=True)
    static, accepted = v2.collisions(m.items, m.allowed)
    seats = previous.supports(m)
    tension = tension_limits(m)
    r = {'fingerprint': FINGERPRINT, 'validator_sha256': sha(Path(__file__)), 'static_collisions': static,
        'static_pass': not static, 'accepted_contacts': accepted, 'support_checks': seats,
        'support_pass': all(s['geometric_seat_pass'] for s in seats), 'tensioner_limits': tension,
        'hardware_accepted': False, 'loaded_operation_allowed': False}
    print(json.dumps({'static': static, 'failed_seats': [s for s in seats if not s['geometric_seat_pass']],
                      'tensioner_limit_collisions': tension['unexpected_collisions']}, indent=2), flush=True)
    (OUT/'engineering_checks.json').write_text(json.dumps(engineering(m), ensure_ascii=False, indent=2))
    (OUT/'validation.json').write_text(json.dumps(r, ensure_ascii=False, indent=2))
    if args.motion:
        r['motion'] = motion(m); (OUT/'validation.json').write_text(json.dumps(r, ensure_ascii=False, indent=2))
    if args.export and r['static_pass'] and r['support_pass'] and tension['geometry_pass'] and r.get('motion', {}).get('sampled_geometry_pass'):
        export(m); r.update(readback())
    r['geometry_deliverable_pass'] = bool(r['static_pass'] and r['support_pass'] and tension['geometry_pass'] and r.get('motion', {}).get('sampled_geometry_pass') and r.get('export_readback_pass'))
    (OUT/'validation.json').write_text(json.dumps(r, ensure_ascii=False, indent=2))
    print('E02 GEOMETRY DELIVERABLE PASS', r['geometry_deliverable_pass'], flush=True)
    passed = r['static_pass'] and r['support_pass'] and tension['geometry_pass']
    if args.motion: passed = passed and r['motion']['sampled_geometry_pass']
    if args.export: passed = passed and r['geometry_deliverable_pass']
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
