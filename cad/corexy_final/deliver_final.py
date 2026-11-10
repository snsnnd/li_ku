"""C04 review drawings and previews, rendered from the verified exported parts."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from corexy_final import ROOT,OUT,FINGERPRINT,Model,Item,v2,belt_shape,HOME_X,HOME_Y
sys.path.insert(0,str(ROOT/'cad/manual_mvp'))
import drawings as util


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def load():
    manifest=json.loads((OUT/'manifest.json').read_text());report=json.loads((OUT/'validation.json').read_text())
    if manifest['fingerprint']!=FINGERPRINT or report['fingerprint']!=FINGERPRINT or not report['mechanical_geometry_package_pass']:raise RuntimeError('C04 export stale or unverified')
    m=Model()
    for r in manifest['parts']:
        s=cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        m.parts[r['name']]=v2.Part(r['name'],s,r['material'],r['process'],r['holes'],r['note'])
    for r in manifest['instances']:m.add(r['name'],m.parts[r['part']],tuple(r['origin_mm']),r['group'])
    return m,manifest


def preview(m,name,args=None,detail=False):
    args=args or {};fig=plt.figure(figsize=(13,10),dpi=140);ax=fig.add_subplot(111,projection='3d',proj_type='ortho');points=[]
    for i in m.items:
        if i.part.material=='guard' or i.name=='maintenance_pin' and args:continue
        if detail and not (i.name.startswith(('terminal_','tension_','motor_','idler_','belt_','gantry_','x_')) or i.name=='xy_plate'):continue
        s=i.located(**args);vs,fs=s.tessellate(.6,.23);v=np.array([p.toTuple() for p in vs]);points.append(v)
        col=v2.COLORS.get(i.part.material,(.5,.5,.5))[:3]
        if i.name=='belt_A':col=(.05,.43,.85)
        elif i.name=='belt_B':col=(.98,.46,.08)
        elif i.part.process=='candidate':col=(.95,.56,.12)
        ax.add_collection3d(Poly3DCollection(v[np.asarray(fs)],facecolors=col,edgecolors=(0,0,0,0),shade=True,lightsource=LightSource(310,45)))
    p=np.concatenate(points);lo,hi=p.min(0),p.max(0)
    ax.set_xlim(lo[0]-10,hi[0]+10);ax.set_ylim(lo[1]-10,hi[1]+10);ax.set_zlim(lo[2]-10,hi[2]+10)
    ax.set_box_aspect(hi-lo);ax.view_init(25,-51);ax.grid(False);ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_zlabel('Z mm')
    ax.set_title('C04 / Fixed A+B CoreXY + travelling TR8x2 Z + rigid fork\nGuard panels omitted / MECHANICAL REVIEW, NOT MANUFACTURING OR LOAD RELEASE')
    path=OUT/'previews'/name;fig.savefig(path,bbox_inches='tight');plt.close(fig);return path


def previews(m):
    (OUT/'previews').mkdir(parents=True,exist_ok=True)
    preview(m,'C04_assembly.png');preview(m,'C04_drive_detail.png',detail=True)
    preview(m,'C04_storage_pickup.png',{'dy':143,'dz':4,'bin_pose':[90,158,384]})
    preview(m,'C04_IO_pickup.png',{'dx':-180,'dy':143,'dz':-83,'door':1,'bin_pose':[-90,158,297]})
    fig,axes=plt.subplots(1,2,figsize=(13,7),dpi=140)
    for axis,ax,col in [('A',axes[0],'#0875d1'),('B',axes[1],'#ed781f')]:
        s=belt_shape(axis);vs,fs=s.tessellate(.3,.15);v=np.array([p.toTuple() for p in vs])
        ax.add_collection(PolyCollection(v[np.asarray(fs)][:,:,:2],facecolors=col,edgecolors='none'))
        ax.scatter([HOME_X-35,HOME_X+35],[HOME_Y,HOME_Y],marker='s',c='#333c45',label='Terminal X centres (Y schematic)')
        ax.set_xlim(-320,320);ax.set_ylim(-390,210);ax.set_aspect('equal');ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_title('C04 open belt '+axis);ax.legend(loc='lower left',fontsize=7)
    fig.suptitle('A = dx + dy; B = -dx + dy / Left sliders 0..2 mm, separate locks\nSupplier GT2 tooth profiles omitted; installation tension NOT selected')
    fig.savefig(OUT/'previews/C04_AB_belt_paths.png',bbox_inches='tight');plt.close(fig)
    (OUT/'previews/manifest.json').write_text(json.dumps({'fingerprint':FINGERPRINT,'generator_sha256':sha(Path(__file__)),'images':{p.name:sha(p) for p in sorted((OUT/'previews').glob('*.png'))}},indent=2))
    print('C04 PREVIEWS READY',flush=True)


def lists(manifest):
    for filename,rows in [('打印清单.csv',[r for r in manifest['parts'] if r['process']=='print']),('采购与金属加工清单.csv',[r for r in manifest['parts'] if r['process']!='print'])]:
        with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['code','name','quantity','material','process','note'],extrasaction='ignore');w.writeheader();w.writerows(rows)


def border(c,code,title,scale='说明/示意不按比例'):
    c.setStrokeColorRGB(.1,.15,.2);c.setLineWidth(.45);c.rect(8*mm,8*mm,404*mm,281*mm);c.line(8*mm,25*mm,412*mm,25*mm)
    util.text(c,12,282,title,12);util.text(c,12,274,'C04 机械收敛版 / 底部固定A+B、随动金属丝杆Z、固定叉 / 1kg设计目标，未带载验收',9)
    util.text(c,12,18,f'{code} | mm | A3横向 | 比例 {scale} | 机械几何评审稿，非制造/运行放行',8)
    util.text(c,12,12,'尺寸/孔表非完整加工公差；金属件禁止打印替代。实际选型、紧固、防坠、安全链与固件待验收。',7);util.text(c,310,12,FINGERPRINT[:20],7)


def drawings(m,manifest):
    util.font();(OUT/'drawings').mkdir(parents=True,exist_ok=True)
    pm=json.loads((OUT/'previews/manifest.json').read_text())
    if pm['fingerprint']!=FINGERPRINT or pm['generator_sha256']!=sha(Path(__file__)):raise RuntimeError('Previews stale')
    target=OUT/'drawings/CoreXY机械收敛_C04_评审图.pdf';c=canvas.Canvas(str(target),pagesize=(util.W,util.H));c.setTitle('C04机械收敛评审图 — 非制造/带载运行放行');codes=[]
    for code,title,image in [('A01','C04整机结构','C04_assembly.png'),('A02','C04底部传动与张紧细节','C04_drive_detail.png'),('B01','C04双层开口皮带路径','C04_AB_belt_paths.png')]:
        border(c,code,title);c.drawImage(str(OUT/'previews'/image),14*mm,38*mm,390*mm,225*mm,preserveAspectRatio=True,mask='auto');codes.append(code);c.showPage()
    sections=[('S01','接口收敛与连接装配',[
        'C03拓扑保留：两台底部固定A/B电机，双金属箱梁，随动TR8x2升降塔，固定双钢叉。第三台电机驱动Z。',
        'Phidgets TRM4226_0齿板+背板各18×18.8×4；四孔10×9.4网格，孔径2.4±0.2；背板沉孔4.4深2。供应商原图见references。',
        '采购真实GT2M-06齿板；本模型平面包络不含齿形，不得按光滑包络自制夹齿。每端名义夹持18，含末端9尾段。',
        '端夹X中心±35；仅左端沿+X移动0..2。M3×25横向拉紧，两颗M3独立槽锁紧；调节行程不是推荐皮带拉伸量。',
        'A电机安装面Z78，B升至Z84；B轴伸入带轮约12，下夹紧轮毂长度仍6。实际采购分体夹紧轮毂、传扭试验待完成。',
        '固定惰轮补内圈顶垫片；定制肩轴补六角孔。肩轴配合、预载、螺纹与供应商额定承载仍需实际确认。',
        '横梁端板Z43..51，梁底壁Z51..55。8颗M4×10向上，头部Z43..47；轴线在端板局部X±10、Y±55。',
        '端板通孔4.2、底部沉孔8深4.1，梁底壁原有3.3底孔；螺杆按3.1小径包络显示，非真实螺纹。梁底壁名义啮合4。',
        '这8颗螺钉与横梁一起沿Y移动；未以碰撞豁免代替通孔。导轨块螺钉孔另在每根梁中心Y±10，不与梁螺钉同轴。',
        '底板、电机座、惰轮座和导轨基准条补明确紧固与头部空间。尚未声称全机所有紧固、工具通道和装配公差已签核。']),
        ('S02','坐标、存取路径与放行边界',[
        '底板660×680×8，上表面Z6。两条Y轨X±205；双梁500×40×60×4，沿Y中心±55。XY板180×156×12，Z124..136。',
        'XY回缩中心(90,-140)，X工作-90..90，Y工作-140..3。货位盒中心(90,158)、层面380；IO(-90,158)、层面293。',
        '叉面进入为层面-8，抬升为层面+4；Z工作285..384。双钢叉18×8×165，中心距56；承托轨内缘±41、叉外缘±37。',
        '先在Y=-140回缩通道横移/大范围升降，再对准库位沿Y进入；插叉状态禁止横向跨库位。固件联锁未实现。',
        'IO门开启90，带盒名义上余量仅6；外门/内门互锁、位置开关和实际变形/容差均需验证。',
        '244个合法姿态为离散采样几何检查，不是连续扫掠或实物动态验收；维护销在运动检查中移除，默认静态装配显示插入。',
        '1kg是净货物设计目标。运动质量含塔、叉、电机、横梁等；扭矩初筛不能代替实际ZDT扭矩-转速、温升及轴承径向额定值。',
        'TR8x2低导程、双螺母、手动维护销均不等于独立自动防坠。自动防下滑、门禁、急停、接地、限位与电气保护尚未实现。',
        '制造放行、硬件验收和带载运行标志保持false。需完整工程签核、防护和控制完成后，再进行空行程、空盒及分级加载试验。'])]
    for code,title,lines in sections:
        border(c,code,title);y=util.paragraphs(c,18,260,lines,width=380,size=10,step=6)
        if y<32:raise RuntimeError('overflow '+code)
        codes.append(code);c.showPage()
    for row in manifest['parts']:
        if row['process'] not in ('print','machined','cut_panel'):continue
        p=m.parts[row['name']];b=p.shape.BoundingBox();code=row['code']
        limit=min(1,108/max(b.xlen,b.ylen,1),78/max(b.zlen,b.ylen,1));scale=next(s for s in (1,.5,1/3,.25,.2,1/6,.1,.05) if s<=limit+1e-8)
        border(c,code,code+' '+p.name,'1:'+util.fmt(1/scale));cache={}
        for kind,x,y,label in [('top',23,172,'俯视 X/Y'),('front',23,61,'主视 X/Z'),('right',155,61,'右视 Y/Z')]:util.view(c,p.shape,kind,x,y,scale,label,cache)
        y=util.paragraphs(c,280,260,[f"数量{row['quantity']}；材料{p.material}；工艺{p.process}。",'局部包围盒起点：',str([round(n,3) for n in row['bounds_mm'][:3]]),'局部原点/方向与分件STEP一致；尺寸非制造公差。',p.note or '位置见总装和manifest。','仅process=print可打印，金属件禁止打印替代。',f'构造孔轴表{len(p.holes)}项；槽和手工切除以STEP为准。','孔轴表非完整工艺/螺纹定义，采购与紧固仍需审核。'],width=124,size=8,step=4)
        if y<32:raise RuntimeError('part overflow '+code)
        codes.append(code);c.showPage()
        for offset in range(0,len(p.holes),38):
            hcode=f'{code}-H{offset//38+1}';border(c,hcode,code+' 局部构造孔轴表（非螺纹定义）');util.text(c,18,259,'序号 | 局部起点X,Y,Z mm | 轴向 | 直径 | 包络长度',10);y=250
            for j,(o,axis,d,length) in enumerate(p.holes[offset:offset+38],offset+1):util.text(c,18,y,f'{j:03} | '+', '.join(util.fmt(n) for n in o)+' | '+str(axis)+f' | Ø{util.fmt(d)} | {util.fmt(length)}',9);y-=5.3
            codes.append(hcode);c.showPage()
        print('C04 DRAWN',code,p.name,flush=True)
    c.save();(OUT/'drawings/manifest.json').write_text(json.dumps({'fingerprint':FINGERPRINT,'generator_sha256':sha(Path(__file__)),'file':target.name,'sha256':sha(target),'page_count':len(codes),'pages':codes,'vectors_from_actual_BRep_HLR':True,'manufacturing_release_allowed':False,'loaded_operation_allowed':False},ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preview-only',action='store_true');ap.add_argument('--drawings-only',action='store_true');args=ap.parse_args()
    m,manifest=load();lists(manifest)
    if not args.drawings_only:previews(m)
    if not args.preview_only:drawings(m,manifest)


if __name__=='__main__':main()
