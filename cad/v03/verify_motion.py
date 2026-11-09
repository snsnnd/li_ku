"""Discrete conservative packaging checks plus separately tested exact tooth geometry.

Motor boxes include rear electronics, pinions use swept outer cylinders, and rack tooth
details use conservative boxes. Only the three declared rack/pinion mesh families are
excluded here; their real B-reps are tested over a pitch and splice by test_v03.py.
This is not continuous collision detection, contact dynamics, or safety acceptance.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from dataclasses import replace

import cadquery as cq
from asrs_v03 import OUT,FINGERPRINT,build_model,Item,v2,box,cyl,fuse
from gears import RADIUS,MODULE


def packaging_model(model):
    items=[]
    for item in model.items:
        p=item.part;shape=p.shape
        if p.name.startswith('ZDT_RealMotor'):
            # Normal frame: mounting face Z=0, shaft +Z, rear driver Z=-59.
            shape=fuse(box(1.325,-10.45,-59,44.65,62.9,59),cyl(0,0,0,11,2),cyl(0,0,2,2.5,22))
            shape=shape.rotate((0,0,0),(1,0,0),90 if p.name.endswith('_Z') else 180)
        elif item.name.endswith('_pinion'):
            shape=cyl(0,0,0,RADIUS+MODULE,12).cut(cyl(0,0,-1,6.1,14))
            if item.group=='zgear':shape=shape.rotate((0,0,0),(1,0,0),90)
        elif '_rack_' in item.name and p.name.startswith('Rack_'):
            b=shape.BoundingBox();shape=box((b.xmin+b.xmax)/2,(b.ymin+b.ymax)/2,b.zmin,b.xlen,b.ylen,b.zlen)
        p=replace(p,shape=shape)
        items.append(Item(item.name,p,item.origin,item.group))
    return items


def same_rigid_group(a,b):
    # Gears rotate with respect to their parent, so only identical groups are rigid.
    return a.group==b.group


def meshing_pair(a,b):
    for axis in ('x','y','z'):
        if {a.name,b.name} & {axis+'_pinion'}:
            other=b.name if a.name==axis+'_pinion' else a.name
            if other.startswith(axis+'_rack_') and other[len(axis+'_rack_'):].isdigit():return True
    return False


def check_pose(items,dx,dz,q,lift,target,bin_q,io_open):
    located=[]
    for i in items:
        if target and (i.name==target or i.name==target+'_marker'):continue
        s=i.located(dx,dz,q,lift,bin_q,io_open)
        located.append((i,s,v2.bbox(s)))
    failures=[];tests=0
    for k,(a,sa,ba) in enumerate(located):
        for b,sb,bb in located[k+1:]:
            if same_rigid_group(a,b):continue
            if meshing_pair(a,b):continue
            if not v2.overlaps(ba,bb):continue
            tests+=1;vol=sa.intersect(sb).Volume()
            if vol>.02:failures.append({'a':a.name,'b':b.name,'volume_mm3':round(vol,4)})
    return failures,tests


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--step',type=float,default=12)
    args=ap.parse_args()
    if args.step<=0:raise ValueError('positive step required')
    m=build_model();items=packaging_model(m)
    n=math.ceil(m.d.transfer/args.step);qs=[m.d.transfer*j/n for j in range(n+1)]
    targets=[(xx,zz,f'stored_bin_{c}_{r}',False) for c,xx in enumerate(m.d.x_positions) for r,zz in enumerate(m.d.decks)]
    targets.append((-150,200,None,True));poses=[]
    lift=7*(1-math.cos(math.radians(165)))
    for xx,zz,target,io in targets:
        for q in qs:
            poses.append(('transfer',xx-m.x,zz-m.deck,q,0,target,None,int(io)))
            poses.append(('released_withdraw',xx-m.x,zz-m.deck,q,lift,target,m.d.transfer,int(io)))
        for bq in (0,m.d.transfer/2,m.d.transfer):
            for offset in (-1.1,1.1):
                poses.append(('pin_clearance',xx-m.x,zz-m.deck,bq+offset,0,target,bq,int(io)))
    for xx in [-150]+m.d.x_positions:
        for j in range(39):poses.append(('z_traverse',xx-m.x,200+10*j-m.deck,-1.1,0,None,0,0))
    for zz in m.d.decks:
        for j in range(40):poses.append(('x_traverse',-150+20*j-m.x,zz-m.deck,-1.1,0,None,0,0))
    for io in (False,True):
        for q in (0,m.d.transfer):
            for degrees in (0,45,90,135,165):
                poses.append(('latch',(-150-m.x) if io else 0,(200-m.deck) if io else 0,
                    q,7*(1-math.cos(math.radians(degrees))),None if io else 'stored_bin_1_2',None,int(io)))
    for j in range(10):
        poses.append(('io_shutter_stroke',-150-m.x,200-m.deck,-1.1,0,None,0,j/9))
    failures=[];boolean_tests=0;start=time.monotonic()
    for j,p in enumerate(poses,1):
        phase,dx,dz,q,l,target,bq,io=p
        bad,tests=check_pose(items,dx,dz,q,l,target,bq,io)
        boolean_tests+=tests
        if bad:failures.append({'phase':phase,'dx':dx,'dz':dz,'q':q,'lift':l,'io_open':io,'collisions':bad})
        if j%50==0:print(f'POSE {j}/{len(poses)} failing={len(failures)} seconds={time.monotonic()-start:.1f}',flush=True)
    report={'fingerprint':FINGERPRINT,'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'method':'Discrete conservative packaging B-reps; exact tooth mesh validated separately',
        'pose_count':len(poses),'y_step_mm':m.d.transfer/n,'x_step_mm':20,'z_step_mm':10,
        'storage_targets':20,'additional_io_targets':1,'x_traverse_heights_mm':m.d.decks,
        'io_shutter_stroke_samples':10,
        'boolean_pair_tests':boolean_tests,'failures':failures,'sampled_packaging_pass':not failures,
        'continuous_collision_detection':False,'hardware_accepted':False,'manufacturing_release_allowed':False,
        'elapsed_seconds':time.monotonic()-start}
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/'motion_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'poses':len(poses),'failing_poses':len(failures),'first_failures':failures[:4]},indent=2),flush=True)
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
