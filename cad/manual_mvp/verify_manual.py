"""Discrete geometry and exported mesh checks, not physical acceptance."""
import hashlib
import json
import math
from pathlib import Path

import cadquery as cq
import trimesh

from manual_3axis import OUT, FINGERPRINT, Z_LOCKS, build, print_shape, kit, gears


def collisions(m, pose=None, rigid_skip=False):
    pose = pose or {}
    shapes = [(i, i.located(**pose)) for i in m.items if pose.get('lock', True) or i.group != 'lock']
    bounds = [kit.bbox(s) for i, s in shapes]
    bad = []
    count = 0
    for ai, (a, sa) in enumerate(shapes):
        for bi in range(ai+1, len(shapes)):
            b, sb = shapes[bi]
            if rigid_skip and a.group == b.group:
                continue
            if not kit.overlaps(bounds[ai], bounds[bi]):
                continue
            count += 1
            volume = sa.intersect(sb).Volume()
            if volume > .02:
                bad.append({'a': a.name, 'b': b.name, 'volume_mm3': volume})
    return bad, count


def support_checks(m):
    shapes = {i.name: i.located() for i in m.items}
    pairs = [('x_base', f'floor_{side}_0') for side in (-1, 1)]
    pairs += [('tower_foot', 'x_carriage'), ('z_base', 'tower_foot'), ('stand_frame', 'cell')]
    for side in ('left', 'right'):
        pairs += [('y_mount_'+side, 'z_carriage'), ('y_mount_'+side, 'y_base')]
    for side in (-1, 1):
        for yy in (-128, -28):
            pairs += [(f'carrier_pillar_{side}_{yy}', name) for name in ('y_base', 'carrier_tray')]
    for xx in (-76, 76):
        for yy in (10, 140):
            pairs += [(f'stand_leg_{xx}_{yy}', name) for name in (f'floor_cross_{yy}', 'stand_frame')]
    rows = []
    for a, b in pairs:
        sa, sb = shapes[a], shapes[b]
        gap = sa.distance(sb)
        area = 0.
        if gap < 1e-5:
            for fa in sa.Faces():
                if fa.geomType() != 'PLANE':
                    continue
                na, ca = fa.normalAt(), fa.Center()
                for fb in sb.Faces():
                    if fb.geomType() != 'PLANE' or na.dot(fb.normalAt()) > -.999999:
                        continue
                    if abs(na.dot(fb.Center()-ca)) < 1e-5:
                        area += fa.intersect(fb).Area()
        rows.append({'a': a, 'b': b, 'gap_mm': gap, 'mating_area_mm2': area,
                     'geometric_seat_pass': gap < 1e-5 and area > 2, 'strength_verified': False})
    return rows


def main():
    m = build()
    errors = []
    static, _ = collisions(m)
    if static:
        errors.append('initial assembly has interference')
    supports = support_checks(m)
    if not all(r['geometric_seat_pass'] for r in supports):
        errors.append('structural support has gap or lacks mating area')
    poses = []
    for j in range(25):
        q = 143*j/24
        poses.append(('transfer', dict(q=q, lock=True)))
        poses.append(('released_withdraw', dict(q=q, lift=14, stored=True, lock=True)))
    for x in (-50, -25, 0, 25, 50):
        for z in (-40, -20, 0, 20, 40):
            poses.append(('xz_retracted', dict(dx=x, dz=z, lock=False)))
    for j in range(41):
        poses.append(('z_stroke', dict(dz=-40+2*j, lock=False)))
    for z in Z_LOCKS:
        poses.append(('z_locked_index', dict(dz=z, lock=True)))
    failures = []
    pairs = 0
    for n, (phase, pose) in enumerate(poses, 1):
        bad, count = collisions(m, pose, True)
        pairs += count
        if bad:
            failures.append({'phase': phase, 'pose': pose, 'collisions': bad})
        if n % 25 == 0:
            print('POSE', n, '/', len(poses), 'failing', len(failures), flush=True)
    if failures:
        errors.append('sampled motion interference')

    # Validate actual STEP/STL files, including the side-down print orientations.
    parts = []
    meshes = []
    for p in m.parts.values():
        path = OUT/'parts'/(p.code+'.step')
        s = cq.importers.importStep(str(path)).val()
        ok = s.isValid() and len(s.Solids()) == 1 and abs(s.Volume()-p.shape.Volume()) < max(.001, p.shape.Volume()*1e-6)
        parts.append({'code': p.code, 'pass': ok, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if not ok:
            errors.append('part STEP '+p.code)
        if p.process == 'print':
            path = OUT/'stl'/(p.code+'.stl')
            mesh = trimesh.load_mesh(path, process=True)
            single = len(mesh.split(only_watertight=False)) == 1
            relative = abs(abs(mesh.volume)-p.shape.Volume())/p.shape.Volume()
            ok = bool(mesh.is_watertight and mesh.is_winding_consistent and single and max(mesh.extents) <= 256 and relative < .02)
            meshes.append({'code': p.code, 'pass': ok, 'watertight': bool(mesh.is_watertight),
                           'single_component': single, 'print_extents_mm': mesh.extents.tolist(),
                           'relative_volume_error': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            if not ok:
                errors.append('print mesh '+p.code)

    # Pulling surfaces must not have proud cap heads: check the actual recesses.
    recesses = []
    for code in ('P14', 'P15'):
        part = m.parts[code].shape
        for xx in (-52, 52):
            for yy in (-50, 50):
                probe = cq.Solid.makeCone(2, 4.45, 2.45, cq.Vector(xx, yy, 1.55))
                ok = part.intersect(probe).Volume() < .001
                recesses.append({'part': code, 'x': xx, 'y': yy, 'head_recess_pass': ok})
                if not ok:
                    errors.append('countersunk head '+code)
    # Pinion/rack overlap-free checks alone do not prove strength or contact load.
    count_print = sum(p.process == 'print' for p in m.parts.values())
    source = OUT/'Manual_3Axis_Assembly.step'
    a = cq.importers.importStep(str(source)).val()
    assembly = {'valid': a.isValid(), 'solid_count': len(a.Solids()), 'expected_solids': len(m.items),
                'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'extents_mm': list(a.BoundingBox().toTuple()) if hasattr(a.BoundingBox(), 'toTuple') else list(kit.bbox(a))}
    if not assembly['valid'] or assembly['solid_count'] != assembly['expected_solids']:
        errors.append('assembly STEP')
    report = {'fingerprint': FINGERPRINT, 'validator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'geometry_deliverable_pass': not errors, 'errors': errors, 'static_collisions': static,
              'structural_support_checks': supports,
              'motion_pose_count': len(poses), 'boolean_pair_tests': pairs, 'motion_failures': failures,
              'part_count': len(parts), 'printable_types': count_print, 'step_checks': parts, 'mesh_checks': meshes,
              'countersunk_head_checks': recesses, 'assembly_step': assembly,
              'guide_clearance_verified_on_printer': False, 'empty_bin_hardware_tested': False,
              'continuous_collision_detection': False, 'hardware_accepted': False,
              'payload_allowed_kg': 0, 'loaded_operation_allowed': False,
              'limitations': ['Discrete un-deformed rigid geometry only.',
                              'Printed guides do not validate production metal rails or bearing capacity.',
                              'Manual Z pin requires hand engagement; not an automatic fall arrest.',
                              'Frame fastener heads not all modelled; use specified lengths and inspect during assembly.']}
    (OUT/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('geometry_deliverable_pass', 'errors', 'motion_pose_count', 'printable_types')}, indent=2), flush=True)
    if failures:
        print(json.dumps(failures[:4], indent=2), flush=True)
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
