"""Display fallback checks independent of the CAD assembly-tree importer."""
import hashlib
import json
import re
from pathlib import Path

import cadquery as cq
import pytest

OUT = Path(__file__).resolve().parents[2]/'model/Manual_3Axis_MVP'


@pytest.fixture(scope='module')
def report():
    return json.loads((OUT/'viewing/compatibility_readback.json').read_text())


def test_flat_step_has_real_solids_without_assembly_tree(report):
    text = (OUT/'viewing'/report['file']).read_text()
    assert 'CONFIG_CONTROL_DESIGN' in text
    assert len(re.findall(r'\bMANIFOLD_SOLID_BREP\s*\(', text)) == 93
    assert not re.search(r'\bNEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(', text)
    assert not re.search(r'\bINVISIBILITY\s*\(', text)


def test_flat_step_matches_original_geometry(report):
    shape = cq.importers.importStep(str(OUT/'viewing'/report['file'])).val()
    original = cq.importers.importStep(str(OUT/report['source_assembly'])).val()
    assert shape.isValid() and len(shape.Solids()) == 93
    assert shape.Volume() == pytest.approx(original.Volume(), rel=1e-6)
    assert report['max_bbox_error_mm'] < 1e-4
    assert report['bbox_mm'] == pytest.approx([-122.5, -370, -6, 122.5, 170, 340], abs=1e-4)


def test_compatibility_does_not_overwrite_original_or_printable_parts(report):
    validation = json.loads((OUT/'validation.json').read_text())
    assert hashlib.sha256((OUT/report['source_assembly']).read_bytes()).hexdigest() == report['source_sha256']
    for row in validation['mesh_checks']:
        assert hashlib.sha256((OUT/'stl'/(row['code']+'.stl')).read_bytes()).hexdigest() == row['sha256']
    assert report['view_mesh']['readback_pass'] and not report['view_mesh']['printable']


def test_report_does_not_claim_unperformed_solidworks_verification(report):
    assert report['readback_pass'] and report['source_unchanged']
    assert report['solidworks_gui_import_verified'] is False
    assert report['loaded_operation_allowed'] is False
