"""Readable inspection renders from V03 CAD, no invented illustrative components."""
import json
from dataclasses import replace
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

from asrs_v03 import OUT,FINGERPRINT,build_model,v2


def main():
    m=build_model();out=OUT/'previews';out.mkdir(exist_ok=True,parents=True)
    cache={}
    for p in m.parts.values():
        vs,fs=p.shape.tessellate(.5,.22)
        cache[p.name]=(np.array([v.toTuple() for v in vs]),np.asarray(fs))
    def draw(name,items,title,elev=23,azim=-67,show_guards=False):
        fig=plt.figure(figsize=(14,10),dpi=130);ax=fig.add_subplot(111,projection='3d',proj_type='ortho')
        points=[]
        for i in items:
            if i.part.material=='guard' and not show_guards:continue
            vs,fs=cache[i.part.name];vs=vs+np.array(i.origin);points.append(vs)
            color=v2.COLORS.get(i.part.material,(.5,.55,.6))[:3]
            if i.part.process=='candidate':color=(.95,.56,.12)
            if 'Rack_' in i.part.name or 'Pinion_' in i.part.name:color=(.18,.62,.78)
            if 'Power_' in i.part.name:color=(.19,.52,.62)
            if i.part.process=='print_paper':color=(.95,.95,.88)
            if i.part.material=='guard':color=(.57,.79,.85,.15)
            poly=Poly3DCollection(vs[fs],facecolors=color,edgecolors=(0,0,0,0),linewidths=0,
                shade=True,lightsource=LightSource(azdeg=310,altdeg=45))
            ax.add_collection3d(poly)
        pts=np.concatenate(points);lo=pts.min(0);hi=pts.max(0);span=np.maximum(hi-lo,1)
        ax.set_xlim(lo[0]-15,hi[0]+15);ax.set_ylim(lo[1]-15,hi[1]+15);ax.set_zlim(lo[2]-10,hi[2]+15)
        ax.set_box_aspect(span);ax.view_init(elev,azim);ax.set_title(title,fontsize=12,pad=18)
        ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm');ax.set_zlabel('Z / mm');ax.grid(False)
        ax.set_facecolor('#f5f7f8');fig.patch.set_facecolor('#f5f7f8')
        fig.savefig(out/name,bbox_inches='tight');plt.close(fig)
    draw('assembly_isometric.png',m.items,'V03 actual CAD | guard panels hidden | orange = UNSELECTED candidate hardware')
    draw('assembly_front.png',m.items,'V03 front | four independent columns + left IO bay | panels hidden',0,-90)
    drive=[i for i in m.items if i.group not in ('fixed','io_shutter')]
    draw('moving_module.png',drive,'Moving module | real motors + local power nodes | candidate packs/brake/reducer in orange')
    draw('io_station.png',[i for i in m.items if i.name.startswith('io_')],
         'Dedicated IO station | human access from LEFT | transparent walls/doors hidden',23,-130)
    draw('io_station_enclosed.png',[i for i in m.items if i.name.startswith('io_')],
         'IO station | transparent shields shown | inner shutter closed, human port at LEFT',23,-130,True)
    node=[]
    for i in m.items:
        if not (i.name.startswith('x_power_') or i.name in ('x_battery_candidate','x_esp32_candidate')):continue
        if i.name=='x_power_lid':continue
        if i.name in ('x_power_case','x_power_tray'):
            xx,yy,zz=i.origin;i=replace(i,origin=(xx,yy,zz-60))
        node.append(i)
    draw('power_node_open.png',node,
         'EXPLODED INSPECTION ONLY | shell/tray lowered 60 mm | orange = candidate pack/controller',35,-65)
    draw('one_column.png',[i for i in m.items if i.name.startswith(('column_0_','stored_bin_0_','cell_0_','shelf_angle_0_'))],
         'Independent column | round/slot location + bolted carrier | reference tag and box tag are distinct')
    (out/'manifest.json').write_text(json.dumps({'fingerprint':FINGERPRINT,
        'source':'CAD tessellation','guards_hidden':True,'orange_candidates_not_selected':True},indent=2))
    print('PREVIEWS',out)


if __name__=='__main__':main()
