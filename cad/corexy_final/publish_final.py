"""Audit and package only the latest C04 review delivery; never release hardware."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile,ZIP_DEFLATED

import pymupdf

from corexy_final import ROOT,OUT,BASE,FINGERPRINT,DEPENDENCIES


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    manifest=json.loads((OUT/'manifest.json').read_text());checks=json.loads((OUT/'validation.json').read_text())
    drawing=json.loads((OUT/'drawings/manifest.json').read_text());preview=json.loads((OUT/'previews/manifest.json').read_text());errors=[]
    for name,r in [('model',manifest),('validation',checks),('drawings',drawing),('previews',preview)]:
        if r['fingerprint']!=FINGERPRINT:errors.append(name+' stale')
        if r.get('loaded_operation_allowed',False) or r.get('manufacturing_release_allowed',False) or r.get('hardware_accepted',False):errors.append(name+' unsafe release')
    if not checks['mechanical_geometry_package_pass']:errors.append('geometry failed')
    if checks['validator_sha256']!=sha(Path(__file__).with_name('validate_final.py')):errors.append('validator changed')
    for name,r in [('drawings',drawing),('previews',preview)]:
        if r['generator_sha256']!=sha(Path(__file__).with_name('deliver_final.py')):errors.append(name+' generator changed')
    pdfpath=OUT/'drawings'/drawing['file']
    if sha(pdfpath)!=drawing['sha256']:errors.append('PDF changed')
    with pymupdf.open(pdfpath) as pdf:
        if len(pdf)!=drawing['page_count']:errors.append('page count')
        for n,p in enumerate(pdf,1):
            if 'C04' not in p.get_text():errors.append(f'page{n} missing C04')
            for b in p.get_text('dict')['blocks']:
                for line in b.get('lines',[]):
                    for span in line['spans']:
                        x0,y0,x1,y1=span['bbox']
                        if x0<0 or y0<0 or x1>p.rect.width or y1>p.rect.height:errors.append(f'page{n} text outside paper')
    for name,h in preview['images'].items():
        if sha(OUT/'previews'/name)!=h:errors.append('preview changed '+name)
    count=0
    for suite in ET.parse(OUT/'tests.xml').getroot().iter('testsuite'):
        count+=int(suite.get('tests',0));props={p.get('name'):p.get('value') for p in suite.findall('./properties/property')}
        if sum(int(suite.get(k,0)) for k in ('failures','errors','skipped')):errors.append('regressions failed/skipped')
        if props.get('fingerprint')!=FINGERPRINT or props.get('test_source_sha256')!=sha(Path(__file__).with_name('test_final.py')):errors.append('regression source binding stale')
    if count<18:errors.append('tests missing')
    if checks['motion']['pose_count']!=244 or not checks['motion']['sampled_geometry_pass']:errors.append('full motion missing/failed')
    if sha(OUT/'viewing/CoreXY_C04_SOLIDS_AP203.step')!=checks['flat_STEP']['sha256']:errors.append('STEP changed')
    for r in checks['mesh_checks']:
        if sha(OUT/'stl'/(r['code']+'.stl'))!=r['sha256']:errors.append(r['code']+' STL changed')
    supplier=json.loads((OUT/'references/supplier_sources.json').read_text())
    for r in supplier['sources']:
        if sha(OUT/'references'/r['file'])!=r['sha256']:errors.append('supplier document changed')
    names={i['name']:i for i in manifest['instances']}
    if sum(n.startswith('beam_mount_') for n in names)!=8:errors.append('beam screw count')
    for name,i in names.items():
        if name.startswith('beam_mount_') and (i['group']!='gantry' or any(name in (c['a'],c['b']) for c in manifest['allowed_contacts'])):errors.append('beam screw group/contact bypass')
    for name in ('README.md','采购补充与未完成项.md','BOM.csv','打印清单.csv','采购与金属加工清单.csv'):
        if not (OUT/name).is_file():errors.append('missing '+name)
    sources=set(DEPENDENCIES);sources.update(Path(__file__).parent.glob('*.py'))
    sources.update([BASE/'delivery_audit.json',ROOT/'cad/corexy_mvp/validate_corexy.py',ROOT/'cad/powered_mvp/requirements.lock.txt',ROOT/'cad/manual_mvp/drawings.py'])
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            p=Path(file).resolve()
            if p.is_relative_to(ROOT/'cad') and p.suffix=='.py':sources.add(p)
    (OUT/'source_dependencies.json').write_text(json.dumps({'fingerprint':FINGERPRINT,'requires_repository_and_git_lfs':True,'files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)}},ensure_ascii=False,indent=2))
    audit={'fingerprint':FINGERPRINT,'mechanical_design_review_package_pass':not errors,'errors':errors,
        'drawing_pages':drawing['page_count'],'regressions':count,'motion_poses':checks['motion']['pose_count'],
        'static_collisions':len(checks['static_collisions']),'support_interfaces':len(checks['support_checks']),
        'flat_step_solids':checks['flat_STEP']['solids'],'part_types':len(manifest['parts']),'instances':len(manifest['instances']),
        'print_types':sum(p['process']=='print' for p in manifest['parts']),'print_quantity':sum(p['quantity'] for p in manifest['parts'] if p['process']=='print'),
        'payload_target_kg':1,'manufacturing_release_allowed':False,'hardware_accepted':False,'loaded_operation_allowed':False,
        'automatic_brake_selected':False,'control_firmware_implemented':False,'all_fasteners_reviewed':False,'solidworks_GUI_import_verified':False,
        'scope':'C04 mechanical geometry review only; latest-version package does not duplicate historical deliveries.'}
    (OUT/'delivery_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    if errors:raise RuntimeError(errors)
    files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.suffix!='.zip' and p.name!='SHA256SUMS.txt')
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.relative_to(OUT)}' for p in files)+'\n')
    path=OUT/'CoreXY机械收敛_C04_评审交付包.zip'
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        for p in [*files,OUT/'SHA256SUMS.txt',*sorted(Path(__file__).parent.glob('*.py'))]:z.write(p,str(p.relative_to(ROOT)))
    with ZipFile(path) as z:
        if z.testzip() is not None:raise RuntimeError('ZIP CRC failure')
    print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True);print('ZIP',path,'bytes',path.stat().st_size,flush=True)


if __name__=='__main__':main()
