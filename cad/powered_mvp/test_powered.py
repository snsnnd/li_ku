"""Readback regression tests for E01; physical safety is deliberately not claimed."""
import hashlib
import json
import math

import cadquery as cq
import pytest

from powered_mvp import OUT, FINGERPRINT, Item, v2


@pytest.fixture(scope='module')
def manifest():
    return json.loads((OUT/'manifest.json').read_text())


@pytest.fixture(scope='module')
def validation():
    return json.loads((OUT/'validation.json').read_text())


def test_fingerprint(manifest, validation):
    assert manifest['fingerprint'] == validation['fingerprint'] == FINGERPRINT


def test_three_complete_real_motors(manifest):
    motors = [r for r in manifest['parts'] if r['name'].startswith('ZDT_RealMotor')]
    assert len(motors) == 3 and sum(r['quantity'] for r in motors) == 3
    assert all(r['solids'] == 24 for r in motors)


def test_single_cell_and_IO(manifest):
    names = [i['name'] for i in manifest['instances']]
    assert sum(n.startswith('cell_') for n in names) == 1
    assert 'io_deck' in names and 'carried_bin' in names
    assert not any(n.startswith(('stored_bin_', 'z_rack_')) for n in names)
    assert not any('reduction_candidate' in n or 'battery_candidate' in n for n in names)


def test_screw_and_metal_load_path(manifest):
    by = {r['name']: r for r in manifest['parts']}
    instances = {r['name']: by[r['part']] for r in manifest['instances']}
    assert manifest['screw_lead_mm'] == 2
    assert instances['z_screw']['extents_mm'][2] == pytest.approx(298)
    for n in ('z_screw', 'z_nut_bridge', 'z_safety_cage', 'maintenance_shoe'):
        assert instances[n]['material'] == 'steel'
        assert instances[n]['process'] != 'print'
    assert instances['z_working_nut']['quantity'] == 2


def test_static_and_seats(validation):
    assert validation['static_pass'] and not validation['static_collisions']
    assert validation['support_pass'] and len(validation['support_checks']) >= 25
    assert all(r['opposed_planar_mating_area_mm2'] > 2 for r in validation['support_checks'])


def test_sampled_motion(validation):
    r = validation['motion']
    assert r['pose_count'] >= 160 and r['sampled_geometry_pass'] and not r['failures']
    assert r['maintenance_pin_removed'] and r['IO_shutter_samples'] == 11
    assert not r['continuous_collision_detection']


def test_print_meshes(validation):
    for r in validation['mesh_checks']:
        assert r['watertight'] and r['winding_consistent'] and r['bodies'] == 1 and r['fits_256']
        assert hashlib.sha256((OUT/'stl'/(r['code']+'.stl')).read_bytes()).hexdigest() == r['sha256']


def test_flat_STEP_readback(validation):
    path = OUT/'viewing/Powered_MVP_E01_SOLIDS_AP203.step'
    shape = cq.importers.importStep(str(path)).val()
    r = validation['flat_STEP']
    assert shape.isValid() and len(shape.Solids()) == r['solids'] == r['assembly_solids']
    assert r['relative_volume_error'] < 1e-6 and r['assembly_occurrences'] == 0
    assert 'CONFIG_CONTROL_DESIGN' in path.read_text()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == r['sha256']


def test_individual_STEP_files_match_manifest(manifest):
    for r in manifest['parts']:
        shape = cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        assert shape.isValid(), r['code']
        assert len(shape.Solids()) == r['solids'], r['code']
        assert shape.Volume() == pytest.approx(r['volume_mm3'], rel=1e-6, abs=1e-5), r['code']
        assert v2.bbox(shape) == pytest.approx(r['bounds_mm'], abs=1e-4), r['code']


def test_not_a_load_or_safety_release(manifest, validation):
    assert manifest['target_payload_kg'] == 1
    for r in (manifest, validation):
        assert not r['hardware_accepted'] and not r['loaded_operation_allowed']
    assert not manifest['motor_torque_curve_verified']
    assert not manifest['independent_brake_selected'] and not manifest['control_firmware_implemented']
    assert not validation['flat_STEP']['solidworks_gui_import_verified']


def test_motion_transforms_from_exported_geometry(manifest):
    parts = {r['name']: r for r in manifest['parts']}
    instances = {r['name']: r for r in manifest['instances']}
    def item(name):
        i = instances[name]; r = parts[i['part']]
        shape = cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        return Item(name, v2.Part(r['name'], shape, r['material'], r['process']), tuple(i['origin_mm']), i['group'])
    for name, expected in [('z_real_motor', (-180, 0, 0)),
                           ('y_real_motor', (-180, 143, -95)), ('carried_bin', (-180, 143, -95))]:
        i = item(name); a, b = i.located().Center(), i.located(dx=-180, dz=-95, q=143).Center()
        assert (b-a).toTuple() == pytest.approx(expected, abs=1e-5)
    shutter = item('io_inner_shutter')
    a, b = shutter.located().Center(), shutter.located(io_open=1).Center()
    assert (b-a).toTuple() == pytest.approx((0, 0, 90), abs=1e-5)


def test_IO_guide_clear_of_storage_bin(manifest):
    parts = {r['name']: r for r in manifest['parts']}
    instances = {r['name']: r for r in manifest['instances']}
    guide = instances['io_shutter_guide_right']
    r = parts[guide['part']]
    right_edge = r['bounds_mm'][3]+guide['origin_mm'][0]
    carried = instances['carried_bin']; bin_part = parts[carried['part']]
    left_edge = bin_part['bounds_mm'][0]+carried['origin_mm'][0]
    assert left_edge-right_edge >= 8-1e-5


def test_sizing_includes_assembly_mass_not_just_payload():
    r = json.loads((OUT/'engineering_checks.json').read_text())
    assert r['fingerprint'] == FINGERPRINT and r['target_payload_kg'] == 1
    for t in r['motor_targets']:
        assert t['moving_mass_with_1kg_payload_and_allowance_kg'] > 2
        arm = .002/(2*math.pi) if t['axis'] == 'Z' else .015
        assert t['required_motor_torque_SF2_Nm'] == pytest.approx(2*t['force_N']*arm/t['assumed_efficiency'])
        assert not t['motor_performance_verified']
    assert not r['self_locking_claimed'] and not r['loaded_operation_allowed']
