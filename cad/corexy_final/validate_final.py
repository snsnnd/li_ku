"""C04 exact mechanical checks with relative-pose caching; full244 path rerun."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import cadquery as cq
import trimesh

from corexy_final import OUT,BASE,ROOT,FINGERPRINT,build_model,export,Item,v2,prior,box,cyl,fuse,drill,hz,free_length,HOME_X,HOME_Y,CELL_Z,IO_Z
sys.path.insert(0,str(ROOT/'cad/corexy_mvp'))
import validate_corexy as previous


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def logical_group(i):
    if i.name in ('motor_A_pulley','motor_A_pinch'):return 'rotA'
    if i.name in ('motor_B_pulley','motor_B_pinch'):return 'rotB'
    if i.name in prior.e01.ROTATING_Z:return 'screw'
    return i.group


def translation(i,p):
    g=i.group
    if g=='fixed':return (0,0,0)
    if g=='gantry':return (0,p['dy'],0)
    if g in ('xy','pin'):return (p['dx'],p['dy'],0)
    if g=='lift':return (p['dx'],p['dy'],p['dz'])
    if g=='bin':return (p['bin_pose'][0]-HOME_X,p['bin_pose'][1]-(HOME_Y+155),p['bin_pose'][2]-CELL_Z)
    if g=='door':return (0,0,90*p['door'])
    return (0,0,0)


def phase(i,p):
    g=logical_group(i)
    if g=='rotA':return round(((p['dx']+p['dy'])*9)%360,6)
    if g=='rotB':return round(((-p['dx']+p['dy'])*9)%360,6)
    if g=='screw':return round((p['dz']*180)%360,6)
    if g=='belt':return (p['dx'],p['dy'])
    return None


def motion(m):
    items=[]
    for i in m.items:
        if i.name=='maintenance_pin':continue
        p=i.part
        if p.name.startswith('ZDT_RealMotor'):
            s=fuse(box(1.325,-10.45,-59,44.65,62.9,59),cyl(0,0,0,11,2),cyl(0,0,2,2.5,22))
            s=drill(s,[hz(a,b,-6,2.5,8) for a in (-15.5,15.5) for b in (-15.5,15.5)])
            if 'AB_Up' not in p.name:s=s.rotate((0,0,0),(1,0,0),180)
            p=replace(p,shape=s)
        items.append(Item(i.name,p,i.origin,i.group))
    results=[];tests=0;cache_hits=0;cache={};shape_cache={};start=time.monotonic()
    poses=previous.poses()
    for n,p in enumerate(poses,1):
        args={k:v for k,v in p.items() if k!='phase'};located=[]
        for i in items:
            t=translation(i,p);ph=phase(i,p);key=(i.name,t,ph)
            if key not in shape_cache:shape_cache[key]=i.located(**args,fast_belt=True)
            s=shape_cache[key];located.append((i,s,v2.bbox(s),t,ph))
        bad=[]
        for k,(a,sa,ba,ta,pa) in enumerate(located):
            for b,sb,bb,tb,pb in located[k+1:]:
                if logical_group(a)==logical_group(b) or tuple(sorted((a.name,b.name))) in m.allowed or not v2.overlaps(ba,bb):continue
                rel=tuple(round(x-y,6) for x,y in zip(ta,tb));key=(a.name,b.name,rel,pa,pb)
                if key in cache:v=cache[key];cache_hits+=1
                else:
                    v=sa.intersect(sb).Volume();cache[key]=v;tests+=1
                if v>.02:bad.append({'a':a.name,'b':b.name,'volume_mm3':round(v,5)})
        if bad:
            results.append({'pose':p,'collisions':bad})
            if len(results)<=3:print('FIRST_MOTION_FAILURE '+json.dumps(results[-1]),flush=True)
        if n%40==0:print(f'C04 POSE {n}/{len(poses)} failures={len(results)} booleans={tests} cache_hits={cache_hits} seconds={time.monotonic()-start:.1f}',flush=True)
    return {'pose_count':len(poses),'failures':results,'sampled_geometry_pass':not results,'boolean_pair_tests':tests,'identical_relative_pose_cache_hits':cache_hits,
        'continuous_collision_detection':False,'maintenance_pin_removed':True,
        'method':'ALL244 C03 legal poses rerun on C04. Exact structures, conservative full motor envelopes, actual rotating pulley/pinch groups. Belt segments form equivalent unfused compound for motion tests, fused solids for exports. Cache only identical named pair/relative translation/rotation phase.',
        'path_constraints':'X/Z traverse retracted atY=-140; insertion only at aligned bay. Mixed XY aisle probes no farther thanY=-135. No sideways inserted travel; control firmware absent.'}


def stroke_checks(m):
    failures=[];tests=0
    changed={i.name for i in m.items if i.name.startswith(('terminal_A_L_','terminal_B_L_')) or i.group=='belt'}
    for ua,ub in [(0,0),(2,0),(0,2),(2,2)]:
        if ua==ub==0:continue
        rows=[]
        for i in m.items:
            s=i.located(tension_a=ua,tension_b=ub,fast_belt=True);rows.append((i,s,v2.bbox(s)))
        for k,(a,sa,ba) in enumerate(rows):
            for b,sb,bb in rows[k+1:]:
                if a.name not in changed and b.name not in changed:continue
                if tuple(sorted((a.name,b.name))) in m.allowed or not v2.overlaps(ba,bb):continue
                tests+=1;vol=sa.intersect(sb).Volume()
                if vol>.02:failures.append({'tension_a':ua,'tension_b':ub,'a':a.name,'b':b.name,'volume_mm3':round(vol,5)})
    return {'stroke_mm':[0,2],'combinations':[[0,0],[2,0],[0,2],[2,2]],'failures':failures,'geometry_pass':not failures,'boolean_tests':tests,
        'not_a_belt_stretch_instruction':True,'nominal_engagement_per_terminal_mm':18,'note':'Stroke checks hardware/slot/screw clearance, not selected belt prestrain or tension. Lock top screws after adjustment.'}


def interface_checks(m):
    out={}
    motor=find(m,'motor_B');shaft_tip=motor.origin[2]+motor.part.shape.BoundingBox().zmax
    pulley=find(m,'motor_B_pulley');bottom=pulley.origin[2]-6;top=pulley.origin[2]+9
    out['B_shaft_tip_Z_mm']=shaft_tip;out['B_shaft_in_pulley_mm']=min(shaft_tip,top)-max(motor.origin[2],bottom)
    out['lower_clamp_hub_length_mm']=6
    out['B_split_clamp_fully_on_shaft']=shaft_tip>=pulley.origin[2] and motor.origin[2]<=bottom
    out['terminal_top_screw_engagement_mm']=124-(132.9-16)
    out['terminal_pinch_screw_engagement_mm']=9.3-4.7
    out['beam_lower_wall_M4_engagement_mm']=4
    out['datum_M5_base_engagement_mm']=6
    out['checks_pass']=out['B_split_clamp_fully_on_shaft'] and out['B_shaft_in_pulley_mm']>=11.9 and out['terminal_top_screw_engagement_mm']>=6
    out['physical_torque_and_strength_verified']=False
    return out


def find(m,name):return next(i for i in m.items if i.name==name)


def connections(m):
    shapes={i.name:i.located() for i in m.items};rows=[]
    for j in m.joints:
        a,b=shapes[j['a']],shapes[j['b']];gap=a.distance(b)
        area=previous.mating_area(a,b) if gap<1e-5 else 0
        rows.append({**j,'gap_mm':gap,'mating_area_mm2':area,'geometric_seat_pass':gap<1e-5 and area>2})
    return rows


def engineering(m):
    r=previous.engineering(m);r['fingerprint']=FINGERPRINT
    worst=r['AB_motor_screen']['motor_force_worst_N'];t0=15
    r['belt_screen']={'reference':'Phidgets TRM4218_0 page lists working tensile27N; exact delivered belt conformity required',
        'reference_url':'https://www.phidgets.com/?prodid=839','reference_working_tensile_N':27,'pretension_example_N':t0,
        'nominal_worst_each_motor_tension_difference_N':worst,'SF2_tight_strand_example_N':t0+worst,
        'SF2_slack_strand_example_N':t0-worst,'example_within_reference_rating':t0+worst<27 and t0-worst>0,
        'pretension_selected_for_operation':False,'actual_motor_bearing_radial_rating_verified':False,
        'note':'Example symmetric two-strand pretension; difference SF2*force, tight=T0+force, slack=T0-force. Supplier and measured installation tension needed. Not a tension-setting instruction.'}
    r['closed_design_items']=['Vendor clamp tooth/backplate dimensions and hole grids referenced; no home-made GT2 tooth profile',
        'A/B left terminals0..2mm screw adjustment + separate slot locks; right terminals fixed',
        'B motor raised6mm for12mm total shaft/pulley support; lowerclamp6mm unchanged',
        'Shoulder socket/inner-ring washer stack and accessible motor/idler/base/beam fasteners modeled',
        'XY top cap recesses prevent heads entering lower screw pedestal or tower feet']
    r['unreleased_gates']=['Selected vendor conforming GT2 clamping pulleys and bearing-retained idlers, physical torque-slip/preload and belt clamp pullout tests',
        'Actual ZDT electrical/interface/torque-speed/temperature and radial bearing ratings; A/B synchronization on actual hardware',
        'All remaining profile/rail/Z bearing/nut/door connections and tolerances/tool access signed off by assembler',
        'Independent automatic fall protection, interlocked doors, emergency stop, protective earth and fault safety circuit',
        'Physical bin/fork/shelf fit, anchors, staged load/endurance and control commissioning']
    return r


def readback():
    manifest=json.loads((OUT/'manifest.json').read_text());meshes=[]
    for r in manifest['parts']:
        if r['process']!='print':continue
        p=OUT/'stl'/(r['code']+'.stl');s=trimesh.load_mesh(p,process=True)
        meshes.append({'code':r['code'],'sha256':sha(p),'watertight':bool(s.is_watertight),'winding_consistent':bool(s.is_winding_consistent),'bodies':s.body_count,'fits_256':bool(max(s.extents)<=256)})
    p=OUT/'viewing/CoreXY_C04_SOLIDS_AP203.step';s=cq.importers.importStep(str(p)).val();a=cq.importers.importStep(str(OUT/'CoreXY_C04_ASSEMBLY.step')).val()
    row={'valid':s.isValid(),'solids':len(s.Solids()),'assembly_solids':len(a.Solids()),'relative_volume_error':abs(s.Volume()-a.Volume())/a.Volume(),'bounds_mm':v2.bbox(s),'assembly_occurrences':p.read_text().count('NEXT_ASSEMBLY_USAGE_OCCURRENCE'),'sha256':sha(p),'solidworks_GUI_import_verified':False}
    return {'mesh_checks':meshes,'flat_STEP':row,'export_readback_pass':bool(row['valid'] and row['solids']==row['assembly_solids'] and row['relative_volume_error']<1e-6 and not row['assembly_occurrences'] and all(r['watertight'] and r['winding_consistent'] and r['bodies']==1 and r['fits_256'] for r in meshes))}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--motion',action='store_true');ap.add_argument('--export',action='store_true');args=ap.parse_args()
    m=build_model();OUT.mkdir(parents=True,exist_ok=True)
    static,accepted=v2.collisions(m.items,m.allowed);seats=connections(m);stroke=stroke_checks(m);interfaces=interface_checks(m)
    r={'fingerprint':FINGERPRINT,'validator_sha256':sha(Path(__file__)),'static_collisions':static,'static_pass':not static,'accepted_contacts':accepted,
        'support_checks':seats,'support_pass':all(s['geometric_seat_pass'] for s in seats),'tension_stroke':stroke,'interface_checks':interfaces,
        'hardware_accepted':False,'manufacturing_release_allowed':False,'loaded_operation_allowed':False}
    print(json.dumps({'static':static,'failed_seats':[s for s in seats if not s['geometric_seat_pass']],'tension_stroke_failures':stroke['failures'],'interfaces':interfaces},indent=2),flush=True)
    (OUT/'validation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(OUT/'engineering_checks.json').write_text(json.dumps(engineering(m),ensure_ascii=False,indent=2))
    if args.motion:r['motion']=motion(m);(OUT/'validation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    passed=r['static_pass'] and r['support_pass'] and stroke['geometry_pass'] and interfaces['checks_pass']
    if args.motion:passed=passed and r['motion']['sampled_geometry_pass']
    if args.export and passed:export(m);r.update(readback())
    r['mechanical_geometry_package_pass']=bool(passed and r.get('export_readback_pass'))
    (OUT/'validation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('C04 MECHANICAL GEOMETRY PASS',r['mechanical_geometry_package_pass'],flush=True)
    return int(not(r['mechanical_geometry_package_pass'] if args.export else passed))


if __name__=='__main__':raise SystemExit(main())
