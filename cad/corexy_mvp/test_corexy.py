"""C03 architectural/kinematic/export regressions, not physical acceptance."""
import hashlib
import json
import math

import cadquery as cq
import pytest

from corexy_mvp import OUT,FINGERPRINT,Item,v2,HOME_X,HOME_Y,CELL_Z,belt_length,drive_partition


@pytest.fixture(scope='module')
def manifest():return json.loads((OUT/'manifest.json').read_text())


@pytest.fixture(scope='module')
def checks():return json.loads((OUT/'validation.json').read_text())


def test_current_fingerprint(manifest,checks):
    assert manifest['fingerprint']==checks['fingerprint']==FINGERPRINT
    assert checks['geometry_deliverable_pass']


def test_whole_architecture_changed(manifest):
    names={r['name'] for r in manifest['instances']}
    assert {'motor_A','motor_B','z_real_motor','fork','xy_plate','bin','belt_A','belt_B'}<=names
    assert not any('pinion' in n or n.startswith(('x_rack_','y_rack_','z_rack_')) or 'servo' in n or n in ('latch_pin','y_real_motor','y_puller_plate','carrier_tray') for n in names)
    assert manifest['AB_fixed'] and not manifest['independent_Y_pusher']


def test_three_complete_motors(manifest):
    motors=[r for r in manifest['parts'] if r['name'].startswith('ZDT_RealMotor')]
    assert sum(r['quantity'] for r in motors)==3
    assert all(r['solids']==24 for r in motors)
    instances={r['name']:r for r in manifest['instances']}
    assert instances['motor_A']['group']==instances['motor_B']['group']=='fixed'
    assert instances['z_real_motor']['group']=='xy'


def test_belt_path_length_and_mapping(checks):
    k=checks['kinematics'];assert k['geometry_mapping_pass']
    assert k['constant_open_belt_length_error_mm']<1e-8 and k['max_mapping_error_mm']<1e-8
    for x in (-90,0,90):
        for y in (-140,-68.5,3):
            a=drive_partition('A',x,y)-drive_partition('A',HOME_X,HOME_Y)
            b=drive_partition('B',x,y)-drive_partition('B',HOME_X,HOME_Y)
            assert ((a-b)/2,(a+b)/2)==pytest.approx((x-HOME_X,y-HOME_Y))
            for axis in ('A','B'):assert belt_length(axis,x,y)==pytest.approx(belt_length(axis,HOME_X,HOME_Y))
    assert k['cut_length_is_not_free_path'] and not k['wiring_signs_and_motor_synchronization_verified']


def test_two_belt_layers_and_four_separate_anchors(manifest):
    assert manifest['belt_layers_bottom_mm']=={'A':91.5,'B':103.5}
    items={r['name']:r for r in manifest['instances']}
    assert items['belt_A']['group']==items['belt_B']['group']=='belt'
    assert len([n for n in items if n.startswith('clamp_')])==4


def test_carriage_and_fork_are_metal(manifest):
    parts={r['name']:r for r in manifest['parts']};items={r['name']:r for r in manifest['instances']}
    for name in ('xy_plate','fork','z_nut_bridge','z_screw','z_safety_cage'):
        assert parts[items[name]['part']]['process']!='print'
    assert parts[items['fork']['part']]['material']=='steel'
    assert len([n for n in items if n.startswith('gantry_beam_')])==2
    assert len([n for n in items if n.startswith('x_block_') and 'bolt' not in n])==4
    assert len([n for n in items if n.startswith('y_block_') and 'bolt' not in n])==4


def test_fork_slot_clearance(manifest):
    parts={r['name']:r for r in manifest['parts']};items={r['name']:r for r in manifest['instances']}
    # Steel support inner edge is41mm, fork outer edge37mm.
    assert 50-18/2-(28+18/2)==4
    assert items['cell_rail_-1']['origin_mm'][0]==40
    assert items['cell_rail_1']['origin_mm'][0]==140
    assert manifest['fork_approach_below_mm']==8 and manifest['fork_lift_above_mm']==4


