"""E02 structural/geometry regressions; deliberately no hardware acceptance."""
import hashlib
import json
import math

import cadquery as cq
import pytest

from belt_mvp import OUT, BASE, FINGERPRINT, Item, v2


@pytest.fixture(scope='module')
def manifest():
    return json.loads((OUT/'manifest.json').read_text())


@pytest.fixture(scope='module')
def checks():
    return json.loads((OUT/'validation.json').read_text())


def test_fingerprint_and_geometry_gate(manifest, checks):
    assert manifest['fingerprint'] == checks['fingerprint'] == FINGERPRINT
    assert checks['geometry_deliverable_pass']


def test_no_racks_or_pinion_hubs(manifest):
    names = [r['name'].lower() for r in manifest['parts']]
    assert not any('rack_m1' in n or 'pinion' in n or 'rack_backbone' in n for n in names)
    for i in manifest['instances']:
        assert not i['name'].startswith(('x_rack_', 'y_rack_', 'x_hub_', 'y_hub_'))


def test_three_complete_motors_correct_parent_groups(manifest):
    parts = {r['name']: r for r in manifest['parts']}
    instances = {i['name']: i for i in manifest['instances']}
    motors = [r for r in manifest['parts'] if r['name'].startswith('ZDT_RealMotor')]
    assert len(motors) == 3 and all(r['solids'] == 24 and r['quantity'] == 1 for r in motors)
    assert instances['x_real_motor']['group'] == 'fixed'
    assert instances['y_real_motor']['group'] == 'z'
    assert instances['z_real_motor']['group'] == 'x'
    assert parts[instances['y_real_motor']['part']]['name'].endswith('_Y_Up')


def test_belt_geometry_and_catalog_lengths(manifest):
    assert manifest['belt_pitch_mm'] == 2 and manifest['pulley_teeth'] == 20 and manifest['advance_mm_rev'] == 40
    for r in manifest['belts'].values():
        assert r['pitch_length_mm'] == pytest.approx(2*r['centres_mm']+40)
    assert manifest['base_mm'] == [610, 590, 6]
    assert manifest['motion_limits'] == {'X_mm': [-90, 90], 'Z_deck_mm': [200, 295], 'Y_transfer_mm': [0, 143]}


def test_wider_Y_guides_and_belt_clearance(manifest):
    instances = {r['name']: r for r in manifest['instances']}
    assert manifest['Y_guide_spacing_mm'] == 52
    assert instances['y_rail_right']['origin_mm'][0]-instances['y_rail']['origin_mm'][0] == 52
    parts = {r['name']: r for r in manifest['parts']}
    block = parts[instances['y_block_right']['part']]
    belt_left = instances['y_belt']['origin_mm'][0]-40/(2*math.pi)-.65
    block_right = instances['y_block_right']['origin_mm'][0]+block['bounds_mm'][3]
    assert belt_left-block_right > 5


def test_screw_and_load_path_stay_metal(manifest):
    parts = {r['name']: r for r in manifest['parts']}; instances = {r['name']: r for r in manifest['instances']}
    assert manifest['screw_lead_mm'] == 2
    for n in ('z_screw', 'z_nut_bridge', 'z_safety_cage', 'maintenance_shoe'):
        assert parts[instances[n]['part']]['material'] == 'steel'
        assert parts[instances[n]['part']]['process'] != 'print'
    assert sum(n.startswith('tube_sleeve_') for n in instances) == 2
    assert sum(n.startswith('tube_bolt_') for n in instances) == 4
    for n in ('tray_tube_plug_-44', 'tray_tube_plug_44'):
        plug = parts[instances[n]['part']]
        assert plug['process'] != 'print'
        assert plug['extents_mm'][2] == pytest.approx(21)


def test_static_contacts_and_supports(checks):
    assert checks['static_pass'] and not checks['static_collisions']
    assert checks['support_pass'] and len(checks['support_checks']) >= 25
    contacts = {tuple(sorted((r['a'], r['b']))) for r in checks['accepted_contacts']}
    assert contacts == {tuple(sorted((n+'_belt', n+'_belt_pressure_jaw'))) for n in ('x', 'y')}


