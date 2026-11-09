"""C03 whole-machine design-review drawings, previews and procurement boundaries."""
import csv
import argparse
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

from corexy_mvp import (ROOT,OUT,FINGERPRINT,Model,Item,v2,HOME_X,HOME_Y,CELL_X,CELL_Z,
    IO_X,IO_Z,BIN_Y,belt_shape,REAR_A,REAR_B,W,R)
sys.path.insert(0,str(ROOT/'cad/manual_mvp'))
import drawings as util


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def border(c,code,title,scale='说明/示意不按比例'):
    c.setStrokeColorRGB(.1,.15,.2);c.setLineWidth(.45);c.rect(8*mm,8*mm,404*mm,281*mm);c.line(8*mm,25*mm,412*mm,25*mm)
    util.text(c,12,282,title,13)
    util.text(c,12,274,'C03 整机CoreXY重构 / 底部两台固定ZDT + 金属丝杆升降 + 固定叉 / 目标1kg，未验收带载',9)
    util.text(c,12,18,f'{code} | mm | A3横向 | 比例 {scale} | 架构/机械设计评审稿，非制造和运行放行',8)
    util.text(c,12,12,'实际皮带夹齿/张紧、惰轮轴栈、全部紧固、公差、安全链/防坠和固件仍需设计/验收。',7)
    util.text(c,302,12,FINGERPRINT[:20],7)


def preview(m,name,args=None,hide_frame=False):
    args=args or {};fig=plt.figure(figsize=(13,10),dpi=140);ax=fig.add_subplot(111,projection='3d',proj_type='ortho');points=[]
    for i in m.items:
        if i.part.material=='guard' or i.name=='maintenance_pin' and args:continue
        if hide_frame and i.name.startswith('guard_'):continue
        s=i.located(**args);vs,fs=s.tessellate(.6,.23);v=np.array([p.toTuple() for p in vs]);points.append(v)
        col=v2.COLORS.get(i.part.material,(.5,.5,.5))[:3]
        if i.name=='belt_A':col=(.05,.43,.85)
        elif i.name=='belt_B':col=(.98,.46,.08)
        elif i.part.process=='candidate':col=(.95,.56,.12)
        elif i.name=='fork':col=(.25,.31,.36)
        ax.add_collection3d(Poly3DCollection(v[np.asarray(fs)],facecolors=col,edgecolors=(0,0,0,0),shade=True,lightsource=LightSource(310,45)))
    p=np.concatenate(points);lo,hi=p.min(0),p.max(0)
    ax.set_xlim(lo[0]-10,hi[0]+10);ax.set_ylim(lo[1]-10,hi[1]+10);ax.set_zlim(lo[2]-10,hi[2]+10)
    ax.set_box_aspect(hi-lo);ax.view_init(25,-51);ax.grid(False);ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_zlabel('Z mm')
    ax.set_title('C03 / Fixed A+B CoreXY + travelling TR8x2 Z + rigid fork\nGuard panels omitted in preview only / DESIGN REVIEW, NOT LOAD ACCEPTED')
    path=OUT/'previews'/name;fig.savefig(path,bbox_inches='tight');plt.close(fig);return path


def belt_preview():
    fig,axes=plt.subplots(1,2,figsize=(13,7),dpi=140)
    for axis,ax,col,rear in [('A',axes[0],'#0875d1',REAR_A),('B',axes[1],'#ed781f',REAR_B)]:
        s=belt_shape(axis);vs,fs=s.tessellate(.3,.15);v=np.array([p.toTuple() for p in vs]);faces=np.asarray(fs)
        ax.add_collection(PolyCollection(v[faces][:,:,:2],facecolors=col,edgecolors='none'))
        ax.scatter([-W if axis=='A' else W],[rear],s=150,marker='s',c='#333c45',label='Fixed motor')
        ax.add_patch(plt.Rectangle((HOME_X-90,HOME_Y-78),180,156,fill=False,color='#3f4952',lw=1))
        ax.axhline(HOME_Y,color='#89939b',ls='--',lw=.6);ax.set_xlim(-320,320);ax.set_ylim(-390,210);ax.set_aspect('equal')
        ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_title(f'OPEN belt {axis}: separate height, TWO carriage anchors');ax.legend(loc='lower left')
    fig.suptitle('C03 exact CAD belt footprints / A = dx + dy; B = -dx + dy\nNot two independent X/Y drives; clamp teeth/tension and real wiring still unverified')
    path=OUT/'previews/C03_AB_belt_paths.png';fig.savefig(path,bbox_inches='tight');plt.close(fig);return path


def info(c,code,title,lines):
    border(c,code,title);y=util.paragraphs(c,18,260,lines,width=380,size=10,step=6)
    if y<32:raise RuntimeError('overflow '+code)
    c.showPage()


