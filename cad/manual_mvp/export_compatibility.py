"""Flatten verified STEP geometry for readers that fail on the assembly tree.

No original assembly, component STEP or printable STL is overwritten. There is
no claim of SolidWorks GUI verification unless it has actually been performed.
"""
import hashlib
import json
import re
from pathlib import Path

import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

OUT = Path(__file__).resolve().parents[2]/'model/Manual_3Axis_MVP'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(shape):
    b = shape.BoundingBox()
    return [b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax]


def entity_count(text, entity):
    return len(re.findall(r'\b'+entity+r'\s*\(', text))


def main():
    source = OUT/'Manual_3Axis_Assembly.step'
    validation = json.loads((OUT/'validation.json').read_text())
    original_hash = sha(source)
    if original_hash != validation['assembly_step']['sha256']:
        raise ValueError('Assembly changed since validation; refusing to flatten an unaudited file')
    original = cq.importers.importStep(str(source)).val()
    expected = validation['assembly_step']['solid_count']
    if not original.isValid() or len(original.Solids()) != expected:
        raise ValueError('Invalid or incomplete source assembly')
    out = OUT/'viewing'
    out.mkdir(parents=True, exist_ok=True)
    target = out/'Manual_3Axis_SOLIDS_AP203.step'
    # Baked world-space solids: no occurrences, references, colors or visibility
    # states that require an assembly-aware importer.
    compound = cq.Compound.makeCompound(original.Solids())
    STEPControl_Writer()  # Initialise OCCT STEP parameters before reading them.
    schema = Interface_Static.CVal_s('write.step.schema')
    assembly_mode = Interface_Static.IVal_s('write.step.assembly')
    try:
        if not Interface_Static.SetCVal_s('write.step.schema', 'AP203'):
            raise RuntimeError('Cannot select AP203')
        if not Interface_Static.SetIVal_s('write.step.assembly', 0):
            raise RuntimeError('Cannot disable STEP assembly generation')
        writer = STEPControl_Writer()
        if writer.Transfer(compound.wrapped, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError('STEP transfer failed')
        if writer.Write(str(target)) != IFSelect_RetDone:
            raise RuntimeError('STEP write failed')
    finally:
        Interface_Static.SetCVal_s('write.step.schema', schema)
        Interface_Static.SetIVal_s('write.step.assembly', assembly_mode)
    text = target.read_text()
    check = cq.importers.importStep(str(target)).val()
    bb = bounds(check)
    error = max(abs(a-b) for a, b in zip(bb, bounds(original)))
    volume_error = abs(check.Volume()-original.Volume())/original.Volume()
    flat_ok = (check.isValid() and len(check.Solids()) == expected and error < 1e-4 and volume_error < 1e-6
               and entity_count(text, 'NEXT_ASSEMBLY_USAGE_OCCURRENCE') == 0
               and entity_count(text, 'MANIFOLD_SOLID_BREP') == expected
               and entity_count(text, 'INVISIBILITY') == 0)
    if not flat_ok:
        raise RuntimeError('Flattened STEP failed geometry or hierarchy checks')

    # This is a whole-machine viewing mesh, not a printable assembly STL.
    mesh_path = out/'Manual_3Axis_VIEW_ONLY.stl'
    cq.exporters.export(check, str(mesh_path), tolerance=.12, angularTolerance=.2)
    mesh = trimesh.load_mesh(mesh_path, process=False)
    mesh_error = max(abs(a-b) for a, b in zip(mesh.bounds.flatten(), bb))
    mesh_ok = bool(np.isfinite(mesh.vertices).all() and len(mesh.faces) > 0 and mesh_error < .1)
    if not mesh_ok:
        raise RuntimeError('Whole-machine viewing mesh failed bounds check')

    # Screenshot of the imported fallback itself, not the source CAD generator.
    vertices, faces = check.tessellate(.45, .18)
    v = np.asarray([p.toTuple() for p in vertices])
    fig = plt.figure(figsize=(12, 10), dpi=130)
    ax = fig.add_subplot(111, projection='3d', proj_type='ortho')
    poly = Poly3DCollection(v[np.asarray(faces)], facecolors=(.2, .57, .68), edgecolors=(0, 0, 0, 0),
                           shade=True, lightsource=LightSource(azdeg=310, altdeg=45))
    ax.add_collection3d(poly)
    lo, hi = v.min(0), v.max(0)
    ax.set_xlim(lo[0]-10, hi[0]+10)
    ax.set_ylim(lo[1]-10, hi[1]+10)
    ax.set_zlim(lo[2]-10, hi[2]+10)
    ax.set_box_aspect(hi-lo)
    ax.view_init(24, -48)
    ax.set_title('AP203 FLAT SOLIDS / imported fallback / 93 bodies / NO motors')
    ax.set_xlabel('X mm'); ax.set_ylabel('Y mm'); ax.set_zlabel('Z mm')
    ax.grid(False)
    image = out/'solid_part_readback.png'
    fig.savefig(image, bbox_inches='tight')
    plt.close(fig)

    report = {'source_assembly': source.name, 'source_fingerprint': validation['fingerprint'],
              'source_sha256': original_hash, 'source_unchanged': sha(source) == original_hash,
              'exporter_sha256': sha(Path(__file__)),
              'purpose': 'Display/import compatibility; all original geometry, no assembly hierarchy or colors.',
              'file': target.name, 'sha256': sha(target), 'bytes': target.stat().st_size,
              'schema': 'AP203', 'valid': check.isValid(), 'solid_count': len(check.Solids()),
              'expected_solids': expected, 'bbox_mm': bb, 'max_bbox_error_mm': error,
              'relative_volume_error': volume_error, 'assembly_occurrences': entity_count(text, 'NEXT_ASSEMBLY_USAGE_OCCURRENCE'),
              'hidden_entities': entity_count(text, 'INVISIBILITY'), 'readback_pass': flat_ok,
              'view_mesh': {'file': mesh_path.name, 'sha256': sha(mesh_path), 'face_count': len(mesh.faces),
                            'bbox_error_mm': mesh_error, 'readback_pass': mesh_ok, 'printable': False},
              'solidworks_gui_import_verified': False, 'user_application_available': False,
              'hardware_accepted': False, 'loaded_operation_allowed': False,
              'note': 'Successful OCCT readback/render does not prove display in the user CAD application.'}
    (out/'compatibility_readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