def test_sampled_motion(checks):
    r = checks['motion']
    assert r['pose_count'] == 165 and r['sampled_geometry_pass'] and not r['failures']
    assert r['maintenance_pin_removed'] and not r['continuous_collision_detection']
    assert r['IO_shutter_samples'] == 11


def test_tensioner_adjustment_limits(checks):
    r = checks['tensioner_limits']
    assert r['geometry_pass'] and not r['unexpected_collisions']
    assert r['X_idler_shift_mm'] == 2 and r['Y_idler_shift_mm'] == -2
    assert r['belt_effective_loop_regenerated'] and not r['belt_extension_is_an_instruction']


def test_individual_step_files(manifest):
    for r in manifest['parts']:
        shape = cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        assert shape.isValid() and len(shape.Solids()) == r['solids'], r['code']
        assert shape.Volume() == pytest.approx(r['volume_mm3'], rel=1e-6, abs=1e-5), r['code']
        assert v2.bbox(shape) == pytest.approx(r['bounds_mm'], abs=1e-4), r['code']


def test_flat_STEP(checks):
    path = OUT/'viewing/Belt_MVP_E02_SOLIDS_AP203.step'; r = checks['flat_STEP']
    shape = cq.importers.importStep(str(path)).val()
    assert shape.isValid() and len(shape.Solids()) == r['solids'] == r['assembly_solids']
    assert r['relative_volume_error'] < 1e-6 and r['assembly_occurrences'] == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == r['sha256']
    assert 'CONFIG_CONTROL_DESIGN' in path.read_text() and 'INVISIBILITY' not in path.read_text()
    assert not r['solidworks_gui_import_verified']


def test_print_meshes_and_reduced_printed_drive_parts(manifest, checks):
    for r in checks['mesh_checks']:
        assert r['watertight'] and r['winding_consistent'] and r['bodies'] == 1 and r['fits_256']
        assert hashlib.sha256((OUT/'stl'/(r['code']+'.stl')).read_bytes()).hexdigest() == r['sha256']
    old = json.loads((BASE/'manifest.json').read_text())
    assert sum(r['quantity'] for r in manifest['parts'] if r['process'] == 'print') < sum(r['quantity'] for r in old['parts'] if r['process'] == 'print')


def test_transforms(manifest):
    parts = {r['name']: r for r in manifest['parts']}; instances = {r['name']: r for r in manifest['instances']}
    for name, delta in [('x_real_motor', (0, 0, 0)), ('y_real_motor', (-180, 0, -95)),
                        ('y_puller_plate', (-180, 143, -95)), ('carried_bin', (-180, 143, -95))]:
        r = instances[name]; p = parts[r['part']]
        shape = cq.importers.importStep(str(OUT/'parts'/(p['code']+'.step'))).val()
        item = Item(name, v2.Part(p['name'], shape, p['material'], p['process']), tuple(r['origin_mm']), r['group'])
        assert (item.located(dx=-180, dz=-95, q=143).Center()-item.located().Center()).toTuple() == pytest.approx(delta, abs=1e-5)


def test_mass_and_torque_comparison():
    r = json.loads((OUT/'engineering_checks.json').read_text())
    assert r['fingerprint'] == FINGERPRINT and r['target_payload_kg'] == 1
    for t in r['motor_targets']:
        assert t['moving_mass_with_1kg_payload_and_allowance_kg'] > 1
        arm = .002/(2*math.pi) if t['axis'] == 'Z' else 40/(2*math.pi)/1000
        assert t['required_motor_torque_SF2_Nm'] == pytest.approx(2*t['force_N']*arm/t['assumed_efficiency'])
        assert not t['motor_performance_verified']
    y = next(t for t in r['comparison_to_E01'] if t['axis'] == 'Y')
    assert y['E01_mass_kg']-y['E02_mass_kg'] > .4
    assert y['E02_torque_SF2_Nm'] < y['E01_torque_SF2_Nm']
    assert not r['belt_screen']['pretension_instruction']
    assert not r['belt_screen']['belt_strength_stiffness_and_motor_bearing_rating_verified']


def test_not_a_hardware_acceptance(manifest, checks):
    for r in (manifest, checks):
        assert not r['hardware_accepted'] and not r['loaded_operation_allowed']
    assert not manifest['control_firmware_implemented'] and not manifest['independent_brake_selected']
    assert not manifest['motor_torque_curve_verified']
