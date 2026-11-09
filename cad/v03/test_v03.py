"""Geometry and executable design-contract regressions, not physical acceptance."""
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from asrs_v03 import build_model, v2, FINGERPRINT, ROOT
from gears import rack,pinion,PITCH,RADIUS,SEGMENT_LENGTH,RACK_PITCH_HEIGHT
from control_contract import (Status,may_move,may_open_outer,may_open_inner,
    may_close_inner,may_transfer_to_io,may_transfer_from_io,may_apply_visual_correction)


@pytest.fixture(scope='session',autouse=True)
def record_sources(record_testsuite_property):
    record_testsuite_property('geometry_fingerprint',FINGERPRINT)
    for name in ('test_v03.py','control_contract.py'):
        record_testsuite_property(name+'_sha256',hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest())


@pytest.fixture(scope='module')
def model():return build_model()


def test_geometry_valid(model):
    assert all(p.shape.isValid() for p in model.parts.values())
    assert all(len(p.shape.Solids())==24 if p.name.startswith('ZDT_RealMotor') else len(p.shape.Solids())==1
               for p in model.parts.values())


def test_all_three_axes_are_rack_driven(model):
    assert all(any(i.name.startswith(axis+'_rack_') for i in model.items) for axis in ('x','y','z'))
    assert not any('Belt' in p.name or 'Screw' in p.name for p in model.parts.values())


def test_three_real_motors_and_local_nodes(model):
    for axis in ('x','y','z'):
        assert next(i for i in model.items if i.name==axis+'_real_motor').group==axis
        assert next(i for i in model.items if i.name==axis+'_battery_candidate').group==axis


def test_independent_columns_have_two_locators_and_four_posts(model):
    for c in range(4):
        assert sum(i.name.startswith(f'column_{c}_post_') for i in model.items)==4
        assert sum(i.name.startswith(f'column_{c}_datum_') for i in model.items)==2
        assert any(i.name==f'column_{c}_carrier' for i in model.items)


def test_rack_phase_repeats_at_segment_boundary():
    assert SEGMENT_LENGTH/PITCH==pytest.approx(24)
    assert SEGMENT_LENGTH/RADIUS/(2*math.pi/20)==pytest.approx(24)


def test_actual_involute_mesh_across_pitch_and_splice():
    r=rack();p=pinion();r=r.fuse(r.translate((SEGMENT_LENGTH,0,0)))
    for xx in [5*PITCH+j*PITCH/8 for j in range(9)]+[SEGMENT_LENGTH-.4,SEGMENT_LENGTH,SEGMENT_LENGTH+.4]:
        gear=(p.rotate((0,0,0),(0,0,1),math.degrees(-xx/RADIUS))
              .rotate((0,0,0),(1,0,0),90).translate((xx,6,RACK_PITCH_HEIGHT+RADIUS)))
        assert r.intersect(gear).Volume()<.02


@pytest.mark.parametrize('axis',['x','y','z'])
def test_actual_axis_pinion_phases(model,axis):
    gear=next(i for i in model.items if i.name==axis+'_pinion')
    racks=[i for i in model.items if i.name.startswith(axis+'_rack_') and i.name[len(axis+'_rack_'):].isdigit()]
    endpoints={'x':(-420,360),'y':(-1.1,144.1),'z':(-190,190)}[axis]
    for delta in (0,PITCH/3,.8*PITCH,*endpoints):
        pose={'dx':delta} if axis=='x' else {'q':delta} if axis=='y' else {'dz':delta}
        g=gear.located(**pose)
        for item in racks:
            r=item.located(**pose)
            if v2.overlaps(v2.bbox(g),v2.bbox(r)):assert g.intersect(r).Volume()<.02


def test_prints_fit_256mm(model):
    for p in model.parts.values():
        if p.process=='print':
            b=p.shape.BoundingBox();assert max(b.xlen,b.ylen,b.zlen)<=256


def test_battery_and_controller_do_not_overlap_case(model):
    for axis in ('x','y','z'):
        case=next(i for i in model.items if i.name==axis+'_power_case').located()
        for suffix in ('battery_candidate','esp32_candidate'):
            other=next(i for i in model.items if i.name==axis+'_'+suffix).located()
            assert case.intersect(other).Volume()<1e-5


def test_independent_safety_track_not_printed(model):
    item=next(i for i in model.items if i.name=='z_independent_safety_track')
    assert item.part.material=='steel'
    assert next(i for i in model.items if i.name=='z_brake_candidate').part.process=='candidate'


