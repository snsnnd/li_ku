"""Inspection renders and a small, explicitly non-manufacturing layout STEP."""
import hashlib
import json
import sys
from dataclasses import replace

import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

from asrs_v03_1 import OUT, ROOT, FINGERPRINT, build_model, v2

sys.path.insert(0, str(ROOT/'cad'/'v03'))
from verify_motion import packaging_model


def colour(part):
    if part.process == 'candidate' or part.name.startswith('Metal_Pinion_Hub'):
        return (.95, .56, .12)
    return v2.COLORS.get(part.material, (.6, .6, .6))[:3]


def main():
    m = build_model()
    out = OUT/'previews'
    out.mkdir(parents=True, exist_ok=True)
    cache = {}
    for p in m.parts.values():
        vertices, faces = p.shape.tessellate(.5, .22)
        cache[p.name] = (np.array([v.toTuple() for v in vertices]), np.asarray(faces))

    def draw(name, items, title, elev=23, azim=-67):
        fig = plt.figure(figsize=(14, 10), dpi=130)
        ax = fig.add_subplot(111, projection='3d', proj_type='ortho')
        points = []
        for i in items:
            if i.part.material == 'guard':
                continue
            vertices, faces = cache[i.part.name]
            vertices = vertices+np.array(i.origin)
            points.append(vertices)
            poly = Poly3DCollection(vertices[faces], facecolors=colour(i.part), edgecolors=(0, 0, 0, 0),
                                    linewidths=0, shade=True, lightsource=LightSource(azdeg=310, altdeg=45))
            ax.add_collection3d(poly)
        p = np.concatenate(points)
        lo, hi = p.min(0), p.max(0)
        ax.set_xlim(lo[0]-15, hi[0]+15)
        ax.set_ylim(lo[1]-15, hi[1]+15)
        ax.set_zlim(lo[2]-10, hi[2]+15)
        ax.set_box_aspect(np.maximum(hi-lo, 1))
        ax.view_init(elev, azim)
        ax.set_title(title, fontsize=12, pad=18)
        ax.set_xlabel('X / mm')
        ax.set_ylabel('Y / mm')
        ax.set_zlabel('Z / mm')
        ax.grid(False)
        ax.set_facecolor('#f5f7f8')
        fig.patch.set_facecolor('#f5f7f8')
        fig.savefig(out/name, bbox_inches='tight')
        plt.close(fig)

    draw('assembly_isometric.png', m.items,
         'V03.1 | actual CAD, guards hidden | orange = unselected hardware')
    draw('moving_module.png', [i for i in m.items if i.group not in ('fixed', 'io_shutter')],
         'V03.1 | reinforced Z backing | Y power node rides Z, not Y')
    draw('x_rack_supports.png', [i for i in m.items if i.name.startswith(('base_panel_', 'x_rack_', 'x_beam_'))],
         'V03.1 | seven bolted X-rack feet | +/-1 mm aligned Y adjustment', 18, -105)
    draw('z_rack_supports.png', [i for i in m.items if i.name.startswith(('z_rack_', 'z_post_', 'z_foot_')) or i.name == 'x_carriage'],
         'V03.1 | 12 mm backing + five supports | maximum span 135 mm', 20, -120)
    draw('y_module.png', [i for i in m.items if i.name.startswith(('y_', 'tray_tube_')) or i.name == 'z_carriage'],
         'V03.1 | shorter moving bridge | separate Z-mounted Y battery', 30, -110)
    draw('io_station.png', [i for i in m.items if i.name.startswith('io_') or i.name == 'base_panel_0'],
         'V03.1 | base-seated flanged legs + matched frame/nest holes', 23, -130)
    (out/'manifest.json').write_text(json.dumps({'fingerprint': FINGERPRINT, 'source': 'CAD tessellation',
                                              'guards_hidden': True, 'hardware_accepted': False}, indent=2))

    # Only motors/pinions become proxies; visible rack teeth remain the real shapes.
    proxies = {i.name: i for i in packaging_model(m)}
    assembly = cq.Assembly(name='V03_1_LAYOUT_ONLY_NOT_FOR_MANUFACTURE')
    expected = 0
    for i in m.items:
        if i.part.material == 'guard':
            continue
        part = proxies[i.name].part if i.part.name.startswith('ZDT_RealMotor') or i.name.endswith('_pinion') else i.part
        assembly.add(part.shape, name=i.name, loc=cq.Location(cq.Vector(*i.origin)), color=cq.Color(*colour(i.part)))
        expected += len(part.shape.Solids())
    target = OUT/'viewing'/'ASRS_V03_1_LIGHT_VIEW.step'
    target.parent.mkdir(parents=True, exist_ok=True)
    assembly.save(str(target))
    readback = cq.importers.importStep(str(target)).val()
    report = {'fingerprint': FINGERPRINT, 'purpose': 'LAYOUT ONLY, NOT FOR MANUFACTURE OR PRINTING',
              'file': target.name, 'bytes': target.stat().st_size,
              'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'expected_solids': expected, 'solid_count': len(readback.Solids()),
              'readback_pass': readback.isValid() and len(readback.Solids()) == expected,
              'rack_teeth_retained': True, 'manufacturing_release_allowed': False}
    (target.parent/'light_view_readback.json').write_text(json.dumps(report, indent=2))
    if not report['readback_pass']:
        raise RuntimeError('Light view failed STEP readback')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
