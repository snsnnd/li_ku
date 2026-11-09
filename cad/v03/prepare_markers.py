"""Download fixed-version official AprilTag images and make metric print sheets.

Only data images/license are fetched; no downloaded code is executed.
"""
from pathlib import Path
import concurrent.futures
import hashlib
import io
import json
import urllib.request
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'model'/'V03'/'markers'
COMMIT='f3fd9a7add5bfd82a886fc65240fdb8e3c9ac5a1'
BASE=f'https://raw.githubusercontent.com/AprilRobotics/apriltag-imgs/{COMMIT}/'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    entries=[(j,f'BIN-{j+1:03d}') for j in range(20)]
    entries += [(100+j,f'COLUMN-{j+1}') for j in range(4)]+[(200,'IO-STATION')]
    def get(entry):
        ident,label=entry;relative=f'tag36h11/tag36_11_{ident:05d}.png'
        data=urllib.request.urlopen(BASE+relative,timeout=30).read()
        image=Image.open(io.BytesIO(data)).convert('L')
        if image.size!=(10,10):raise ValueError('Unexpected AprilTag image extent')
        pixels=list(image.getdata())
        if any(pixels[x]!=255 or pixels[90+x]!=255 for x in range(10)):
            raise ValueError('Quiet margin missing')
        source=OUT/f'tag36h11_{ident:03d}_source.png'
        if source.exists() and source.read_bytes()!=data:raise FileExistsError(source)
        source.write_bytes(data)
        image.resize((1000,1000),Image.Resampling.NEAREST).save(OUT/f'{label}.png',dpi=(793.75,793.75))
        rects=''.join(f'<rect x="{x}" y="{y}" width="1" height="1"/>'
            for y in range(10) for x in range(10) if pixels[y*10+x]<128)
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="32mm" height="32mm" viewBox="0 0 10 10"><rect width="10" height="10" fill="white"/><g fill="black">{rects}</g></svg>'
        (OUT/f'{label}.svg').write_text(svg,encoding='utf-8')
        return {'id':ident,'label':label,'family':'tag36h11','outer_card_mm':32,
            'detected_black_border_square_mm':25.6,'source_url':BASE+relative,
            'source_sha256':hashlib.sha256(data).hexdigest(),'pixels':pixels}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(get,entries))
    licence=urllib.request.urlopen(BASE+'LICENSE',timeout=30).read()
    (OUT/'LICENSE.apriltag-imgs').write_bytes(licence)
    sheet=['<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">',
           '<rect width="210" height="297" fill="white"/>',
           '<text x="10" y="10" font-size="3">V03 AprilTag36h11 | print 100%, NO fit-to-page | card 32mm, black square 25.6mm</text>']
    for j,row in enumerate(rows):
        ox,oy=10+(j%5)*39,18+(j//5)*46
        sheet.append(f'<g transform="translate({ox},{oy}) scale(3.2)" fill="black">')
        for y in range(10):
            for x in range(10):
                if row['pixels'][10*y+x]<128:sheet.append(f'<rect x="{x}" y="{y}" width="1" height="1"/>')
        sheet.append(f'</g><text x="{ox}" y="{oy+37}" font-size="3">{row["label"]} / ID {row["id"]}</text>')
    sheet.append('<path d="M10 270H60 M10 268V272 M60 268V272" stroke="black" stroke-width=".3"/><text x="10" y="277" font-size="3">Measure this bar: 50mm. Do not use scaled screenshots as markers.</text></svg>')
    (OUT/'A4_32mm_marker_sheet.svg').write_text('\n'.join(sheet),encoding='utf-8')
    # Vector PDF in millimetre coordinates; no raster interpolation at marker edges.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig=plt.figure(figsize=(210/25.4,297/25.4));ax=fig.add_axes([0,0,1,1])
    ax.set_xlim(0,210);ax.set_ylim(297,0);ax.axis('off')
    ax.text(10,10,'V03 AprilTag36h11 | 100%, no fit-to-page | outer 32mm; black square 25.6mm',fontsize=6)
    for j,row in enumerate(rows):
        ox,oy=10+(j%5)*39,18+(j//5)*46
        for y in range(10):
            for x in range(10):
                if row['pixels'][10*y+x]<128:ax.add_patch(Rectangle((ox+x*3.2,oy+y*3.2),3.2,3.2,color='black',linewidth=0))
        ax.text(ox,oy+37,f'{row["label"]} / ID {row["id"]}',fontsize=7)
        row.pop('pixels')
    ax.plot([10,60],[270,270],color='black',linewidth=.7);ax.text(10,277,'Calibration bar: 50mm',fontsize=8)
    fig.savefig(OUT/'A4_32mm_marker_sheet.pdf');plt.close(fig)
    (OUT/'marker_manifest.json').write_text(json.dumps({'commit':COMMIT,'tags':rows,
        'ids_are_not_storage_coordinates':True,'actual_camera_decode_test_passed':False},indent=2))
    print('MARKERS_PREPARED',len(rows),OUT)


if __name__=='__main__':main()