def lists(manifest):
    fields=['code','name','quantity','material','process','note']
    for filename,rows in [('打印清单.csv',[r for r in manifest['parts'] if r['process']=='print']),('采购与金属加工清单.csv',[r for r in manifest['parts'] if r['process']!='print'])]:
        with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


def drawings(m,manifest):
    util.font();(OUT/'drawings').mkdir(parents=True,exist_ok=True);(OUT/'previews').mkdir(parents=True,exist_ok=True)
    image=preview(m,'C03_assembly.png');paths=belt_preview()
    preview(m,'C03_structure.png',hide_frame=True)
    preview(m,'C03_inserted_pickup.png',{'dy':143,'dz':4,'bin_pose':[CELL_X,BIN_Y,CELL_Z+4]})
    preview(m,'C03_IO_pickup.png',{'dx':-180,'dy':143,'dz':IO_Z+4-CELL_Z,'door':1,'bin_pose':[IO_X,BIN_Y,IO_Z+4]})
    target=OUT/'drawings/CoreXY整机重构_C03_工程图.pdf';c=canvas.Canvas(str(target),pagesize=(util.W,util.H));c.setTitle('CoreXY整机重构C03 — 机械架构评审，非带载运行放行');codes=[]
    border(c,'A01','C03整体架构 — 不再在立柱上设置独立Y推拉机构')
    c.drawImage(str(image),10*mm,45*mm,260*mm,215*mm,preserveAspectRatio=True,mask='auto')
    util.paragraphs(c,280,260,[
        '底部A/B两台电机均固定；双层CoreXY带路驱动双梁横梁和承载小车。',
        '第三台ZDT随小车移动，驱动金属TR8x2升降。',
        '升降板上直接装两根固定钢叉；取消Y电机/皮带头、释放舵机、牵引销和外伸驱动臂。',
        '货位和IO改两侧金属承托，中间留叉道；料盒去掉原牵引眼，外形110×120×60保持。',
        '1个货位+独立IO；XY中心距180，进出143，层面293/380，另有进入/微升的上下余量。',
        '底板660×680×8；这是新架构，不宣称比E02总体更小或更轻。',
        '原雕绘仪仅参考平面拓扑；横梁、小车和载荷支承重新设计，不复用轻笔架承载。',
        '当前为架构/机械设计评审，皮带夹齿/张紧、轴栈、紧固细节、公差、安全链和固件仍需完成。'],size=9,step=5)
    codes.append('A01');c.showPage()
    info(c,'A02','全机坐标、金属支承与包络',[ 
        '底板上表面Z6，下表面Z-2；底板660×680；防护外廓以总装STEP回读值为准，不以旧E02底板为准。',
        'Y双轨MGN12 L400，X=±205，中心Y=-100，轨底Z30；每侧两个长块，前后中心距110。',
        '移动横梁是两根500×40×60×4金属箱梁，分别在横梁Y中心±55，Z51..111；端板Z43..51。',
        'X双轨MGN12 L440，轨底Z111，沿两根梁顶部；四个X长块中心X=小车±45。',
        'XY承载板180×156×12，Z124..136；两根3030长350从Z136至486，顶板Z486..498。',
        '平面小车中心默认(90,-140)；X工作-90..90，Y工作-140..3。Z塔全部随小车XY移动。',
        '货位料盒中心(90,158)，IO(-90,158)，料盒下表面名义层面分别380/293。',
        '两根钢叉宽18、厚8、中心距56，自根部Y+48延伸到Y+213；料盒中心=小车Y+155，叉尖避开后挡块2mm。',
        '两侧货位承托轨中心X=料盒中心±50，内缘±41；叉外缘±37，名义横向余量4mm，待实物验证。',
        '货叉、升降架和整个横梁必须按运动自重、重心及悬臂力矩校核；不能按1kg净货物替代全部运动质量。'])
    codes.append('A02')
    border(c,'B01','CoreXY双层独立开口皮带 — 实际CAD带路俯视投影')
    c.drawImage(str(paths),12*mm,70*mm,392*mm,190*mm,preserveAspectRatio=True,mask='auto')
    util.paragraphs(c,18,59,['A带底Z91.5、B带底Z103.5，带宽6，层间距12；每条带的两端分别固定在承载小车上。',
        'A=ΔX+ΔY；B=-ΔX+ΔY；20T/GT2每转40mm。实际接线正负、同步轨迹与驱动接口未验证。',
        '带路在每个XY姿态重新生成；不是用一条不变的闭环带或固定示意线冒充CoreXY运动。'],width=380,size=9,step=5)
    codes.append('B01');c.showPage()
    info(c,'B02','A/B驱动、惰轮和皮带端部边界',[ 
        '两台电机都轴向上、安装面Z78，在支架顶板下表面；轴端约Z102。',
        'A驱动中心(-260,-330)，带轮底Z90；B中心(260,-285)，带轮底Z102；都需要下置夹紧轮毂。',
        '上层B轮毂仅分配约6mm轴向啮合，必须用实际厂家带轮和可靠夹紧复核，不能宣称模型套上轴就能传扭。',
        'A/B驱动Y错开45，避免电机外壳与另一层回程惰轮支承相撞；不能随意把两个驱动中心改到同一横线。',
        '两侧移动转向轮为双层同轴，每侧共用一根D5肩轴；4个MR105轴承，层间内圈隔套，不能上下重复穿两根独立肩轴。',
        '所有带轮为金属采购包络，不包含GT2制造齿形；皮带使用开口带，切断长度需另加真实夹持和张紧余量。',
        '当前金属端夹只表示带端连接位置和几何空间，尚未完成实际齿形压板、螺纹调节器、张紧锁紧及拉脱强度。',
        '固定惰轮支脚、肩轴/内圈垫片的完整厂家叠层和锁紧结构仍需深化，不能按包络直接下料装机。',
        '数学带长不变和映射正确不代表皮带刚度、动态同步、轴承径向承载及电机运行扭矩已验收。'])
    codes.append('B02')
    info(c,'S01','货叉存取循环与IO',[ 
        '取货：空叉上表面到货位层面-8 → 底部Y从-140进到3 → Z微升到层面+4 → XY退出。',
        '存货：带盒、叉面=层面+4 → Y进入 → Z降到层面-8，料盒接触外侧轨后留在层面 → 空叉退出。',
        '下降时料盒不是一直跟着叉走；验证中使用max(叉面,货位承托面)模拟接触后落座，不能把盒子穿进承托轨。',
        '8mm进入间隙和4mm微升是当前设计几何值，不是实物已验证的安全余量；打印误差、变形和定位需实测后确定。',
        '禁止插叉后横向跨库位：先回到Y=-140的退出通道再横移/大范围升降；Y进入只能在已对准的货位或IO上进行，固件联锁尚未实现。',
        'Z实际采样范围285..384；IO层面提高到293，使叉进入位避开下轴承和止挡。名义层差87mm；不得沿用旧限位坐标。',
        'IO内部门须先打开并确认外门闭锁；验证同时包含IO开门行程。原门执行器/互锁仍未实现。',
        'IO下挡板移低以留叉道，门板下延14mm关闭叉道；开启90mm后门下缘363，离满载盒顶357仅6mm，需实物容差/变形验证。',
        '叉与外侧轨不重叠，货物竖向重量通过叉/根板传入Z板；薄皮带或夹爪不承担货物竖向支承。',
        '新的叉槽货位和无牵引眼料盒不能与E02整板托盘/推拉销方案直接互换；不得混用不同版本分件。'])
    codes.append('S01')
    sizing=json.loads((OUT/'engineering_checks.json').read_text());mass=sizing['moving_masses_kg_including_payload_and_allowance']
    info(c,'S02','承力估算、架构代价与运行边界',[ 
        f"按当前密度、电机0.50kg假定、1kg净货物及余量：X运动质量{mass['X']:.2f}kg，Y{mass['Y']:.2f}kg，Z{mass['Z']:.2f}kg。不是称重结果。",
        f"A/B按同时轴力的雅可比变换估算，各电机所需扭矩含SF2约{sizing['AB_motor_screen']['required_each_motor_torque_SF2_Nm']:.3f}N·m；候选8mm/s每轴，合成电机转速上限24rpm。",
        f"Z候选2mm/s=60rpm，含SF2扭矩约{sizing['Z_motor_screen']['required_torque_SF2_Nm']:.3f}N·m；仍没有实际ZDT运行曲线。",
        '好处：两台平面电机都不动，上部没有独立推拉驱动、牵引销和释放舵机；取放接口更直接。',
        '代价：Y也要搬动完整升降架，双梁/底部跨距和占地增加，A/B控制耦合；不宣称一定比E02重量/成本最优。',
        '货叉的理想挠度/根应力仅初筛；焊缝、M4连接、导轨抗倾覆、双梁平面误差和紧固预载都需详细工程验收。',
        'Z保留金属丝杆、双金属螺母、顶端推力栈；低导程丝杆、第二螺母和手动维护销都不是完整自动防坠。',
        '独立自动防下滑、实际限位/门禁/急停/断能/接地保护、柔性线束和控制固件仍未实现。',
        '完成上述设计与防护后才可组织空行程/空盒及分级加载试验；当前模型不能直接加工装好后上电带1kg。'])
    codes.append('S02')
    selected=[i.located() for i in m.items if i.part.material not in ('guard','rubber') and i.part.process not in ('candidate','purchased') and not i.name.startswith('guard_')]
    shape=cq.Compound.makeCompound(selected);border(c,'A03','主结构正投影（省略采购件、外罩和小五金）','1:7.5');cache={}
    for kind,x,y,label in [('top',23,161,'俯视 X/Y'),('front',23,50,'主视 X/Z'),('right',155,50,'右视 Y/Z')]:util.view(c,shape,kind,x,y,1/7.5,label,cache)
    util.paragraphs(c,280,260,['本页尺寸是所显示结构包围盒，不是完整防护外廓。','完整整机见STEP；运动平台宽度和线束空间不能只按笔尖行程估算。','底座固定电机在后两角，双梁与塔小车平面运动。'],size=9,step=5)
    codes.append('A03');c.showPage()
    for row in manifest['parts']:
        if row['process'] not in ('print','machined','cut_panel'):continue
        p=m.parts[row['name']];b=p.shape.BoundingBox();code=row['code']
        scale=min(1,108/max(b.xlen,b.ylen,1),78/max(b.zlen,b.ylen,1));scale=next(s for s in (1,.5,1/3,.25,.2,1/6,.1,.05) if s<=scale+1e-8)
        border(c,code,code+' '+p.name,'1:'+util.fmt(1/scale));cache={}
        for kind,x,y,label in [('top',23,172,'俯视 X/Y'),('front',23,61,'主视 X/Z'),('right',155,61,'右视 Y/Z')]:util.view(c,p.shape,kind,x,y,scale,label,cache)
        y=util.paragraphs(c,280,260,[f"数量{row['quantity']}；材料{p.material}；工艺{p.process}。",'包围盒局部起点：',str([round(n,3) for n in row['bounds_mm'][:3]]),
            '局部方向/原点与分件STEP一致；尺寸不是制造公差。',p.note or '位置见总装STEP和manifest实例表。',
            '打印仅process=print分件；金属件禁止打印替代。',f'构造孔轴表{len(p.holes)}项，见后续页；槽/沉孔/手工切除以STEP为准。',
            '孔轴表不是完整工艺或螺纹定义；实际配合/紧固与供应商图仍需审核。'],width=124,size=8,step=4)
        if y<32:raise RuntimeError('part text overflow '+code)
        codes.append(code);c.showPage()
        for offset in range(0,len(p.holes),38):
            hcode=f'{code}-H{offset//38+1}';border(c,hcode,code+' 局部构造孔轴表（非螺纹定义）');util.text(c,18,259,'序号 | 起点X,Y,Z（局部mm） | 轴向 | 直径 | 包络长度',10);y=250
            for j,(o,axis,d,length) in enumerate(p.holes[offset:offset+38],offset+1):util.text(c,18,y,f'{j:03} | '+', '.join(util.fmt(n) for n in o)+' | '+str(axis)+f' | Ø{util.fmt(d)} | {util.fmt(length)}',9);y-=5.3
            codes.append(hcode);c.showPage()
        print('DRAWN',code,p.name,flush=True)
    c.save();(OUT/'drawings/manifest.json').write_text(json.dumps({'fingerprint':FINGERPRINT,'generator_sha256':sha(Path(__file__)),'file':target.name,'sha256':sha(target),'page_count':len(codes),'pages':codes,'vectors_from_actual_BRep_HLR':True,'loaded_operation_allowed':False,'machining_release_allowed':False},ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview-only',action='store_true');args=parser.parse_args()
    manifest=json.loads((OUT/'manifest.json').read_text())
    if manifest['fingerprint']!=FINGERPRINT:raise RuntimeError('StaleC03 export')
    # Draw from precisely the verified exports, avoiding another costly rebuild
    # of the entire inherited tower and open-belt booleans before showing a view.
    m=Model()
    for r in manifest['parts']:
        shape=cq.importers.importStep(str(OUT/'parts'/(r['code']+'.step'))).val()
        m.parts[r['name']]=v2.Part(r['name'],shape,r['material'],r['process'],r['holes'],r['note'])
    for r in manifest['instances']:m.add(r['name'],m.parts[r['part']],tuple(r['origin_mm']),r['group'])
    if args.preview_only:
        (OUT/'previews').mkdir(parents=True,exist_ok=True)
        lists(manifest);preview(m,'C03_structure.png',hide_frame=True);belt_preview()
        print('C03 MODEL AND STRUCTURE PREVIEWS READY',flush=True)
        return
    lists(manifest);drawings(m,manifest);print('C03 DRAWINGS COMPLETE',flush=True)


if __name__=='__main__':main()