def test_box_markers_and_camera_reserved(model):
    assert sum(i.name.endswith('_marker') for i in model.items)==20
    assert any(i.name=='tool_camera_candidate' for i in model.items)


def test_io_is_distinct_from_storage(model):
    assert len(model.d.x_positions)*len(model.d.decks)==20
    assert any(i.name=='io_deck' and i.origin[0]==-150 for i in model.items)
    shutter=next(i for i in model.items if i.name=='io_inner_shutter')
    assert v2.bbox(shutter.located(io_open=1))[2]==pytest.approx(284)


def test_static_assembly(model):
    bad,_=v2.collisions(model.items,model.allowed)
    assert bad==[]


@pytest.fixture
def ready():
    return Status(homed=True,y_retracted=True,local_stop_ok=True,safety_chain_ok=True,
        battery_ok=True,brake_ready=True,motion_stopped=True,outer_door_locked=True)


@pytest.mark.parametrize('axis',['X','Y','Z'])
def test_local_command_gate(axis,ready):
    good=dict(link_age_ms=20,command_age_ms=20,session_matches=True,sequence_new=True)
    assert may_move(axis,ready,**good)
    for name,value in [('link_age_ms',250),('command_age_ms',150),('session_matches',False),('sequence_new',False)]:
        assert not may_move(axis,ready,**{**good,name:value})
    assert not may_move(axis,dataclasses.replace(ready,battery_ok=False),**good)
    assert not may_move(axis,dataclasses.replace(ready,safety_chain_ok=False),**good)


def test_z_needs_independent_brake(ready):
    assert not may_move('Z',dataclasses.replace(ready,brake_ready=False),link_age_ms=0,
        command_age_ms=0,session_matches=True,sequence_new=True)


def test_mutual_door_and_box_occupancy_logic(ready):
    assert may_open_outer(ready)
    assert not may_open_outer(dataclasses.replace(ready,inner_shutter_closed=False))
    assert not may_open_inner(dataclasses.replace(ready,outer_door_locked=False))
    opened=dataclasses.replace(ready,inner_shutter_closed=False,inner_shutter_open=True)
    assert may_transfer_to_io(dataclasses.replace(opened,tray_has_box=True))
    assert may_transfer_from_io(dataclasses.replace(opened,io_has_box=True))
    assert not may_transfer_to_io(dataclasses.replace(opened,tray_has_box=True,io_has_box=True))
    assert not may_transfer_to_io(dataclasses.replace(ready,tray_has_box=True))
    assert not may_close_inner(dataclasses.replace(ready,y_retracted=False))


def test_camera_does_not_override_homing_or_freshness(ready):
    vision=dataclasses.replace(ready,vision_fresh=True,correct_box_id=True,camera_calibrated=True)
    assert may_apply_visual_correction(vision,.5,-.5)
    assert not may_apply_visual_correction(vision,3,0)
    assert not may_apply_visual_correction(dataclasses.replace(vision,vision_fresh=False),0,0)
    assert not may_apply_visual_correction(dataclasses.replace(vision,correct_box_id=False),0,0)
    assert not may_apply_visual_correction(dataclasses.replace(vision,homed=False),0,0)


def test_metric_marker_assets():
    data=json.loads((ROOT/'model/V03/markers/marker_manifest.json').read_text())
    assert len(data['tags'])==25
    assert len({r['id'] for r in data['tags']})==25
    assert all(r['outer_card_mm']==32 and r['detected_black_border_square_mm']==25.6 for r in data['tags'])


def test_nominal_front_marker_sightlines(model):
    import cadquery as cq
    for q in (0,143):
        for ox,oz in ((-16,-16),(-16,16),(16,-16),(16,16),(0,0)):
            start=cq.Vector(model.x-36,-204.8,model.deck+38)
            end=cq.Vector(model.x-36+ox,-78-61.2+q,model.deck+38+oz)
            vec=end-start;ray=cq.Solid.makeCylinder(.10,vec.Length-1,start,vec.normalized())
            for i in model.items:
                if i.name in ('tool_camera_candidate','carried_bin_marker'):continue
                s=i.located(q=q)
                if v2.overlaps(v2.bbox(ray),v2.bbox(s)):assert ray.intersect(s).Volume()<.001,(q,i.name)
