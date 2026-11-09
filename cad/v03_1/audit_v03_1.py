"""Read back exported geometry and bind the evidence to the current sources."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import cadquery as cq
import trimesh

from asrs_v03_1 import OUT, ROOT, FINGERPRINT, baseline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    errors = []
    manifest = json.loads((OUT/'manifest.json').read_text())
    validation = json.loads((OUT/'validation.json').read_text())
    engineering = json.loads((OUT/'engineering_checks.json').read_text())
    for name, data in [('manifest', manifest), ('validation', validation), ('engineering', engineering)]:
        if data['fingerprint'] != FINGERPRINT:
            errors.append(name+' fingerprint differs')
        if data['hardware_accepted'] or data['manufacturing_release_allowed']:
            errors.append(name+' incorrectly released hardware')
    if not validation['connection_pass'] or not validation['static_pass']:
        errors.append('connection or static validation failed')
    if not validation.get('motion', {}).get('sampled_packaging_pass') or validation['motion']['pose_count'] < 1097:
        errors.append('full motion evidence missing or failed')
    if validation['validator_sha256'] != sha(Path(__file__).with_name('validate_v03_1.py')):
        errors.append('validator changed since run')

    suite = ET.parse(OUT/'tests.xml').getroot()
    properties = {p.get('name'): p.get('value') for p in suite.iter('property')}
    if properties.get('geometry_fingerprint') != FINGERPRINT:
        errors.append('test geometry fingerprint differs')
    for path in (Path(__file__).with_name('test_v03_1.py'), Path(__file__).with_name('validate_v03_1.py'),
                 ROOT/'cad/v03/test_v03.py', ROOT/'cad/v03/control_contract.py'):
        if properties.get(path.name+'_sha256') != sha(path):
            errors.append('tested source changed: '+path.name)
    suites = list(suite.iter('testsuite'))
    count = sum(int(s.get('tests', 0)) for s in suites)
    if count < 30 or any(int(s.get('errors', 0))+int(s.get('failures', 0))+int(s.get('skipped', 0)) for s in suites):
        errors.append('regressions missing, skipped or failed')

    parts, meshes = [], []
    for p in manifest['parts']:
        path = OUT/'parts'/(p['name']+'.step')
        s = cq.importers.importStep(str(path)).val()
        b = s.BoundingBox()
        # Fresh analytic STEP bounds may differ slightly from tessellated bounds.
        extent_error = max(abs(a-c) for a, c in zip([b.xlen, b.ylen, b.zlen], p['extents_mm']))
        passed = (s.isValid() and len(s.Solids()) == p['solids']
                  and abs(s.Volume()-p['volume_mm3']) < max(1e-4, p['volume_mm3']*1e-6)
                  and extent_error < .02)
        parts.append({'name': p['name'], 'sha256': sha(path), 'pass': passed, 'solids': len(s.Solids()),
                      'max_analytic_extent_difference_mm': extent_error})
        if not passed:
            errors.append('part STEP readback: '+p['name'])
        if p['process'] == 'print':
            path = OUT/'stl'/(p['name']+'.stl')
            mesh = trimesh.load_mesh(path, process=True)
            bodies = len(mesh.split(only_watertight=False))
            relative = abs(abs(mesh.volume)-s.Volume())/s.Volume()
            ok = bool(mesh.is_watertight and mesh.is_winding_consistent and bodies == 1
                      and max(mesh.extents) <= 256 and relative < .02)
            meshes.append({'name': p['name'], 'sha256': sha(path), 'watertight': bool(mesh.is_watertight),
                           'bodies': bodies, 'volume_relative_error': relative, 'pass': ok})
            if not ok:
                errors.append('printed mesh: '+p['name'])
    path = OUT/'ASRS_Modular_V03_1.step'
    s = cq.importers.importStep(str(path)).val()
    byname = {p['name']: p for p in manifest['parts']}
    expected = sum(byname[i['part']]['solids'] for i in manifest['instances'])
    volume = sum(byname[i['part']]['volume_mm3'] for i in manifest['instances'])
    b = s.BoundingBox()
    assembly = {'valid': s.isValid(), 'solid_count': len(s.Solids()), 'expected_solids': expected,
                'sha256': sha(path), 'extents_mm': [b.xlen, b.ylen, b.zlen], 'bytes': path.stat().st_size}
    assembly['pass'] = assembly['valid'] and len(s.Solids()) == expected and abs(s.Volume()-volume) < volume*1e-6
    if not assembly['pass']:
        errors.append('assembly STEP readback failed')

    # Confirm preserved V03 CAD and reports, rather than assuming the new output
    # directory alone guarantees that the old delivery was left untouched.
    old = json.loads((ROOT/'model/V03/delivery_audit.json').read_text())
    if old['fingerprint'] != baseline.FINGERPRINT:
        errors.append('baseline source fingerprint differs')
    if sha(ROOT/'model/V03/ASRS_Modular_V03.step') != old['assembly_step_readback']['file_sha256']:
        errors.append('baseline assembly changed')
    for p in old['part_step_readbacks']:
        if sha(ROOT/'model/V03/parts'/(p['name']+'.step')) != p['sha256']:
            errors.append('baseline part changed: '+p['name'])

    light = json.loads((OUT/'viewing/light_view_readback.json').read_text())
    light_path = OUT/'viewing'/light['file']
    if light['fingerprint'] != FINGERPRINT or not light['readback_pass'] or sha(light_path) != light['sha256']:
        errors.append('light view outdated or invalid')
    previews = json.loads((OUT/'previews/manifest.json').read_text())
    if previews['fingerprint'] != FINGERPRINT:
        errors.append('previews outdated')
    report = {'fingerprint': FINGERPRINT, 'prototype_geometry_deliverable_pass': not errors, 'errors': errors,
              'part_types': len(parts), 'instances': len(manifest['instances']), 'printable_types': len(meshes),
              'regression_test_count': count, 'connection_count': validation['connection_count'],
              'motion_pose_count': validation['motion']['pose_count'], 'assembly_step_readback': assembly,
              'part_step_readbacks': parts, 'stl_mesh_checks': meshes,
              'baseline_V03_CAD_unchanged': not any('baseline' in e for e in errors),
              'native_motion_assembly_created': False, 'continuous_collision_detection': False,
              'hardware_accepted': False, 'manufacturing_release_allowed': False,
              'release_blockers': engineering['blockers']}
    (OUT/'delivery_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('prototype_geometry_deliverable_pass', 'errors', 'part_types',
                                           'instances', 'printable_types', 'regression_test_count',
                                           'connection_count', 'motion_pose_count')}, indent=2), flush=True)
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
