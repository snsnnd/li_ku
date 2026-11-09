"""Bind final drawings/models/evidence and create a self-contained print ZIP."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf

from manual_3axis import OUT, FINGERPRINT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    errors = []
    manifest = json.loads((OUT/'manifest.json').read_text())
    validation = json.loads((OUT/'validation.json').read_text())
    drawing = json.loads((OUT/'drawings/manifest.json').read_text())
    for name, data in [('manifest', manifest), ('validation', validation), ('drawing', drawing)]:
        if data['fingerprint'] != FINGERPRINT:
            errors.append(name+' fingerprint differs')
    if not validation['geometry_deliverable_pass'] or validation['errors']:
        errors.append('geometry/mesh/motion check failed')
    if not all(r['geometric_seat_pass'] for r in validation['structural_support_checks']):
        errors.append('load path mating face failed')
    if validation['validator_sha256'] != sha(Path(__file__).with_name('verify_manual.py')):
        errors.append('validator changed')
    if drawing['drawing_generator_sha256'] != sha(Path(__file__).with_name('drawings.py')):
        errors.append('drawing source changed')
    pdf_path = OUT/'drawings'/drawing['file']
    if sha(pdf_path) != drawing['sha256']:
        errors.append('PDF changed')
    doc = pymupdf.open(pdf_path)
    if len(doc) != 35 or len(doc) != drawing['page_count']:
        errors.append('drawing page count')
    expected = {p['code'] for p in manifest['parts'] if p['process'] == 'print'}
    if expected != set(drawing['pages'])-{'A01', 'A02', 'S01', 'S02', 'B01'}:
        errors.append('missing part drawing')
    if not all(abs(page.rect.width-420*72/25.4) < .1 and abs(page.rect.height-297*72/25.4) < .1 for page in doc):
        errors.append('drawing page size')
    if 'Ø' not in doc[5].get_text():
        errors.append('diameter glyph missing')
    for page in doc:
        if '\ufffd' in page.get_text():
            errors.append('PDF contains replacement glyph')
    # Retain a few final raster previews of the actual PDF for convenient review.
    for n in (0, 3, 5, 12):
        doc[n].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2)).save(str(OUT/'drawings'/f'check_page_{n+1:02d}.png'))
    doc.close()

    tree = ET.parse(OUT/'tests.xml').getroot()
    props = {p.get('name'): p.get('value') for p in tree.iter('property')}
    if props.get('geometry_fingerprint') != FINGERPRINT:
        errors.append('regression geometry fingerprint')
    for name in ('test_manual.py', 'verify_manual.py'):
        if props.get(name+'_sha256') != sha(Path(__file__).with_name(name)):
            errors.append('regression source differs '+name)
    suites = list(tree.iter('testsuite'))
    tests = sum(int(s.get('tests', 0)) for s in suites)
    if tests < 12 or any(int(s.get('errors', 0))+int(s.get('failures', 0))+int(s.get('skipped', 0)) for s in suites):
        errors.append('regressions missing/failed/skipped')
    for row in validation['step_checks']:
        if sha(OUT/'parts'/(row['code']+'.step')) != row['sha256']:
            errors.append('part changed '+row['code'])
    for row in validation['mesh_checks']:
        if sha(OUT/'stl'/(row['code']+'.stl')) != row['sha256']:
            errors.append('STL changed '+row['code'])
    if sha(OUT/'Manual_3Axis_Assembly.step') != validation['assembly_step']['sha256']:
        errors.append('assembly changed')
    for name in ('README.md', '打印清单.csv', '五金清单.csv'):
        if not (OUT/name).is_file():
            errors.append('missing '+name)
    compatibility = None
    compat_path = OUT/'viewing/compatibility_readback.json'
    if compat_path.exists():
        compatibility = json.loads(compat_path.read_text())
        if (compatibility['source_fingerprint'] != FINGERPRINT
                or compatibility['source_sha256'] != sha(OUT/'Manual_3Axis_Assembly.step')
                or not compatibility['readback_pass'] or compatibility['solid_count'] != 93
                or compatibility['assembly_occurrences'] != 0):
            errors.append('compatibility model stale or invalid')
        if sha(OUT/'viewing'/compatibility['file']) != compatibility['sha256']:
            errors.append('compatibility STEP changed')
        if sha(OUT/'viewing'/compatibility['view_mesh']['file']) != compatibility['view_mesh']['sha256']:
            errors.append('compatibility viewing mesh changed')
        compat_tests = ET.parse(OUT/'viewing/compatibility_tests.xml').getroot()
        if any(int(s.get('errors', 0))+int(s.get('failures', 0))+int(s.get('skipped', 0))
               for s in compat_tests.iter('testsuite')):
            errors.append('compatibility regressions failed')
    report = {'fingerprint': FINGERPRINT, 'geometry_drawings_deliverable_pass': not errors, 'errors': errors,
              'drawing_pages': len(drawing['pages']), 'printed_types': len(expected),
              'printed_quantity_including_coupons': sum(p['quantity'] for p in manifest['parts'] if p['process'] == 'print'),
              'regressions': tests, 'motion_poses': validation['motion_pose_count'],
              'support_interfaces': len(validation['structural_support_checks']),
              'all_prints_fit_256': all(max(m['print_extents_mm']) <= 256 for m in validation['mesh_checks']),
              'model_contains_motors': False, 'hardware_accepted': False, 'loaded_operation_allowed': False,
              'payload_allowed_kg': 0, 'pdf_sha256': sha(pdf_path),
              'flat_compatibility_export_included': compatibility is not None,
              'solidworks_gui_import_verified': False,
              'note': 'CAD, drawings and packaging consistency only; not physical guide fit, load rating or automatic fall arrest.'}
    (OUT/'delivery_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 1
    target = OUT/'手动三轴验证装置_M01_打印包.zip'
    with ZipFile(target, 'w', ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                z.write(path, '手动三轴验证装置_M01/'+path.relative_to(OUT).as_posix())
    with ZipFile(target) as z:
        if z.testzip() is not None:
            raise RuntimeError('ZIP CRC check failed')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print('PRINT ZIP', target, 'bytes', target.stat().st_size, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
