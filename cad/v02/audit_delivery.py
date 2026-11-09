"""Independent disk-artifact audit. Does not turn engineering assumptions into approvals."""
import argparse
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import cadquery as cq
import numpy as np

from asrs_v02 import OUT, source_sha256


def audit_stl(path):
    data = path.read_bytes()
    n = struct.unpack_from('<I', data, 80)[0] if len(data) >= 84 else 0
    if len(data) != 84+50*n:
        raise ValueError('Expected the binary STL produced by this exporter: '+str(path))
    dtype = np.dtype([('normal', '<f4', (3,)), ('v', '<f4', (3, 3)), ('attr', '<u2')])
    triangles = np.frombuffer(data, dtype, n, 84)['v'].astype(float)
    _, inverse = np.unique(np.round(triangles.reshape(-1, 3), 5), axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    edge_faces, directed, parents = {}, Counter(), list(range(len(faces)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]; i = parents[i]
        return i
    for k, tri in enumerate(faces):
        for a, b in zip(tri, np.roll(tri, -1)):
            directed[(int(a), int(b))] += 1
            key = tuple(sorted((int(a), int(b))))
            if key in edge_faces:
                r1, r2 = root(k), root(edge_faces[key][0]); parents[r1] = r2
                edge_faces[key].append(k)
            else:
                edge_faces[key] = [k]
    volume = np.einsum('ij,ij->i', triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum()/6
    extents = triangles.max((0, 1))-triangles.min((0, 1))
    return {'triangles': n, 'watertight': bool(n) and all(len(v) == 2 for v in edge_faces.values()),
            'winding_consistent': all(directed[(a, b)] == directed[(b, a)] for a, b in edge_faces),
            'connected_bodies': len({root(i) for i in range(n)}), 'volume_mm3': float(volume),
            'extents_mm': extents.tolist(), 'fits_a1': bool(max(extents) <= 256)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive-stale', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    generator_hash = source_sha256()
    errors, archived, stale = [], [], []
    expected = {p['name'] for p in manifest['parts']}
    print_expected = {p['name'] for p in manifest['parts'] if p['process'] == 'print'}
    for folder, suffix, names in (('parts', '.step', expected), ('stl', '.stl', print_expected)):
        for path in (OUT/folder).glob('*'+suffix):
            if path.stem not in names:
                stale.append(str(path.relative_to(OUT)))
                if args.archive_stale:
                    target = OUT/'superseded_generated'/folder/path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise FileExistsError('Refusing to overwrite archived artifact '+str(target))
                    path.rename(target)
                    archived.append(str(target.relative_to(OUT)))
    if manifest.get('generator_sha256') != generator_hash:
        errors.append('manifest generator fingerprint differs')
    sources = {}
    for name in ('validation.json', 'motion_validation.json', 'engineering_checks.json'):
        sources[name] = json.loads((OUT/name).read_text(encoding='utf-8'))
        if sources[name].get('generator_sha256') != generator_hash:
            errors.append(name+' generator fingerprint differs')
    static, motion = sources['validation.json'], sources['motion_validation.json']
    if static['unexpected_static_collisions'] or not all(c['pass'] for c in static['dimensional_checks']):
        errors.append('static validation failed')
    if motion['failures'] or not motion['geometry_sample_pass']:
        errors.append('sampled motion validation failed')
    verifier = Path(__file__).with_name('verify_motion.py')
    if motion.get('verifier_sha256') != hashlib.sha256(verifier.read_bytes()).hexdigest():
        errors.append('motion checker fingerprint differs')
    suite = ET.parse(OUT/'tests.xml').getroot()
    suites = list(suite.iter('testsuite'))
    test_count = sum(int(s.get('tests', 0)) for s in suites)
    if test_count < 15 or any(int(s.get('failures', 0))+int(s.get('errors', 0)) for s in suites):
        errors.append('unit tests missing or failed')
    parts, meshes = [], []
    for n, p in enumerate(manifest['parts'], 1):
        path = OUT/'parts'/(p['name']+'.step')
        shape = cq.importers.importStep(str(path)).val()
        volume = shape.Volume()
        relative_error = abs(volume-p['volume_mm3'])/max(p['volume_mm3'], 1e-9)
        absolute_error = abs(volume-p['volume_mm3'])
        row = {'name': p['name'], 'valid': shape.isValid(), 'solids': len(shape.Solids()),
               'volume_mm3': volume, 'volume_relative_error': relative_error,
               'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        parts.append(row)
        # Manifest volumes are rounded to 4 decimal places: allow that quantization.
        if not row['valid'] or row['solids'] != 1 or absolute_error > max(.000051, volume*1e-6):
            errors.append('STEP round trip failed '+p['name'])
        if p['process'] == 'print':
            stl = audit_stl(OUT/'stl'/(p['name']+'.stl'))
            stl['name'] = p['name']
            stl['volume_relative_error'] = abs(stl['volume_mm3']-volume)/volume
            meshes.append(stl)
            if not (stl['watertight'] and stl['winding_consistent'] and stl['connected_bodies'] == 1
                    and stl['fits_a1'] and stl['volume_relative_error'] < .02):
                errors.append('STL audit failed '+p['name'])
        if n % 20 == 0:
            print(f'ROUND_TRIP {n}/{len(manifest["parts"])}', flush=True)
    assembly_path = OUT/'ASRS_Modular_V02.step'
    assembly = cq.importers.importStep(str(assembly_path)).val()
    part_volumes = {p['name']: p['volume_mm3'] for p in manifest['parts']}
    expected_volume = sum(part_volumes[i['part']] for i in manifest['instances'])
    bounds = assembly.BoundingBox()
    assembly_check = {'valid': assembly.isValid(), 'solids': len(assembly.Solids()),
                      'expected_components': len(manifest['instances']),
                      'extents_mm': [bounds.xlen, bounds.ylen, bounds.zlen],
                      'volume_mm3': assembly.Volume(), 'expected_volume_mm3': expected_volume,
                      'file_sha256': hashlib.sha256(assembly_path.read_bytes()).hexdigest()}
    assembly_check['pass'] = (assembly_check['valid']
        and assembly_check['solids'] == assembly_check['expected_components']
        and abs(assembly_check['volume_mm3']-expected_volume) <= max(.02, expected_volume*1e-6))
    if not assembly_check['pass']:
        errors.append('assembly STEP round trip failed')
    native_path = OUT/'native'/'solidworks_validation.json'
    native = json.loads(native_path.read_text(encoding='utf-8')) if native_path.exists() else None
    native_ok = bool(native and native.get('generator_sha256') == generator_hash
                     and native.get('status') == 'native_positioned_assembly_saved'
                     and len(native.get('parts', [])) == len(parts)
                     and native.get('component_count') == len(manifest['instances'])
                     and native.get('temporary_preferences_restored') is True)
    native_missing_files = []
    if native_ok:
        for p in manifest['parts']:
            if not (OUT/'native'/'parts'/(p['name']+'.SLDPRT')).is_file():
                native_missing_files.append(p['name'])
        native_ok = not native_missing_files and (OUT/'native'/'ASRS_Modular_V02.SLDASM').is_file()
    report = {'generator_sha256': generator_hash, 'prototype_geometry_deliverable_pass': not errors,
              'errors': errors, 'unit_test_count': test_count, 'motion_pose_count': motion['pose_count'],
              'native_positioned_assembly_pass': native_ok, 'native_missing_files': native_missing_files,
              'native_conversion_status': native.get('status') if native else 'not_completed',
              'native_saved_part_count': len(native.get('parts', [])) if native else 0,
              'solidworks_preferences_restored': native.get('temporary_preferences_restored') if native else None,
              'solidworks_settings_review_required': bool(native and native.get('temporary_preferences_restored') is False),
              'assembly_step_round_trip': assembly_check,
              'step_round_trip': parts, 'stl_checks': meshes, 'archived_obsolete_artifacts': archived,
              'obsolete_artifacts_found': stale, 'manufacturing_release_allowed': False,
              'hardware_accepted': False,
              'release_blockers': ['Supplier drawings and purchased interfaces not frozen',
                  'Complete manufacturing drawings, fastener/tool access and tolerance chain pending',
                  'Safety circuit, wiring and feedback not implemented',
                  'Catch impact, brake, frame stiffness, endurance and real load tests pending',
                  'Native Motion Study and physical contact dynamics not verified']}
    (OUT/'delivery_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'geometry_pass': not errors, 'native_pass': native_ok, 'step_parts': len(parts),
                      'printed_stls': len(meshes), 'tests': test_count, 'errors': errors,
                      'manufacturing_release_allowed': False}, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
