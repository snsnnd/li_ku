"""Generate a genuinely smaller LAYOUT-ONLY STEP from audited V03 exports.

No engineering STEP, STL, geometry generator, or acceptance evidence is overwritten.
Motors and pinions become labelled proxies; actual rack tooth profiles remain visible.
"""
import hashlib
import json
from pathlib import Path

import cadquery as cq

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'model'/'V03'


def box(x,y,z,w,d,h):
    return cq.Solid.makeBox(w,d,h,cq.Vector(x-w/2,y-d/2,z))


def cyl(r,h,z=0):
    return cq.Solid.makeCylinder(r,h,cq.Vector(0,0,z))


def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    audit=json.loads((OUT/'delivery_audit.json').read_text())
    source=OUT/'ASRS_Modular_V03.step'
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if not audit['prototype_geometry_deliverable_pass'] or audit['fingerprint']!=manifest['fingerprint']:
        raise ValueError('Only an audited geometry baseline may be used')
    if source_hash!=audit['assembly_step_readback']['file_sha256']:
        raise ValueError('Engineering assembly changed since audit')
    source_parts={p['name']:p['sha256'] for p in audit['part_step_readbacks']}
    parts={};simplified=[];omitted=[]
    colours={'aluminum':(.64,.69,.73),'steel':(.28,.33,.38),'PETG':(.15,.61,.78),
        'purchased':(.25,.29,.34),'safety':(.90,.28,.15),'rubber':(.12,.14,.16)}
    metadata={p['name']:p for p in manifest['parts']}
    for p in manifest['parts']:
        name=p['name']
        if p['material']=='guard':continue
        if name.startswith('ZDT_RealMotor_'):
            # Conservative complete-body/driver envelope plus pilot and actual shaft size.
            normal=box(1.325,-10.45,-59,44.65,62.9,59).fuse(cyl(11,2),cyl(2.5,22,2))
            shape=normal.rotate((0,0,0),(1,0,0),90 if name.endswith('_Z') else 180)
            simplified.append({'part':name,'replacement':'body/driver envelope + pilot + shaft; no detailed electronics'})
        elif name.startswith('Pinion_M1p5_20T_'):
            shape=cyl(16.5,12).cut(cyl(6.1,14,-1))
            if name.endswith('_Z'):shape=shape.rotate((0,0,0),(1,0,0),90)
            simplified.append({'part':name,'replacement':'outer-diameter ring, not a printable tooth profile'})
        else:
            path=OUT/'parts'/(name+'.step')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=source_parts[name]:raise ValueError('Part changed '+name)
            shape=cq.importers.importStep(str(path)).val()
        parts[name]=shape
    assembly=cq.Assembly(name='V03_LIGHT_LAYOUT_ONLY_NOT_FOR_MANUFACTURE')
    expected_solids=0;included=[]
    for i in manifest['instances']:
        p=metadata[i['part']]
        if p['material']=='guard':omitted.append(i['name']);continue
        color=colours.get(p['material'],(.65,.65,.60))
        if p['process']=='candidate':color=(.95,.56,.12)
        # Reuse part definitions, rather than exporting a new translated body for every instance.
        assembly.add(parts[p['name']],name=i['name'],loc=cq.Location(cq.Vector(*i['origin_mm'])),color=cq.Color(*color))
        expected_solids+=len(parts[p['name']].Solids());included.append(i['name'])
    target=OUT/'viewing'/'ASRS_V03_LIGHT_VIEW.step'
    assembly.save(str(target))
    result=cq.importers.importStep(str(target)).val();b=result.BoundingBox()
    report={'purpose':'LAYOUT VIEW ONLY - NOT FOR MANUFACTURE OR PRINTING','source_fingerprint':manifest['fingerprint'],
        'source_assembly_sha256':source_hash,'source_bytes':source.stat().st_size,'view_bytes':target.stat().st_size,
        'file':target.name,'file_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'included_instances':len(included),'omitted_guard_instances':omitted,'simplified_parts':simplified,
        'actual_rack_teeth_retained':True,'geometry_valid':result.isValid(),
        'solid_count':len(result.Solids()),'expected_solids':expected_solids,
        'extents_mm':[b.xlen,b.ylen,b.zlen],'solidworks_display_verified':False,'manufacturing_release_allowed':False}
    report['readback_pass']=report['geometry_valid'] and report['solid_count']==expected_solids
    (target.parent/'light_view_readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['readback_pass']:raise RuntimeError('Light view readback failed')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
