"""Independent exported STEP/STL and evidence audit; never grants hardware release."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import cadquery as cq
from asrs_v03 import OUT,FINGERPRINT
from audit_delivery import audit_stl


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive-stale',action='store_true');args=ap.parse_args()
    errors=[];archived=[]
    manifest=json.loads((OUT/'manifest.json').read_text())
    evidence={}
    for file in ('manifest.json','static_validation.json','motion_validation.json','engineering_checks.json'):
        value=json.loads((OUT/file).read_text());evidence[file]=value
        if value.get('fingerprint')!=FINGERPRINT:errors.append(file+' fingerprint differs')
    if not evidence['static_validation.json']['static_pass']:errors.append('static geometry failed')
    if not evidence['motion_validation.json']['sampled_packaging_pass']:errors.append('sampled packaging failed')
    mh=hashlib.sha256(Path(__file__).with_name('verify_motion.py').read_bytes()).hexdigest()
    if evidence['motion_validation.json'].get('verifier_sha256')!=mh:errors.append('motion verifier changed')
    suite=ET.parse(OUT/'tests.xml').getroot();suites=list(suite.iter('testsuite'))
    tests=sum(int(s.get('tests',0)) for s in suites)
    if tests<23 or any(int(s.get('errors',0))+int(s.get('failures',0)) for s in suites):errors.append('regressions missing or failed')
    properties={p.get('name'):p.get('value') for p in suite.iter('property')}
    if properties.get('geometry_fingerprint')!=FINGERPRINT:errors.append('tests geometry fingerprint differs')
    for name in ('test_v03.py','control_contract.py'):
        if properties.get(name+'_sha256')!=hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest():
            errors.append('tested source changed '+name)
    expected={p['name'] for p in manifest['parts']};printed={p['name'] for p in manifest['parts'] if p['process']=='print'}
    for sub,suffix,names in (('parts','.step',expected),('stl','.stl',printed)):
        for path in (OUT/sub).glob('*'+suffix):
            if path.stem not in names:
                if args.archive_stale:
                    dst=OUT/'superseded_generated'/sub/path.name;dst.parent.mkdir(parents=True,exist_ok=True)
                    if dst.exists():raise FileExistsError(dst)
                    path.rename(dst);archived.append(str(dst.relative_to(OUT)))
                else:errors.append('obsolete artifact in active directory '+str(path))
    parts=[];meshes=[]
    for n,p in enumerate(manifest['parts'],1):
        path=OUT/'parts'/(p['name']+'.step');s=cq.importers.importStep(str(path)).val()
        b=s.BoundingBox();raw_ext=[b.xlen,b.ylen,b.zlen]
        # The manifest was measured after STL export. OCC's display bounds include
        # mesh deflection (up to ~0.004 mm here), unlike a fresh STEP's analytic box.
        # Reproduce the same mesh before comparing; do not silently loosen fit tolerances.
        if p['process']=='print':s.tessellate(.03,.10)
        b=s.BoundingBox();ext=[b.xlen,b.ylen,b.zlen]
        ok=(s.isValid() and len(s.Solids())==p['solids']
            and abs(s.Volume()-p['volume_mm3'])<=max(.0001,p['volume_mm3']*1e-6)
            and max(abs(a-b) for a,b in zip(ext,p['extents_mm']))<.001)
        parts.append({'name':p['name'],'pass':ok,'solids':len(s.Solids()),
            'raw_step_extents_mm':raw_ext,'comparable_export_bounds_mm':ext,
            'max_extent_difference_mm':max(abs(a-b) for a,b in zip(ext,p['extents_mm'])),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if not ok:errors.append('STEP readback '+p['name'])
        if p['process']=='print':
            row=audit_stl(OUT/'stl'/(p['name']+'.stl'));row['name']=p['name']
            row['volume_relative_error']=abs(row['volume_mm3']-s.Volume())/s.Volume()
            row['pass']=(row['watertight'] and row['winding_consistent'] and row['connected_bodies']==1
                and row['fits_a1'] and row['volume_relative_error']<.02)
            if not row['pass']:errors.append('STL mesh '+p['name'])
            meshes.append(row)
        if n%20==0:print('PART_ROUNDTRIP',n,'/',len(manifest['parts']),flush=True)
    byname={p['name']:p for p in manifest['parts']}
    expected_solids=sum(byname[i['part']]['solids'] for i in manifest['instances'])
    expected_volume=sum(byname[i['part']]['volume_mm3'] for i in manifest['instances'])
    s=cq.importers.importStep(str(OUT/'ASRS_Modular_V03.step')).val();b=s.BoundingBox()
    assembly={'valid':s.isValid(),'solid_count':len(s.Solids()),'expected_solids':expected_solids,
        'extents_mm':[b.xlen,b.ylen,b.zlen],'volume_mm3':s.Volume(),
        'file_sha256':hashlib.sha256((OUT/'ASRS_Modular_V03.step').read_bytes()).hexdigest()}
    assembly['pass']=assembly['valid'] and assembly['solid_count']==expected_solids and abs(s.Volume()-expected_volume)<expected_volume*1e-6
    if not assembly['pass']:errors.append('assembly STEP readback')
    tags=json.loads((OUT/'markers/marker_manifest.json').read_text())
    for tag in tags['tags']:
        path=OUT/'markers'/f'tag36h11_{tag["id"]:03d}_source.png'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=tag['source_sha256']:errors.append('marker source changed '+tag['label'])
    report={'fingerprint':FINGERPRINT,'prototype_geometry_deliverable_pass':not errors,'errors':errors,
        'part_types':len(parts),'instances':len(manifest['instances']),'printable_types':len(meshes),
        'regression_test_count':tests,'motion_pose_count':evidence['motion_validation.json']['pose_count'],
        'assembly_step_readback':assembly,'part_step_readbacks':parts,'stl_mesh_checks':meshes,
        'marker_count':len(tags['tags']),'archived_obsolete_artifacts':archived,
        'native_assembly_completed':False,'camera_hardware_decode_test_passed':False,
        'wireless_firmware_implemented':False,'hardware_accepted':False,'manufacturing_release_allowed':False,
        'release_blockers':evidence['engineering_checks.json']['blockers']}
    (OUT/'delivery_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ('prototype_geometry_deliverable_pass','errors','part_types','instances',
        'printable_types','regression_test_count','motion_pose_count','manufacturing_release_allowed')},indent=2),flush=True)
    return int(bool(errors))


if __name__=='__main__':raise SystemExit(main())
