"""Regression tests for the actual V02 B-reps, not expected component counts."""
import dataclasses
import math

import pytest

import cadquery as cq

from asrs_v02 import Design, bbox, box, build_model, collisions, dimension_checks


@pytest.fixture(scope="module")
def model():
    return build_model()


def test_all_dimensional_requirements():
    assert all(c["pass"] for c in dimension_checks(Design()))


def test_v01_lowest_level_regression_is_detected():
    old_height = dataclasses.replace(Design(), first_deck=94)
    failed = [c["name"] for c in dimension_checks(old_height) if not c["pass"]]
    assert "lowest_z_block_end_margin" in failed
    assert "lowest_plate_to_x_plate" in failed


def test_short_rail_is_not_accepted():
    short = dataclasses.replace(Design(), y_rail_max=-30)
    assert not next(c["pass"] for c in dimension_checks(short) if c["name"] == "y_extended_rail_margin")


def test_all_parts_valid_single_solids(model):
    assert all(p.shape.isValid() and len(p.shape.Solids()) == 1 for p in model.parts.values())


def test_no_geometry_below_workbench(model):
    assert min(bbox(i.located())[2] for i in model.items) >= -1e-6


def test_support_tubes_below_box(model):
    tube = next(i for i in model.items if i.name == "tray_tube_-44")
    bin_item = next(i for i in model.items if i.name == "carried_bin")
    assert bbox(bin_item.located())[2]-bbox(tube.located())[5] == pytest.approx(4)
    assert tube.located().intersect(bin_item.located()).Volume() < 1e-6


def test_pin_enters_real_eye_void_and_releases(model):
    b = next(i for i in model.items if i.name == "carried_bin").located()
    pin = next(i for i in model.items if i.name == "latch_pin")
    assert pin.located().intersect(b).Volume() < 1e-6
    # At the horizontal eye elevation the pin is in the hole, not outside the handle.
    eye_zone = box(model.x, model.d.tray_y+model.d.eye_offset_y, model.deck+10, 32, 18, 6)
    assert pin.located().intersect(eye_zone).Volume() > 50
    assert pin.located(pin_lift=14).intersect(eye_zone).Volume() < 1e-6


def test_realistic_servo_150_degree_stroke():
    low = 7*(1-math.cos(math.radians(15)))
    high = 7*(1-math.cos(math.radians(165)))
    assert high-low > 13.5
    assert 6+high-16 > 3.5
    assert 6+low < 10


def test_printed_parts_fit_a1(model):
    for p in model.parts.values():
        if p.process == "print":
            b = bbox(p.shape)
            assert max(b[k+3]-b[k] for k in range(3)) <= 256


def test_static_full_assembly(model):
    bad, _ = collisions(model.items, model.allowed)
    assert bad == []


def test_secondary_nut_catch_gap(model):
    nut = next(i for i in model.items if i.name == "z_safety_nut")
    cage = next(i for i in model.items if i.name == "z_safety_cage")
    assert bbox(nut.located())[2]-(cage.origin[2]+5) == pytest.approx(.8)
    assert nut.located().intersect(cage.located()).Volume() < 1e-6


def test_positive_thrust_cross_pin_fits_real_holes(model):
    pin = next(i for i in model.items if i.name == "z_thrust_cross_pin").located()
    for name in ("z_shaft_collar", "z_screw"):
        body = next(i for i in model.items if i.name == name).located()
        assert pin.intersect(body).Volume() < 1e-6
    assert bbox(pin)[5]-bbox(pin)[2] == pytest.approx(2.5)


def test_mgn9h_real_15_by_16_hole_pattern(model):
    block = model.parts["MGN9H_Y"].shape
    for xx in (-7.5, 7.5):
        for yy in (-8, 8):
            assert not block.isInside(cq.Vector(xx, yy, 9), 1e-6)
            assert block.isInside(cq.Vector(xx+1.6, yy, 9), 1e-6)


def test_bin_lateral_float_is_controlled(model):
    tray = next(i for i in model.items if i.name == "carrier_tray").located()
    b = next(i for i in model.items if i.name == "carried_bin").located()
    assert tray.intersect(b.translate((.5, 0, 0))).Volume() < 1e-6
    assert tray.intersect(b.translate((1.5, 0, 0))).Volume() > 1


def test_y_clamp_exports_watertight_stl(model, tmp_path):
    from audit_delivery import audit_stl
    path = tmp_path/'y_clamp.stl'
    cq.exporters.export(model.parts['Y_Belt_Clamp'].shape, str(path), tolerance=.03, angularTolerance=.10)
    result = audit_stl(path)
    assert result['watertight']
    assert result['winding_consistent']
    assert result['connected_bodies'] == 1
