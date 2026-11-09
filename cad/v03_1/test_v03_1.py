"""V03.1 regressions: interfaces, inherited motion/teeth and explicit limits."""
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asrs_v03_1 import FINGERPRINT, ROOT, X_SUPPORTS, Z_SUPPORTS, baseline, box, build_model, cyl
from validate_v03_1 import connection_checks, engineering, mating_area, motion_poses

sys.path.insert(0, str(ROOT/'cad'/'v03'))
import test_v03 as original


@pytest.fixture(scope='session', autouse=True)
def record_sources(record_testsuite_property):
    record_testsuite_property('geometry_fingerprint', FINGERPRINT)
    for path in (Path(__file__), Path(__file__).with_name('validate_v03_1.py'), ROOT/'cad/v03/test_v03.py', ROOT/'cad/v03/control_contract.py'):
        record_testsuite_property(path.name+'_sha256', hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture(scope='module')
def model():
    return build_model()


@pytest.fixture(scope='module')
def joints(model):
    return connection_checks(model)


@pytest.fixture(scope='module')
def sizing(model):
    return engineering(model)


@pytest.mark.parametrize('name', [
    'test_geometry_valid', 'test_all_three_axes_are_rack_driven',
    'test_independent_columns_have_two_locators_and_four_posts', 'test_prints_fit_256mm',
    'test_battery_and_controller_do_not_overlap_case', 'test_independent_safety_track_not_printed',
    'test_box_markers_and_camera_reserved', 'test_io_is_distinct_from_storage',
    'test_static_assembly', 'test_nominal_front_marker_sightlines',
])
def test_inherited_geometry_on_revised_model(model, name):
    getattr(original, name)(model)


@pytest.mark.parametrize('axis', ['x', 'y', 'z'])
def test_exact_axis_phases(model, axis):
    original.test_actual_axis_pinion_phases(model, axis)


def test_exact_teeth_and_segment_splice():
    original.test_rack_phase_repeats_at_segment_boundary()
    original.test_actual_involute_mesh_across_pitch_and_splice()


def test_original_marker_assets():
    original.test_metric_marker_assets()


@pytest.mark.parametrize('axis', ['X', 'Y', 'Z'])
def test_inherited_local_command_gates(axis):
    original.test_local_command_gate(axis, original.ready.__wrapped__())


@pytest.mark.parametrize('name', ['test_z_needs_independent_brake', 'test_mutual_door_and_box_occupancy_logic',
                                 'test_camera_does_not_override_homing_or_freshness'])
def test_inherited_safety_contracts(name):
    getattr(original, name)(original.ready.__wrapped__())


def test_all_declared_connections_have_real_mating_area(joints):
    assert len(joints) == 42
    assert all(c['geometric_connection_pass'] for c in joints), [c for c in joints if not c['geometric_connection_pass']]
    assert all(not c['fastener_strength_verified'] for c in joints)


def test_edge_contact_does_not_count_as_support():
    a = box(0, 0, 0, 10, 10, 10)
    b = box(10, 0, 10, 10, 10, 10)
    assert a.distance(b) < 1e-6  # only a shared edge
    assert mating_area(a, b) == pytest.approx(0)
    assert mating_area(a, b.translate((-10, 0, 0))) == pytest.approx(100)


def test_original_six_mm_y_gap_is_rejected():
    manifest = json.loads((ROOT/'model/V03/manifest.json').read_text())
    items = []
    for name in ('y_rack_backbone', 'y_rack_standoff_-220'):
        row = next(i for i in manifest['instances'] if i['name'] == name)
        s = baseline.cq.importers.importStep(str(ROOT/'model/V03/parts'/(row['part']+'.step'))).val()
        p = baseline.v2.Part(row['part'], s, 'aluminum', 'machined')
        items.append(baseline.Item(name, p, row['origin_mm'], row['group']))
    probe = SimpleNamespace(items=items, connections=[{'a': items[0].name, 'b': items[1].name}])
    row = connection_checks(probe)[0]
    assert row['gap_mm'] == pytest.approx(6)
    assert not row['geometric_connection_pass']


def test_broken_revised_joint_is_rejected(model):
    names = ('x_rack_foot_90', 'x_rack_backbone')
    items = [dataclasses.replace(i) for i in model.items if i.name in names]
    foot = next(i for i in items if i.name == names[0])
    xx, yy, zz = foot.origin
    foot.origin = (xx, yy-2, zz)
    probe = SimpleNamespace(items=items, connections=[{'a': names[0], 'b': names[1]}])
    assert not connection_checks(probe)[0]['geometric_connection_pass']


def test_x_feet_connect_backing_to_every_base_panel(model, joints):
    assert sum(i.name.startswith('x_rack_foot_') for i in model.items) == len(X_SUPPORTS)
    for xx in X_SUPPORTS:
        name = f'x_rack_foot_{xx}'
        assert any(c['a'] == name and c['b'] == 'x_rack_backbone' for c in joints)
        assert any(c['a'] == name and c['b'].startswith('base_panel_') for c in joints)
    assert {c['b'] for c in joints if c['a'].startswith('x_rack_foot_') and c['b'].startswith('base_panel_')} == {
        'base_panel_0', 'base_panel_1', 'base_panel_2'}


def test_x_backing_screw_pilots_are_real(model):
    item = next(i for i in model.items if i.name == 'x_rack_backbone')
    s = item.located()
    for xx in X_SUPPORTS:
        for off in (-8, 8):
            for zz in (56, 76):
                probe = cyl(xx+off, -328, zz, 1.60, 6, (0, 1, 0))
                assert s.intersect(probe).Volume() < 1e-6
                # A displaced probe hits metal; an absent entire backing cannot pass.
                assert s.intersect(probe.translate((0, 0, 2))).Volume() > 1


def test_io_load_path_and_matched_frame_holes(model, joints):
    items = {i.name: i for i in model.items}
    for a in (-65, 65):
        for yy in (10, 140):
            name = f'io_leg_{a}_{yy}'
            b = items[name].located().BoundingBox()
            assert b.zmin == pytest.approx(6)
            assert b.zmax == pytest.approx(190)
            assert any(c['a'] == name and c['b'] == 'io_deck_frame' for c in joints)
            # Both leg and base must have the four mating fastener bores.
            for off in (-14, 14):
                for dy in (-14, 14):
                    p = cyl(-150+a+off, yy+dy, 0, 2.0, 12)
                    assert items[name].located().intersect(p).Volume() < 1e-6
                    assert items['base_panel_0'].located().intersect(p).Volume() < 1e-6
                    washer = cyl(-150+a+off, yy+dy, 12, 5, 1)
                    assert items[name].located().intersect(washer).Volume() < 1e-6
    frame = items['io_deck_frame'].located()
    for a in (-52, 52):
        for yy in (15, 115):
            assert frame.intersect(cyl(-150+a, yy, 190, 1.6, 6)).Volume() < 1e-6


def test_z_backing_preserves_mating_plane_and_has_five_supports(model):
    item = next(i for i in model.items if i.name == 'z_rack_backbone')
    b = item.located().BoundingBox()
    assert b.xlen == pytest.approx(12)
    assert b.xmax == pytest.approx(model.x-122)
    assert [i.origin[2] for i in model.items if i.name.startswith('z_rack_standoff_')] == list(Z_SUPPORTS)
    assert max(b-a for a, b in zip(Z_SUPPORTS, Z_SUPPORTS[1:])) == 135


def test_power_bracket_edge_threads_do_not_break_into_guide_bores(model):
    carriage = next(i for i in model.items if i.name == 'z_carriage').located()
    for offset in (-63, -53):
        # Full annular metal around the edge tap, over its intended engagement.
        outer = cyl(model.x+55.5, -232, model.deck+offset, 2.3, 9, (1, 0, 0))
        inner = cyl(model.x+55.4, -232, model.deck+offset, 2.1, 9.2, (1, 0, 0))
        wall = outer.cut(inner)
        assert carriage.intersect(wall).Volume() == pytest.approx(wall.Volume(), rel=1e-5)


def test_three_motors_remain_but_y_battery_rides_z(model):
    items = {i.name: i for i in model.items}
    for axis in ('x', 'y', 'z'):
        assert items[axis+'_real_motor'].group == axis
    for suffix in ('power_tray', 'power_case', 'power_lid', 'battery_candidate', 'esp32_candidate'):
        assert items['y_'+suffix].group == 'z'
        a = items['y_'+suffix].located(q=0).Center()
        b = items['y_'+suffix].located(q=143).Center()
        assert (a-b).Length < 1e-6
        c = items['y_'+suffix].located(dz=20).Center()
        assert c.z-a.z == pytest.approx(20)
    assert not any(i.name.startswith('y_power_leg_') for i in model.items)
    b = items['y_puller_plate'].part.shape.BoundingBox()
    assert b.xmax == pytest.approx(120)


def test_mass_and_offset_reduction_is_quantified_not_certified(sizing):
    y = sizing['Y_offset_comparison']
    assert y['V03_1_same_group_kg'] < 1.1
    assert y['moment_reduction_fraction'] > .65
    assert sizing['Z_backbone_screen']['max_support_span_mm'] == 135
    assert sizing['Z_backbone_screen']['simply_supported_centre_deflection_mm'] < .02
    assert not sizing['hardware_accepted']
    assert not sizing['manufacturing_release_allowed']
    assert not sizing['printed_Z_tooth_screen']['allowable_printed_strength_verified']


def test_full_motion_schedule_retains_all_baseline_phases(model):
    poses = motion_poses(model, 12)
    assert len(poses) == 1097
    assert {p[0] for p in poses} == {'transfer', 'released_withdraw', 'pin_clearance', 'z_traverse',
                                     'x_traverse', 'latch', 'io_shutter'}
    assert len({p[5] for p in poses if p[0] == 'transfer' and p[5] is not None}) == 20


def test_baseline_evidence_remains_at_original_fingerprint():
    for name in ('manifest.json', 'static_validation.json', 'motion_validation.json', 'engineering_checks.json', 'delivery_audit.json'):
        assert json.loads((ROOT/'model/V03'/name).read_text())['fingerprint'] == baseline.FINGERPRINT
    assert FINGERPRINT != baseline.FINGERPRINT
