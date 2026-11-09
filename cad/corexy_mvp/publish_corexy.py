"""Audit C03 design-review geometry/evidence without implying manufacturing release."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile,ZIP_DEFLATED

import pymupdf

from corexy_mvp import ROOT,OUT,BASE,FINGERPRINT,DEPENDENCIES


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    manifest=json.loads((OUT/'manifest.json').read_text());checks=json.loads((OUT/'validation.json').read_text());drawing=json.loads((OUT/'drawings/manifest.json').read_text());errors=[]
    for name,r in [('model',manifest),('validation',checks),('drawings',drawing)]:
        if r['fingerprint']!=FINGERPRINT:errors.append(name+' stale')
    if not checks['geometry_deliverable_pass']:errors.append('geometry failed')
    if checks['validator_sha256']!=sha(Path(__file__).with_name('validate_corexy.py')):errors.append('validator changed')
    if drawing['generator_sha256']!=sha(Path(__file__).with_name('deliver_corexy.py')):errors.append('drawing generator changed')
    pdfpath=OUT/'drawings'/drawing['file']
    if sha(pdfpath)!=drawing['sha256']:errors.append('PDF changed')
    with pymupdf.open(pdfpath) as pdf:
        if len(pdf)!=drawing['page_count']:errors.append('page count')
        for n,p in enumerate(pdf,1):
            if 'C03' not in p.get_text():errors.append(f'page{n} missing C03')
            for b in p.get_text('dict')['blocks']:
                for line in b.get('lines',[]):
                    for span in line['spans']:
                        x0,y0,x1,y1=span['bbox']
                        if x0<0 or y0<0 or x1>p.rect.width or y1>p.rect.height:errors.append(f'page{n} text outside paper')
    count=0
    for suite in ET.parse(OUT/'tests.xml').getroot().iter('testsuite'):
        count+=int(suite.get('tests',0))
        if sum(int(suite.get(k,0)) for k in ('failures','errors','skipped')):errors.append('regressions failed/skipped')
    if count<16:errors.append('tests missing')
    if sha(OUT/'viewing/CoreXY_Fork_C03_SOLIDS_AP203.step')!=checks['flat_STEP']['sha256']:errors.append('STEP changed')
    for r in checks['mesh_checks']:
        if sha(OUT/'stl'/(r['code']+'.stl'))!=r['sha256']:errors.append(r['code']+' STL changed')
    for name in ('README.md','采购补充与未完成项.md','打印清单.csv','采购与金属加工清单.csv'):
        if not (OUT/name).is_file():errors.append('missing '+name)
    old_count=0;preserved=Path('/tmp/opencode/c03_preserved_hashes.json')
    if preserved.exists():
        for n,h in json.loads(preserved.read_text()).items():
            old_count+=1
            if not (ROOT/n).is_file() or sha(ROOT/n)!=h:errors.append('prior delivery changed '+n)
    r={'fingerprint':FINGERPRINT,'architecture_geometry_review_package_pass':not errors,'errors':errors,
        'motor_quantity':3,'AB_motors_fixed':True,'independent_Y_pusher_removed':True,'fork_cells_rebuilt':True,
        'drawing_pages':drawing['page_count'],'regressions':count,'motion_poses':checks['motion']['pose_count'],
        'static_collisions':len(checks['static_collisions']),'support_interfaces':len(checks['support_checks']),
        'CoreXY_mapping_pass':checks['kinematics']['geometry_mapping_pass'],'flat_step_solids':checks['flat_STEP']['solids'],
        'print_types':sum(p['process']=='print' for p in manifest['parts']),
        'print_quantity':sum(p['quantity'] for p in manifest['parts'] if p['process']=='print'),
        'payload_target_kg':1,'hardware_accepted':False,'loaded_operation_allowed':False,'machining_release_allowed':False,
        'actual_belt_clamp_and_tensioner_detail_complete':False,'actual_idler_and_drive_hub_selected':False,
        'automatic_brake_selected':False,'control_firmware_implemented':False,'all_fasteners_modeled':False,
        'solidworks_gui_import_verified':False,'prior_delivery_files_checked_unchanged':old_count}
    (OUT/'delivery_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    if errors:raise RuntimeError(errors)
    files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.suffix!='.zip' and p.name!='SHA256SUMS.txt')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.relative_to(OUT)}' for p in files)+'\n')
    sources=set(DEPENDENCIES);sources.update(Path(__file__).parent.glob('*.py'))
    sources.update([ROOT/'cad/powered_mvp/requirements.lock.txt',ROOT/'cad/v03_1/validate_v03_1.py',ROOT/'cad/v03/engineering_checks.py',ROOT/'cad/v03/verify_motion.py',
        ROOT/'cad/manual_mvp/drawings.py',ROOT/'cad/manual_mvp/manual_3axis.py',ROOT/'CoreXY整体重构_C03_先读我.md',ROOT/'文档/CoreXY_EP_V3_参考评估.md'])
    path=OUT/'CoreXY整机重构_C03_机械设计包.zip'
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        for p in [*files,OUT/'SHA256SUMS.txt',*sorted(sources)]:z.write(p,str(p.relative_to(ROOT)))
    with ZipFile(path) as z:
        if z.testzip() is not None:raise RuntimeError('ZIP CRC failure')
    print(json.dumps(r,ensure_ascii=False,indent=2),flush=True);print('ZIP',path,'bytes',path.stat().st_size,flush=True)


if __name__=='__main__':main()