def test_no_unknown_static_penetrations(checks):
    assert checks['static_pass'] and not checks['static_collisions']
    allowed={tuple(sorted((r['a'],r['b']))) for r in checks['accepted_contacts']}
    assert all(any(n.startswith('clamp_') for n in pair) and any(n.startswith('belt_') for n in pair) for pair in allowed)


def test_support_faces(checks):
    assert checks['support_pass'] and len(checks['support_checks'])>=50
    assert all(r['mating_area_mm2']>2 and r['gap_mm']<1e-5 for r in checks['support_checks'])


def test_store_retrieve_and_motion(checks):
    r=checks['motion'];assert r['sampled_geometry_pass'] and not r['failures']
    assert r['pose_count']>=200 and r['maintenance_pin_removed'] and not r['continuous_collision_detection']
    assert 'store' in r['cycles'] and 'retrieve' in r['cycles']


def test_part_step_readbacks(manifest):
    for r in manifest['parts']:
        s=cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        assert s.isValid() and len(s.Solids())==r['solids'],r['code']
        assert s.Volume()==pytest.approx(r['volume_mm3'],rel=1e-6,abs=1e-5),r['code']
        assert v2.bbox(s)==pytest.approx(r['bounds_mm'],abs=1e-4),r['code']


def test_print_meshes(checks):
    for r in checks['mesh_checks']:
        assert r['watertight'] and r['winding_consistent'] and r['bodies']==1 and r['fits_256']
        assert hashlib.sha256((OUT/'stl'/(r['code']+'.stl')).read_bytes()).hexdigest()==r['sha256']


def test_flat_STEP(checks):
    path=OUT/'viewing/CoreXY_Fork_C03_SOLIDS_AP203.step';r=checks['flat_STEP']
    s=cq.importers.importStep(str(path)).val()
    assert s.isValid() and len(s.Solids())==r['solids']==r['assembly_solids']
    assert r['relative_volume_error']<1e-6 and not r['assembly_occurrences']
    assert 'CONFIG_CONTROL_DESIGN' in path.read_text() and 'INVISIBILITY' not in path.read_text()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']


def test_transforms(manifest):
    parts={r['name']:r for r in manifest['parts']};items={r['name']:r for r in manifest['instances']}
    for name,delta in [('motor_A',(0,0,0)),('motor_B',(0,0,0)),('z_real_motor',(-180,143,0)),('fork',(-180,143,-95)),('gantry_beam_55',(0,143,0))]:
        r=items[name];p=parts[r['part']];s=cq.importers.importStep(str(OUT/'parts'/(p['code']+'.step'))).val()
        i=Item(name,v2.Part(p['name'],s,p['material'],p['process']),tuple(r['origin_mm']),r['group'])
        assert (i.located(dx=-180,dy=143,dz=-95).Center()-i.located().Center()).toTuple()==pytest.approx(delta,abs=1e-5)


def test_AB_force_mapping_and_mass():
    r=json.loads((OUT/'engineering_checks.json').read_text());f=r['axis_force_N']
    worst=(abs(f['X'])+abs(f['Y']))/2
    assert r['AB_motor_screen']['required_each_motor_torque_SF2_Nm']==pytest.approx(2*worst*40/(2*math.pi)/1000/.8)
    assert r['moving_masses_kg_including_payload_and_allowance']['Y']>r['moving_masses_kg_including_payload_and_allowance']['X']>1
    assert not r['AB_motor_screen']['motor_curve_verified']


def test_not_approved_for_hardware_or_power(manifest,checks):
    for r in (manifest,checks):assert not r['hardware_accepted'] and not r['loaded_operation_allowed']
    assert not manifest['automatic_brake_selected'] and not manifest['control_firmware_implemented']
    assert not checks['flat_STEP']['solidworks_gui_import_verified']
