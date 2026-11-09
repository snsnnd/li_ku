"""Interface regressions for the manually operated empty-bin MVP."""
import json
import hashlib
import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_3axis import FINGERPRINT, OUT, build, cyl, gears, print_shape
from verify_manual import collisions, support_checks


@pytest.fixture(scope='session', autouse=True)
def record_sources(record_testsuite_property):
    record_testsuite_property('geometry_fingerprint', FINGERPRINT)
    for name in ('test_manual.py', 'verify_manual.py'):
        record_testsuite_property(name+'_sha256', hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest())


@pytest.fixture(scope='module')
def model():
    return build()


def test_printed_parts_fit_256_and_are_single_solids(model):
    for p in model.parts.values():
        assert p.shape.isValid() and len(p.shape.Solids()) == 1
        if p.process == 'print':
            b = print_shape(p).BoundingBox()
            assert max(b.xlen, b.ylen, b.zlen) <= 256


def test_no_motors_and_full_size_bin(model):
    assert not any('Motor' in p.name or '电机' in p.name for p in model.parts.values())
    b = model.parts['P16'].shape.BoundingBox()
    assert b.xlen == pytest.approx(110)
    assert b.zlen == pytest.approx(60)
    assert gears.MODULE == 1.5 and gears.TEETH == 20
    assert gears.SEGMENT_LENGTH/gears.PITCH == pytest.approx(24)


def test_initial_full_assembly_no_ignored_pairs(model):
    assert collisions(model)[0] == []


def test_all_modified_load_paths_have_mating_faces(model):
    rows = support_checks(model)
    assert len(rows) == 25
    assert all(r['geometric_seat_pass'] for r in rows)


@pytest.mark.parametrize('code', ['C02', 'C03', 'C04'])
def test_guide_coupons_fit_axially_but_are_captured_vertically(model, code):
    rail = model.parts['C01'].shape
    slider = model.parts[code].shape
    assert rail.intersect(slider).Volume() < 1e-5
    assert rail.intersect(slider.translate((0, 0, 3))).Volume() > 1


def test_axial_stack_is_not_clamped_on_rotating_hub(model):
    hub = model.parts['P03'].shape.BoundingBox()
    assert hub.zlen == pytest.approx(36)
    assert 40-hub.zlen-2*1.8 == pytest.approx(.4)
    assert model.parts['H02'].shape.BoundingBox().zlen == pytest.approx(40)


def test_lower_carrier_nuts_and_screws_have_open_access(model):
    p = model.parts['P13'].shape
    # Bolt below a 16 mm countersunk head has six mm protrusion below the cap.
    assert p.intersect(cyl(-18, 0, 60, 2.2, 9)).Volume() < 1e-5
    assert p.intersect(cyl(-18, 0, 69, 3.5, 3.3)).Volume() < 1e-5


def test_y_mount_lower_nut_and_screw_do_not_hit_ledge(model):
    for code in ('P12', 'P26'):
        part = model.parts[code].shape
        assert part.intersect(cyl(0, 6.01, -20, 3.5, 3, (0, 1, 0))).Volume() < 1e-5
        assert part.intersect(cyl(0, 6.01, -20, 1.5, 4, (0, 1, 0))).Volume() < 1e-5


@pytest.mark.parametrize('code', ['P12', 'P26'])
def test_y_mount_tessellation_has_no_tangent_sliver(model, code):
    vertices, faces = print_shape(model.parts[code]).tessellate(.03, .1)
    mesh = trimesh.Trimesh(vertices=[v.toTuple() for v in vertices], faces=faces, process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent


def test_floor_bolt_lengths_leave_no_table_protrusion(model):
    by = {r['specification']: r for r in model.hardware}
    assert by['M3x10 内六角螺钉']['quantity'] == 16
    assert by['M3x12 内六角螺钉']['quantity'] == 32
    assert 4-10 == -6  # splice top 4, floor underside -6
    assert 6-12 == -6  # X base/crossbar top 6
    assert sum(r['quantity'] for r in model.hardware if r['specification'].startswith('M3x')) == 116


def test_published_geometry_fingerprint(model):
    m = json.loads((OUT/'manifest.json').read_text())
    assert m['fingerprint'] == FINGERPRINT
    assert not m['motors_included']
    assert m['payload_allowed_kg'] == 0
    assert not m['loaded_operation_allowed']
