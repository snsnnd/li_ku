"""Reject stale/failed evidence, hash final E01 files and package the design."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf

from powered_mvp import ROOT, OUT, FINGERPRINT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    checks = json.loads((OUT/'validation.json').read_text())
    drawings = json.loads((OUT/'drawings/manifest.json').read_text())
    errors = []
    for label, data in [('model', manifest), ('validation', checks), ('drawings', drawings)]:
        if data['fingerprint'] != FINGERPRINT: errors.append(label+' fingerprint stale')
    if not checks['geometry_deliverable_pass']: errors.append('geometry deliverable failed')
    if checks['validator_sha256'] != sha(Path(__file__).with_name('validate_powered.py')):
        errors.append('validator changed since run')
    if drawings['generator_sha256'] != sha(Path(__file__).with_name('deliver_powered.py')):
        errors.append('drawing generator changed since run')
    pdf_path = OUT/'drawings'/drawings['file']
    if sha(pdf_path) != drawings['sha256']: errors.append('PDF changed')
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != drawings['page_count']: errors.append('PDF page mismatch')
        for n, page in enumerate(pdf, 1):
            if 'E01' not in page.get_text(): errors.append(f'PDF page{n} missing E01 label')
            if not page.get_fonts(full=True): errors.append(f'PDF page{n} no font')
    tests = ET.parse(OUT/'tests.xml').getroot()
    count = 0
    for suite in tests.iter('testsuite'):
        count += int(suite.get('tests', 0))
        if sum(int(suite.get(k, 0)) for k in ('failures', 'errors', 'skipped')):
            errors.append('regression failed/skipped')
    if count < 9: errors.append('missing regressions')
    if sha(OUT/'viewing/Powered_MVP_E01_SOLIDS_AP203.step') != checks['flat_STEP']['sha256']:
        errors.append('flat STEP changed')
    for r in checks['mesh_checks']:
        if sha(OUT/'stl'/(r['code']+'.stl')) != r['sha256']: errors.append(r['code']+' mesh changed')
    for name in ('README.md', '打印清单.csv', '采购与金属加工清单.csv', '采购补充与未选型项.md'):
        if not (OUT/name).is_file(): errors.append('missing '+name)
    preserved_count = 0
    preserved = Path('/tmp/opencode/e01_preserved_hashes.json')
    if preserved.exists():
        for relative, expected in json.loads(preserved.read_text()).items():
            preserved_count += 1
            if not (ROOT/relative).is_file() or sha(ROOT/relative) != expected:
                errors.append('prior delivery changed: '+relative)
    report = {'fingerprint': FINGERPRINT, 'design_geometry_package_pass': not errors,
              'errors': errors, 'drawing_pages': drawings['page_count'], 'regressions': count,
              'static_collisions': len(checks['static_collisions']), 'support_interfaces': len(checks['support_checks']),
              'motion_poses': checks['motion']['pose_count'], 'model_contains_motors': True, 'motor_quantity': 3,
              'print_types': sum(r['process'] == 'print' for r in manifest['parts']),
              'print_quantity': sum(r['quantity'] for r in manifest['parts'] if r['process'] == 'print'),
              'flat_step_solids': checks['flat_STEP']['solids'], 'target_payload_kg': 1,
              'hardware_accepted': False, 'loaded_operation_allowed': False, 'machining_release_allowed': False,
              'solidworks_gui_import_verified': False, 'independent_brake_selected': False,
              'all_fasteners_modeled': False, 'control_firmware_implemented': False,
              'prior_delivery_files_checked_unchanged': preserved_count}
    (OUT/'delivery_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if errors: raise RuntimeError(errors)
    # List the precise source/evidence used in the ZIP, excluding ZIP/hash files.
    paths = [p for p in OUT.rglob('*') if p.is_file() and p.suffix != '.zip' and p.name != 'SHA256SUMS.txt']
    source = [p for p in Path(__file__).parent.glob('*') if p.is_file() and p.suffix in ('.py', '.txt')]
    # Include frozen donors too, so the generated CAD can be rebuilt elsewhere.
    source += [ROOT/'cad/v03_1/asrs_v03_1.py', ROOT/'cad/v03_1/validate_v03_1.py',
               ROOT/'cad/v03/asrs_v03.py', ROOT/'cad/v03/gears.py', ROOT/'cad/v03/verify_motion.py',
               ROOT/'cad/v03/engineering_checks.py', ROOT/'cad/v02/asrs_v02.py',
               ROOT/'cad/manual_mvp/drawings.py', ROOT/'cad/manual_mvp/manual_3axis.py',
               ROOT/'stl/ZDT_X42_L48Motor.STEP']
    sums = '\n'.join(f'{sha(p)}  {p.relative_to(OUT)}' for p in sorted(paths))+'\n'
    (OUT/'SHA256SUMS.txt').write_text(sums)
    zip_path = OUT/'电驱单库位MVP_E01_机械设计包.zip'
    with ZipFile(zip_path, 'w', ZIP_DEFLATED) as z:
        for p in [*paths, OUT/'SHA256SUMS.txt']:
            z.write(p, str(p.relative_to(ROOT)))
        for p in source:
            z.write(p, str(p.relative_to(ROOT)))
        z.write(ROOT/'电驱单库位MVP_先读我.md', '电驱单库位MVP_先读我.md')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('ZIP', zip_path, 'bytes', zip_path.stat().st_size)


if __name__ == '__main__':
    main()
