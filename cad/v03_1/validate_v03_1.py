"""Check new load-path interfaces as well as the inherited motion envelope.

Reports explicitly distinguish coincident mating faces from verified fastener
capacity, and discrete collision checks from continuous dynamics.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

from asrs_v03_1 import OUT, ROOT, FINGERPRINT, X_SUPPORTS, Z_SUPPORTS, baseline, build_model, v2

# V02 and V03 use identical helper module names; select V03 explicitly.
sys.path.insert(0, str(ROOT/'cad'/'v03'))
from engineering_checks import mass
from verify_motion import packaging_model, check_pose


def mating_area(a, b):
    """Common area of opposite, coincident planar faces (not just zero distance)."""
    total = 0.
    for fa in a.Faces():
        if fa.geomType() != 'PLANE':
            continue
        na, ca = fa.normalAt(), fa.Center()
        ba = v2.bbox(fa)
        for fb in b.Faces():
            if fb.geomType() != 'PLANE':
                continue
            nb = fb.normalAt()
            if na.dot(nb) > -.999999 or abs(na.dot(fb.Center()-ca)) > 1e-5:
                continue
            bb = v2.bbox(fb)
            if any(min(ba[k+3], bb[k+3])-max(ba[k], bb[k]) < -1e-5 for k in range(3)):
                continue
            total += fa.intersect(fb).Area()
    return total


def connection_checks(m):
    shapes = {i.name: i.located() for i in m.items}
    rows = []
    for c in m.connections:
        a, b = shapes[c['a']], shapes[c['b']]
        gap = a.distance(b)
        area = mating_area(a, b) if gap < 1e-5 else 0.
        rows.append({**c, 'gap_mm': gap, 'mating_area_mm2': area,
                     'geometric_connection_pass': gap < 1e-5 and area > 2,
                     'fastener_strength_verified': False})
    return rows


def engineering(m):
    rows = []
    for i in m.items:
        kg, method = mass(i.part)
        c = i.located().Center()
        rows.append({'instance': i.name, 'group': i.group, 'kg': kg, 'method': method,
                     'centre_mm': [c.x, c.y, c.z]})
    zg = {'z', 'zgear', 'y', 'ygear', 'bin', 'pin', 'roller', 'crank', 'spring'}
    yg = {'y', 'ygear', 'bin', 'pin', 'roller', 'crank', 'spring'}
    zm = sum(r['kg'] for r in rows if r['group'] in zg)+1+.45
    xm = sum(r['kg'] for r in rows if r['group'] not in ('fixed', 'io_shutter'))+1+.9
    ym = sum(r['kg'] for r in rows if r['group'] in yg)+1+.20
    g = 9.80665
    targets = []
    for axis, kg, speed, accel, friction, external, ratio, eta in [
        ('X', xm, 12, 40, .03, 4, 1, .8), ('Z', zm, 3, 15, 0, 8, 10, .7), ('Y', ym, 5, 25, .35, 4, 3, .7)]:
        force = kg*accel/1000+friction*kg*g+external+(kg*g if axis == 'Z' else 0)
        targets.append({'axis': axis, 'mass_kg': kg, 'initial_speed_mm_s': speed, 'initial_accel_mm_s2': accel,
                        'ratio': ratio, 'assumed_total_efficiency': eta, 'force_N': force,
                        'pinion_torque_Nm': force*.015, 'motor_torque_with_SF2_Nm': 2*force*.015/(ratio*eta),
                        'motor_speed_rpm': speed/(2*math.pi*15)*60*ratio, 'motor_curve_verified': False})
    force = next(t['force_N'] for t in targets if t['axis'] == 'Z')
    radial = force*math.tan(math.radians(20))
    span = max(b-a for a, b in zip(Z_SUPPORTS, Z_SUPPORTS[1:]))
    inertia = 30*12**3/12
    yr = [r for r in rows if r['group'] == 'y']
    ykg = sum(r['kg'] for r in yr)
    moment = sum(r['kg']*g*(r['centre_mm'][0]-m.x)/1000 for r in yr)
    base = json.loads((ROOT/'model/V03/engineering_checks.json').read_text())
    original_y_moment = 0.
    # Original group centres are reconstructed from unchanged V03 part exports.
    old_manifest = json.loads((ROOT/'model/V03/manifest.json').read_text())
    old_by = {r['instance']: r for r in base['mass_breakdown']}
    cache = {}
    for i in old_manifest['instances']:
        if i['group'] != 'y':
            continue
        name = i['part']
        if name not in cache:
            cache[name] = baseline.cq.importers.importStep(str(ROOT/'model/V03/parts'/(name+'.step'))).val().Center().x
        original_y_moment += old_by[i['name']]['kg']*g*(cache[name]+i['origin_mm'][0]-m.x)/1000
    empty = sum(r['kg'] for r in rows)
    blockers = [
        'Printed Z teeth have no material/direction/creep/endurance acceptance, even without a 1 kg payload.',
        'Actual motor torque curves, measured masses, reducer drawings and output radial load ratings.',
        'Replace candidate flange hubs by selected clamp/keyed hubs with axial retention and torque proof.',
        'Independent fall protection: verified holding and dynamic capture on tooth fracture and power/control faults.',
        'Fastener lengths, engagement, tightening torques, T-nuts, tool access and bench anchor capacity.',
        'Local Y flexible harness, strain relief, bend radius and full-stroke endurance; electrical hardware and firmware.',
        'Door hardware, interlocks, physical limits, emergency stop and actual camera calibration.'
    ]
    return {'fingerprint': FINGERPRINT, 'mass_breakdown': rows, 'cad_empty_mass_estimate_kg': empty,
            'fully_loaded_mass_including_2kg_allowance_kg': empty+22,
            'motor_targets': targets,
            'Y_offset_comparison': {'V03_same_group_kg': sum(r['kg'] for r in base['mass_breakdown'] if r['group'] == 'y'),
                                    'V03_1_same_group_kg': ykg, 'V03_moment_Nm': original_y_moment,
                                    'V03_1_moment_Nm': moment, 'moment_reduction_fraction': 1-moment/original_y_moment,
                                    'guide_spacing_mm': 26,
                                    'ideal_vertical_reactions_N': [ykg*g/2-moment/.026, ykg*g/2+moment/.026],
                                    'note': 'Y rigid-group only, declared candidate weights; not rail or fastener acceptance.'},
            'Z_backbone_screen': {'thickness_mm': 12, 'width_mm': 30, 'max_support_span_mm': span,
                                 'assumed_aluminium_E_MPa': 69000, 'radial_force_N': radial,
                                 'I_mm4': inertia, 'simply_supported_centre_deflection_mm': radial*span**3/(48*69000*inertia),
                                 'nominal_peak_bending_stress_MPa': (radial*span/4)/(30*12**2/6),
                                 'note': 'Ideal isolated metal beam only; joints, bracket flexibility, tooth/rail error and FEA excluded.'},
            'printed_Z_tooth_screen': {'nominal_root_stress_MPa': force/(12*1.5*.3),
                                      'stress_with_SF2_MPa': 2*force/(12*1.5*.3),
                                      'allowable_printed_strength_verified': False,
                                      'note': 'Lewis screen; printed Z drive remains UNRELEASED. Added supports do not certify teeth.'},
            'blockers': blockers, 'hardware_accepted': False, 'manufacturing_release_allowed': False}


def motion_poses(m, step):
    n = math.ceil(m.d.transfer/step)
    qs = [m.d.transfer*j/n for j in range(n+1)]
    targets = [(xx, zz, f'stored_bin_{c}_{r}', False)
               for c, xx in enumerate(m.d.x_positions) for r, zz in enumerate(m.d.decks)]
    targets.append((-150, 200, None, True))
    lift = 7*(1-math.cos(math.radians(165)))
    poses = []
    for xx, zz, target, io in targets:
        for q in qs:
            poses.append(('transfer', xx-m.x, zz-m.deck, q, 0, target, None, int(io)))
            poses.append(('released_withdraw', xx-m.x, zz-m.deck, q, lift, target, m.d.transfer, int(io)))
        for bq in (0, m.d.transfer/2, m.d.transfer):
            for offset in (-1.1, 1.1):
                poses.append(('pin_clearance', xx-m.x, zz-m.deck, bq+offset, 0, target, bq, int(io)))
    for xx in [-150]+m.d.x_positions:
        for j in range(39):
            poses.append(('z_traverse', xx-m.x, 200+10*j-m.deck, -1.1, 0, None, 0, 0))
    for zz in m.d.decks:
        for j in range(40):
            poses.append(('x_traverse', -150+20*j-m.x, zz-m.deck, -1.1, 0, None, 0, 0))
    for io in (False, True):
        for q in (0, m.d.transfer):
            for angle in (0, 45, 90, 135, 165):
                poses.append(('latch', -150-m.x if io else 0, 200-m.deck if io else 0,
                              q, 7*(1-math.cos(math.radians(angle))), None if io else 'stored_bin_1_2', None, int(io)))
    for j in range(10):
        poses.append(('io_shutter', -150-m.x, 200-m.deck, -1.1, 0, None, 0, j/9))
    return poses


def validate(m, step=12, full_motion=False):
    connections = connection_checks(m)
    bad, _ = v2.collisions(m.items, m.allowed)
    report = {'fingerprint': FINGERPRINT, 'validator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'connections': connections, 'connection_count': len(connections),
              'connection_pass': all(c['geometric_connection_pass'] for c in connections),
              'unexpected_static_collisions': bad, 'static_pass': not bad,
              'continuous_collision_detection': False, 'fastener_strength_verified': False,
              'hardware_accepted': False, 'manufacturing_release_allowed': False}
    if full_motion:
        items = packaging_model(m)
        poses = motion_poses(m, step)
        failures, tests = [], 0
        start = time.monotonic()
        for j, pose in enumerate(poses, 1):
            phase, *args = pose
            wrong, n = check_pose(items, *args)
            tests += n
            if wrong:
                failures.append({'phase': phase, 'pose': args, 'collisions': wrong})
            if j % 100 == 0:
                print(f'POSE {j}/{len(poses)} failing={len(failures)} elapsed={time.monotonic()-start:.1f}s', flush=True)
        report['motion'] = {'pose_count': len(poses), 'y_step_mm': m.d.transfer/math.ceil(m.d.transfer/step),
                            'x_step_mm': 20, 'z_step_mm': 10, 'boolean_pair_tests': tests,
                            'failures': failures, 'sampled_packaging_pass': not failures,
                            'method': 'V03 conservative motor/pinion/rack envelopes, exact teeth tested separately.'}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--motion', action='store_true')
    ap.add_argument('--step', type=float, default=12)
    args = ap.parse_args()
    if args.step <= 0:
        ap.error('--step must be positive')
    m = build_model()
    result = validate(m, args.step, args.motion)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    sizing = engineering(m)
    (OUT/'engineering_checks.json').write_text(json.dumps(sizing, ensure_ascii=False, indent=2))
    print(json.dumps({k: result[k] for k in ('connection_count', 'connection_pass', 'unexpected_static_collisions', 'static_pass')}, indent=2), flush=True)
    print(json.dumps({'Y_offset_comparison': sizing['Y_offset_comparison'], 'Z_backbone_screen': sizing['Z_backbone_screen']}, indent=2), flush=True)
    if 'motion' in result:
        print('MOTION', result['motion']['pose_count'], 'FAILURES', len(result['motion']['failures']), flush=True)
    return int(not result['connection_pass'] or not result['static_pass'] or bool(result.get('motion', {}).get('failures')))


if __name__ == '__main__':
    raise SystemExit(main())
