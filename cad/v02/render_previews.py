"""Inspection previews rendered from actual CAD tessellation, with honest visibility labels."""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from asrs_v02 import COLORS, OUT, bbox, build_model, source_sha256


def main():
    m = build_model()
    directory = OUT/'previews'
    directory.mkdir(parents=True, exist_ok=True)
    cache = {}
    for p in m.parts.values():
        vertices, triangles = p.shape.tessellate(.35, .18)
        cache[p.name] = (np.array([v.toTuple() for v in vertices]), np.array(triangles))

    def draw(filename, items, title, elev=24, azim=-65, q=0, lift=0):
        fig = plt.figure(figsize=(14, 10), dpi=140)
        ax = fig.add_subplot(111, projection='3d', proj_type='ortho')
        all_vertices = []
        for i in items:
            if i.part.material == 'guard':
                continue
            if i.group in ('crank', 'roller', 'spring') and lift:
                vv, tt = i.located(q=q, pin_lift=lift).tessellate(.35, .18)
                vertices = np.array([v.toTuple() for v in vv]); faces = np.array(tt)
            else:
                v, faces = cache[i.part.name]
                offset = np.array(i.origin, dtype=float)
                if i.group in ('y', 'pin', 'bin', 'spring'):
                    offset[1] += q
                if i.group == 'pin':
                    offset[2] += lift
                vertices = v+offset
            all_vertices.append(vertices)
            color = COLORS.get(i.part.material, COLORS['aluminum'])[:3]
            collection = Poly3DCollection(vertices[faces], facecolors=color,
                                          edgecolors=(.15, .19, .22, .18), linewidths=.12,
                                          shade=True, lightsource=matplotlib.colors.LightSource(azdeg=315, altdeg=45))
            ax.add_collection3d(collection)
        vv = np.concatenate(all_vertices)
        lo, hi = vv.min(0), vv.max(0)
        span = np.maximum(hi-lo, 1)
        for axis, a, b in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), lo, hi):
            pad = max((b-a)*.04, 2)
            axis(a-pad, b+pad)
        ax.set_box_aspect(span)
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel('X / mm'); ax.set_ylabel('Y / mm'); ax.set_zlabel('Z / mm')
        ax.set_title(title, fontsize=13, pad=18)
        ax.grid(False)
        ax.set_facecolor('#f5f7f8')
        fig.patch.set_facecolor('#f5f7f8')
        fig.savefig(directory/filename, bbox_inches='tight')
        plt.close(fig)

    draw('assembly_isometric.png', m.items, 'V02 | actual CAD geometry | panels hidden for inspection')
    draw('assembly_front.png', m.items, 'V02 | front view | panels hidden for inspection', 0, -90)
    draw('assembly_side.png', m.items, 'V02 | side view | panels hidden for inspection', 0, 0)
    pickup = [i for i in m.items if i.group in ('z', 'y', 'pin', 'crank', 'roller', 'spring')]
    draw('pickup_retracted.png', pickup, 'Pickup | retracted, pin engaged | bin hidden for inspection', 24, -65)
    draw('pickup_extended_released.png', pickup, 'Pickup | extended 143 mm, pin lifted 14 mm | bin hidden', 24, -65,
         q=m.d.transfer, lift=14)
    (directory/'manifest.json').write_text(json.dumps({
        'generator_sha256': source_sha256(), 'source': 'actual OCCT B-rep tessellation',
        'guards_hidden_in_inspection_views': True, 'render_is_not_a_motion_verification': True,
        'files': sorted(p.name for p in directory.glob('*.png'))}, indent=2), encoding='utf-8')
    print('PREVIEWS_CREATED', directory)


if __name__ == '__main__':
    main()
