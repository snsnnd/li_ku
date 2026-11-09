"""Audit E02 evidence/source, preserve all earlier deliveries, then package."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf

from belt_mvp import ROOT, OUT, BASE, FINGERPRINT, DEPENDENCIES


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((OUT/'manifest.json').read_text()); checks = json.loads((OUT/'validation.json').read_text())
    drawing = json.loads((OUT/'drawings/manifest.json').read_text()); errors = []
    for name, r in [('geometry', manifest), ('validation', checks), ('drawings', drawing)]:
        if r['fingerprint'] != FINGERPRINT: errors.append(name+' stale fingerprint')
    if not checks['geometry_deliverable_pass']: errors.append('geometry checks failed')
    if checks['validator_sha256'] != sha(Path(__file__).with_name('validate_belt.py')): errors.append('validator changed')
    if drawing['generator_sha256'] != sha(Path(__file__).with_name('deliver_belt.py')): errors.append('drawing generator changed')
    pdf_path = OUT/'drawings'/drawing['file']
    if sha(pdf_path) != drawing['sha256']: errors.append('PDF changed')
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != drawing['page_count']: errors.append('page count mismatch')
        for n, page in enumerate(pdf, 1):
            if 'E02' not in page.get_text(): errors.append(f'page{n} missing E02')
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        x0, y0, x1, y1 = span['bbox']
                        if x0 < 0 or y0 < 0 or x1 > page.rect.width or y1 > page.rect.height:
                            errors.append(f'page{n} text outside paper')
    count = 0
    for suite in ET.parse(OUT/'tests.xml').getroot().iter('testsuite'):
        count += int(suite.get('tests', 0))
        if sum(int(suite.get(k, 0)) for k in ('failures', 'errors', 'skipped')): errors.append('tests failed/skipped')
    if count < 15: errors.append('regressions missing')
    if sha(OUT/'viewing/Belt_MVP_E02_SOLIDS_AP203.step') != checks['flat_STEP']['sha256']: errors.append('STEP changed')
    for r in checks['mesh_checks']:
        if sha(OUT/'stl'/(r['code']+'.stl')) != r['sha256']: errors.append(r['code']+' STL changed')
    for name in ('README.md', '采购补充与未选型项.md', '打印清单.csv', '采购与金属加工清单.csv', 'E01_E02优化对比.md'):
        if not (OUT/name).is_file(): errors.append('missing '+name)
    preserved = Path('/tmp/opencode/e02_preserved_hashes.json'); old_count = 0
    if preserved.exists():
        for name, expected in json.loads(preserved.read_text()).items():
            old_count += 1
            if not (ROOT/name).is_file() or sha(ROOT/name) != expected: errors.append('prior delivery changed '+name)
    report = {'fingerprint': FINGERPRINT, 'design_geometry_package_pass': not errors, 'errors': errors,
        'motor_quantity': 3, 'motor_on_X_carriage': False, 'motor_on_Y_head': False,
        'XY_racks_removed': True, 'base_depth_reduction_mm': 60, 'Y_guide_spacing_mm': 52,
        'drawing_pages': drawing['page_count'], 'regressions': count, 'static_collisions': len(checks['static_collisions']),
        'motion_poses': checks['motion']['pose_count'], 'support_interfaces': len(checks['support_checks']),
        'tensioner_limit_geometry_pass': checks['tensioner_limits']['geometry_pass'],
        'flat_step_solids': checks['flat_STEP']['solids'],
        'print_types': sum(r['process'] == 'print' for r in manifest['parts']),
        'print_quantity': sum(r['quantity'] for r in manifest['parts'] if r['process'] == 'print'),
        'target_payload_kg': 1, 'hardware_accepted': False, 'loaded_operation_allowed': False,
        'machining_release_allowed': False, 'solidworks_gui_import_verified': False,
        'independent_brake_selected': False, 'control_firmware_implemented': False,
        'all_fasteners_modeled': False, 'prior_delivery_files_checked_unchanged': old_count}
    (OUT/'delivery_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if errors: raise RuntimeError(errors)
    files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.suffix != '.zip' and p.name != 'SHA256SUMS.txt')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.relative_to(OUT)}' for p in files)+'\n')
    sources = set(DEPENDENCIES)
    sources.update(p for p in Path(__file__).parent.glob('*.py'))
    sources.update([BASE/'delivery_audit.json', ROOT/'cad/powered_mvp/validate_powered.py', ROOT/'cad/powered_mvp/requirements.lock.txt',
        ROOT/'cad/v03_1/validate_v03_1.py', ROOT/'cad/v03/verify_motion.py', ROOT/'cad/v03/engineering_checks.py',
        ROOT/'cad/manual_mvp/drawings.py', ROOT/'cad/manual_mvp/manual_3axis.py', ROOT/'同步带优化MVP_E02_先读我.md'])
    path = OUT/'同步带单库位MVP_E02_机械设计包.zip'
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for p in [*files, OUT/'SHA256SUMS.txt', *sorted(sources)]: z.write(p, str(p.relative_to(ROOT)))
    with ZipFile(path) as z:
        if z.testzip() is not None: raise RuntimeError('ZIP CRC failed')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print('ZIP', path, 'bytes', path.stat().st_size, flush=True)


if __name__ == '__main__':
    main()
