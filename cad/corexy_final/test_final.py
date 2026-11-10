"""C04 design-freeze evidence: interfaces, full motion and fail-closed release flags."""
import hashlib
import json
import math
from pathlib import Path

import cadquery as cq
import pytest

from corexy_final import OUT,FINGERPRINT,Item,v2,free_length,HOME_X,HOME_Y,prior


@pytest.fixture(scope='session',autouse=True)
def evidence_binding(record_testsuite_property):
    record_testsuite_property('fingerprint',FINGERPRINT)
    record_testsuite_property('test_source_sha256',hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


@pytest.fixture(scope='module')
def manifest():return json.loads((OUT/'manifest.json').read_text())


@pytest.fixture(scope='module')
def report():return json.loads((OUT/'validation.json').read_text())


def test_fingerprints_and_geometry_gate(manifest,report):
    assert manifest['fingerprint']==report['fingerprint']==FINGERPRINT
    assert report['mechanical_geometry_package_pass']


def test_three_complete_motors_and_architecture(manifest):
    motors=[p for p in manifest['parts'] if p['name'].startswith('ZDT_RealMotor')]
    assert sum(p['quantity'] for p in motors)==3 and all(p['solids']==24 for p in motors)
    items={i['name']:i for i in manifest['instances']}
    assert items['motor_A']['group']==items['motor_B']['group']=='fixed'
    assert not any(i.startswith(('x_rack_','y_rack_','z_rack_')) or i in ('y_real_motor','y_puller_plate','latch_servo') for i in items)
    assert manifest['AB_fixed'] and not manifest['independent_Y_pusher']


def test_b_motor_shaft_support_not_confused_with_hub_length(manifest,report):
    assert manifest['motor_faces_Z_mm']=={'A':78,'B':84}
    assert manifest['B_shaft_in_pulley_mm']==12 and manifest['lower_clamping_hub_length_mm']==6
    i=report['interface_checks']
    assert i['B_shaft_in_pulley_mm']==pytest.approx(12,abs=1e-4)
    assert i['B_split_clamp_fully_on_shaft'] and not i['physical_torque_and_strength_verified']


def test_sourced_clamp_dimensions_and_grid(manifest):
    parts=[p for p in manifest['parts'] if p['name'].startswith('C04_TRM4226_')]
    assert len(parts)==4 and sum(p['quantity'] for p in parts)==8
    for p in parts:
        assert p['process']=='purchased_sourced' and p['material']=='aluminum'
        assert p['extents_mm']==pytest.approx([18,4,18.8],abs=1e-4)
        assert 'phidgets.com' in p['note'] and 'NOT' in p['note']


def test_supplier_document_hashes():
    r=json.loads((OUT/'references/supplier_sources.json').read_text())
    assert r['geometry_mm']['hole_grid']==[10,9.4]
    assert r['geometry_mm']['cap_counterbore_diameter']==4.4
    for p in r['sources']:
        assert hashlib.sha256((OUT/'references'/p['file']).read_bytes()).hexdigest()==p['sha256']
    assert not r['supplier_fit_and_delivery_confirmed']


def test_two_pull_screws_and_independent_locks(manifest):
    items={i['name']:i for i in manifest['instances']}
    assert {'tension_A_pull','tension_B_pull','tension_A_lug','tension_B_lug'}<=set(items)
    locks=[n for n in items if n.startswith('terminal_') and '_lock_' in n]
    pinch=[n for n in items if n.startswith('terminal_') and '_pinch_' in n]
    assert len(locks)==8 and len(pinch)==16
    assert manifest['right_terminal_fixed'] and manifest['left_tension_slider_stroke_mm']==[0,2]


def test_stroke_end_geometry(report):
    r=report['tension_stroke']
    assert r['geometry_pass'] and not r['failures']
    assert len(r['combinations'])==4 and r['not_a_belt_stretch_instruction']
    assert r['nominal_engagement_per_terminal_mm']==18


def test_open_belt_lengths_and_corexy_partition():
    for axis in ('A','B'):
        values=[free_length(axis,x,y) for x in (-90,0,90) for y in (-140,-68.5,3)]
        assert max(values)-min(values)<1e-8
        assert free_length(axis,HOME_X,HOME_Y,2)-values[0]==pytest.approx(2)
    for dx,dy in [(-180,143),(0,143),(-180,0)]:
        a,b=dx+dy,-dx+dy
        assert ((a-b)/2,(a+b)/2)==pytest.approx((dx,dy))


def test_static_and_seats(report):
    assert report['static_pass'] and not report['static_collisions']
    assert report['support_pass'] and len(report['support_checks'])>=60
    assert all(s['mating_area_mm2']>2 for s in report['support_checks'])


def test_full244_motion_rerun(report):
    r=report['motion']
    assert r['pose_count']==244 and r['sampled_geometry_pass'] and not r['failures']
    assert r['boolean_pair_tests']>0 and r['identical_relative_pose_cache_hits']>0
    assert r['maintenance_pin_removed'] and not r['continuous_collision_detection']
    assert 'ALL244' in r['method']


def test_part_step_readbacks(manifest):
    for p in manifest['parts']:
        s=cq.importers.importStep(str(OUT/'parts'/(p['code']+'.step'))).val()
        assert s.isValid() and len(s.Solids())==p['solids'],p['code']
        assert s.Volume()==pytest.approx(p['volume_mm3'],rel=1e-6,abs=1e-5),p['code']
        assert v2.bbox(s)==pytest.approx(p['bounds_mm'],abs=1e-4),p['code']


def test_flat_AP203_readback(report):
    path=OUT/'viewing/CoreXY_C04_SOLIDS_AP203.step';r=report['flat_STEP']
    s=cq.importers.importStep(str(path)).val()
    assert s.isValid() and len(s.Solids())==r['solids']==r['assembly_solids']
    assert r['relative_volume_error']<1e-6 and not r['assembly_occurrences']
    assert 'CONFIG_CONTROL_DESIGN' in path.read_text()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
    assert not r['solidworks_GUI_import_verified']


def test_print_meshes(report):
    for r in report['mesh_checks']:
        assert r['watertight'] and r['winding_consistent'] and r['bodies']==1 and r['fits_256']
        assert hashlib.sha256((OUT/'stl'/(r['code']+'.stl')).read_bytes()).hexdigest()==r['sha256']


def test_added_stack_hardware(manifest):
    names={i['name'] for i in manifest['instances']}
    assert len([n for n in names if n.startswith('motor_') and '_base_' in n])==8
    assert len([n for n in names if n.startswith('beam_mount_')])==8
    assert len([n for n in names if n.startswith('y_datum_base_')])==8
    assert len([n for n in names if n.endswith('_axle_topwasher')])==4
    assert {'motor_A_pinch','motor_B_pinch'}<=names


def test_beam_screws_follow_gantry_and_use_existing_bores(manifest):
    items={i['name']:i for i in manifest['instances']};parts={p['name']:p for p in manifest['parts']}
    for side in (-1,1):
        end=parts[items[f'gantry_end_{side}']['part']]
        for a in (-10,10):
            for b in (-55,55):
                name=f'beam_mount_{side}_{a}_{b}';r=items[name];p=parts[r['part']]
                assert r['group']=='gantry' and r['origin_mm']==[side*205+a,HOME_Y+b,47]
                assert any(h[0][:2]==[a,b] and h[2]==4.2 for h in end['holes'])
                beam=parts[items[f'gantry_beam_{b}']['part']]
                assert any(h[0][:2]==[side*205+a,0] and h[2]==3.3 for h in beam['holes'])
                assert not any(name in (c['a'],c['b']) for c in manifest['allowed_contacts'])
                shape=cq.importers.importStep(str(OUT/'parts'/(p['code']+'.step'))).val()
                item=Item(name,v2.Part(p['name'],shape,p['material'],p['process']),tuple(r['origin_mm']),r['group'])
                assert (item.located(dx=-180,dy=143,dz=4).Center()-item.located().Center()).toTuple()==pytest.approx((0,143,0))


def test_tension_slider_does_not_move_other_axis(manifest):
    parts={p['name']:p for p in manifest['parts']};items={i['name']:i for i in manifest['instances']}
    for name,delta in [('terminal_A_L_receiver',(2,0,0)),('terminal_A_R_receiver',(0,0,0)),('terminal_B_L_receiver',(0,0,0)),('tension_A_pull',(0,0,0))]:
        r=items[name];p=parts[r['part']];s=cq.importers.importStep(str(OUT/'parts'/(p['code']+'.step'))).val()
        i=Item(name,v2.Part(p['name'],s,p['material'],p['process']),tuple(r['origin_mm']),r['group'])
        assert (i.located(tension_a=2).Center()-i.located().Center()).toTuple()==pytest.approx(delta,abs=1e-5)
        with pytest.raises(ValueError):i.located(tension_a=3)


def test_physical_gates_are_not_silently_released(manifest,report):
    for r in (manifest,report):assert not r['hardware_accepted'] and not r['loaded_operation_allowed']
    assert not manifest['manufacturing_release_allowed'] and not manifest['motor_performance_verified']
    assert not manifest['automatic_brake_selected'] and not manifest['safety_circuit_implemented'] and not manifest['control_firmware_implemented']
    assert report['interface_checks']['terminal_top_screw_engagement_mm']>=6


def test_belt_force_screen_not_an_installation_tension():
    r=json.loads((OUT/'engineering_checks.json').read_text())
    b=r['belt_screen']
    assert not b['pretension_selected_for_operation'] and not b['actual_motor_bearing_radial_rating_verified']
    assert b['SF2_tight_strand_example_N']==pytest.approx(b['pretension_example_N']+b['nominal_worst_each_motor_tension_difference_N'])
    assert r['moving_masses_kg_including_payload_and_allowance']['Y']>1
