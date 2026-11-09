"""Dimensioned, vector A3 drawings from the exact CAD and actual hardware list."""
import hashlib
import json
import math
import os
from pathlib import Path

import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepLib import BRepLib

from manual_3axis import OUT, FINGERPRINT, build, kit

W, H = 420*mm, 297*mm
FONT_PATH = Path(os.environ.get('MANUAL_CJK_TTF', '/mnt/c/Windows/Fonts/simhei.ttf'))
FONT = 'ManualCJK'
LATIN = 'ManualLatin'


def font():
    if not FONT_PATH.exists():
        raise FileNotFoundError('Chinese font required: set FONT_PATH to an installed embeddable CJK TTF')
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_PATH)))
    pdfmetrics.registerFont(TTFont(LATIN, '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))


def runs(s):
    current, active = '', None
    for ch in s:
        selected = FONT if ord(ch) >= 0x2e80 else LATIN
        if active is not None and selected != active:
            yield active, current
            current = ''
        current += ch
        active = selected
    if current:
        yield active, current


def text_width(s, size):
    return sum(pdfmetrics.stringWidth(t, f, size) for f, t in runs(s))


def text(c, x, y, s, size=8):
    xx = x*mm
    for f, t in runs(s):
        c.setFont(f, size)
        c.drawString(xx, y*mm, t)
        xx += pdfmetrics.stringWidth(t, f, size)


def wrap(s, width, size=8):
    lines, line = [], ''
    for char in s:
        if text_width(line+char, size) > width*mm:
            lines.append(line)
            line = char
        else:
            line += char
    return lines+[line]


def paragraphs(c, x, y, lines, width=124, size=8, step=4):
    for s in lines:
        for line in wrap(s, width, size):
            text(c, x, y, line, size)
            y -= step
    return y


def border(c, code, title, scale='按各视图标注'):
    c.setStrokeColorRGB(.1, .15, .2)
    c.setLineWidth(.45)
    c.rect(8*mm, 8*mm, 404*mm, 281*mm)
    c.line(8*mm, 25*mm, 412*mm, 25*mm)
    text(c, 12, 281, title, 15)
    text(c, 12, 273, '手动三轴单库位验证样机  /  无电机  /  仅空盒配合验证', 9)
    text(c, 12, 18, f'图号 {code}  |  单位 mm  |  比例 {scale}  |  A3 横向  |  版本 M01', 8)
    text(c, 12, 12, '未注尺寸以同编号STEP为准；打印STL已摆正。不可据本样机证明正式设备承重或防坠。', 7)
    text(c, 288, 12, FINGERPRINT[:24], 7)


def arrow(c, x, y, dx, dy):
    length = math.hypot(dx, dy)
    dx, dy = dx/length, dy/length
    c.line(x*mm, y*mm, (x+dx*2-dy*.65)*mm, (y+dy*2+dx*.65)*mm)
    c.line(x*mm, y*mm, (x+dx*2+dy*.65)*mm, (y+dy*2-dx*.65)*mm)


def fmt(n):
    return f'{n:.3f}'.rstrip('0').rstrip('.')


def dim_h(c, x1, x2, y, edge, label):
    c.setStrokeColorRGB(.15, .25, .35)
    c.setLineWidth(.35)
    for x in (x1, x2):
        c.line(x*mm, edge*mm, x*mm, (y-1)*mm)
    c.line(x1*mm, y*mm, x2*mm, y*mm)
    arrow(c, x1, y, 1, 0)
    arrow(c, x2, y, -1, 0)
    text(c, (x1+x2)/2-6, y+1.4, label, 7)


def dim_v(c, x, y1, y2, edge, label):
    for y in (y1, y2):
        c.line(edge*mm, y*mm, (x+1)*mm, y*mm)
    c.line(x*mm, y1*mm, x*mm, y2*mm)
    arrow(c, x, y1, 0, 1)
    arrow(c, x, y2, 0, -1)
    c.saveState()
    c.translate((x+2)*mm, ((y1+y2)/2)*mm)
    c.rotate(90)
    c.setFont(FONT, 7)
    c.drawString(-5*mm, 0, label)
    c.restoreState()


VIEWS = {'top': ((0, 0, 1), (1, 0, 0), (0, 1)),
         'front': ((0, -1, 0), (1, 0, 0), (0, 2)),
         'right': ((1, 0, 0), (0, 1, 0), (1, 2))}


def projected(shape, kind):
    normal, horizontal, axes = VIEWS[kind]
    algo = HLRBRep_Algo()
    algo.Add(shape.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*normal), gp_Dir(*horizontal))))
    algo.Update()
    algo.Hide()
    result = HLRBRep_HLRToShape(algo)
    sets = []
    for hidden, names in [(False, ('VCompound', 'Rg1LineVCompound', 'OutLineVCompound')),
                          (True, ('HCompound', 'OutLineHCompound'))]:
        edges = []
        for name in names:
            raw = getattr(result, name)()
            if raw.IsNull():
                continue
            BRepLib.BuildCurves3d_s(raw, 1e-7)
            for edge in cq.Shape(raw).Edges():
                n = 2 if edge.geomType() == 'LINE' else 48
                points, _ = edge.sample(n)
                edges.append([(p.x, p.y) for p in points])
        sets.append((hidden, edges))
    return sets


def view(c, shape, kind, x, y, scale, label, cache):
    bb = kit.bbox(shape)
    a, b = VIEWS[kind][2]
    lo = (bb[a], bb[b])
    w, h = bb[a+3]-lo[0], bb[b+3]-lo[1]
    key = (id(shape), kind)
    if key not in cache:
        cache[key] = projected(shape, kind)
    for hidden, edges in reversed(cache[key]):
        c.setStrokeColorRGB(.65, .68, .7) if hidden else c.setStrokeColorRGB(.08, .12, .16)
        c.setDash(1.5, 1.5) if hidden else c.setDash()
        c.setLineWidth(.25 if hidden else .45)
        for points in edges:
            p = c.beginPath()
            p.moveTo((x+(points[0][0]-lo[0])*scale)*mm, (y+(points[0][1]-lo[1])*scale)*mm)
            for u, v in points[1:]:
                p.lineTo((x+(u-lo[0])*scale)*mm, (y+(v-lo[1])*scale)*mm)
            c.drawPath(p)
    c.setDash()
    text(c, x, y+h*scale+5, label, 9)
    dim_h(c, x, x+w*scale, y-7, y, fmt(w))
    dim_v(c, x+w*scale+7, y, y+h*scale, x+w*scale, fmt(h))


def preview(m, name, pose=None):
    pose = pose or {}
    fig = plt.figure(figsize=(13, 10), dpi=140)
    ax = fig.add_subplot(111, projection='3d', proj_type='ortho')
    points = []
    for i in m.items:
        if not pose.get('lock', True) and i.group == 'lock':
            continue
        s = i.located(**pose)
        vs, fs = s.tessellate(.45, .18)
        vertices = np.array([v.toTuple() for v in vs])
        points.append(vertices)
        colour = {'fixed': (.68, .72, .74), 'x': (.2, .5, .68), 'z': (.15, .59, .65),
                  'y': (.94, .59, .21), 'pin': (.94, .59, .21), 'bin': (.65, .28, .23), 'lock': (.98, .74, .1)}.get(i.group, (.25, .29, .33))
        if i.part.process == 'buy':
            colour = (.27, .3, .34)
        poly = Poly3DCollection(vertices[np.asarray(fs)], facecolors=colour, edgecolors=(0, 0, 0, 0),
                               shade=True, lightsource=LightSource(azdeg=310, altdeg=45))
        ax.add_collection3d(poly)
    p = np.concatenate(points)
    lo, hi = p.min(0), p.max(0)
    ax.set_xlim(lo[0]-10, hi[0]+10)
    ax.set_ylim(lo[1]-10, hi[1]+10)
    ax.set_zlim(lo[2]-10, hi[2]+10)
    ax.set_box_aspect(hi-lo)
    ax.view_init(24, -48)
    ax.set_title('MANUAL XYZ / one full-size EMPTY bin / NO motors', fontsize=13)
    ax.set_xlabel('X mm')
    ax.set_ylabel('Y mm')
    ax.set_zlabel('Z mm')
    ax.grid(False)
    ax.set_facecolor('#f7f8f8')
    fig.patch.set_facecolor('#f7f8f8')
    target = OUT/'previews'/name
    fig.savefig(target, bbox_inches='tight')
    plt.close(fig)
    return target


def main():
    font()
    m = build()
    (OUT/'drawings').mkdir(exist_ok=True, parents=True)
    (OUT/'previews').mkdir(exist_ok=True, parents=True)
    image = preview(m, 'assembly.png')
    preview(m, 'bin_in_cell.png', dict(q=0, lift=14, stored=True))
    target = OUT/'drawings/手动三轴验证装置_工程图_M01.pdf'
    c = canvas.Canvas(str(target), pagesize=(W, H))
    c.setTitle('手动三轴验证装置 M01 工程图 — 仅空盒配合验证')
    c.setAuthor('立库项目')
    cache = {}
    page_codes = []

    border(c, 'A01', '手动三轴最小验证装置 — 总装与适用范围', '示意图不按比例')
    c.drawImage(str(image), 10*mm, 53*mm, 262*mm, 201*mm, preserveAspectRatio=True, anchor='c', mask='auto')
    paragraphs(c, 280, 263, [
        '验证目标', '三轴手动移动、真实齿形与两段齿条拼接、空箱存取和销孔配合。',
        '不包含电机、电池、舵机、摄像头或正式金属导轨。',
        '尺寸与行程', '底架245x540；名义层面Z=250。X行程±50，Z行程±40，Y取放行程143。',
        '扫掠外廓需至少约260宽、540深、386高，另留手部操作空间。',
        '全部打印件最大轴向尺寸<=256；按实际打印机余量检查切片。',
        '强制边界', '只用空盒，不放货物，不加砝码。未夹紧台面不得升Z。',
        'Z锁销是手动定位销，不是自动防坠。拔销前必须手托升降台。',
        '不得把打印滑动导向的验证结果用于认定正式金属机器承重合格。',
        '颜色：灰为固定架，蓝为X随动，青为Z随动，橙为Y取放，红为空盒。'], size=9, step=4.8)
    page_codes.append('A01'); c.showPage()

    border(c, 'A02', '总装正投影、外廓与基准', '各视图 1:6')
    compound = cq.Compound.makeCompound([i.located() for i in m.items])
    for kind, x, y, title in [('top', 25, 170, '俯视 X/Y'), ('front', 25, 58, '主视 X/Z'), ('right', 155, 58, '右视 Y/Z')]:
        view(c, compound, kind, x, y, 1/6, title, cache)
    paragraphs(c, 280, 263, ['坐标基准', 'Z=0为底架上平面，底架下表面Z=-6；所有层面尺寸为模型坐标。',
        'X=0为唯一库位中心；Y=0为库位托板前沿。', '关键装配坐标',
        'X导向底座中心：(0,-310,0)。', 'Z立柱基准：(0,-310,180)，底端Z60。',
        'Y底座中心：(0,-135,165)。', '移动托盘中心：(0,-78,246)，承托面Z250。',
        '固定库位托板中心：(0,65,246)，承托面Z250。',
        '料盒中心由Y=-78移动至Y=65；不是缩小比例的料盒。',
        '库位腿中心X=±76，Y=10/140；腿底Z6、框架底Z240。',
        '底架纵梁中心X=±110；分段180/140/220，接缝Y=-190/-50。',
        '图示为中性位置；全部运动必须先将Y收回、插销插入或释放到正确状态。'], size=8.5, step=4.5)
    page_codes.append('A02'); c.showPage()

    border(c, 'S01', '装配顺序与手动存取流程', '文字说明')
    paragraphs(c, 16, 260, ['装配顺序',
        '1. 先打印C01轨试块与C02/C03/C04滑块。C03对应正式0.35间隙，必须端部滑入，不得强行从上压入。',
        '2. 所有毛刺和支撑清理干净；槽不得靠硬拧螺钉拉到位。若C03不顺畅，先调整切片补偿，不要整机全部打印后再磨。',
        '3. 两侧纵梁按P21/P22/P23由后到前排布，用P24拼接；装P25横梁。M3螺母预先装入底面窝。',
        '4. 装X底座、两段P01齿条。将X滑台从端部滑入，再装P07端挡。',
        '5. 装P11、Z底座和Z滑台；先插Z锁销，再装Y连接角座、Y底座与滑台。',
        '6. 每轴按S02装光滑金属隔套、垫片、齿轮与手轮。两个M3螺母的平面朝中心套，避免顶到套筒。',
        '7. 装外置承托支柱P13、沉头托盘P14、手动取放头P17和M4x80牵引销；检查销能自由抬高14mm。',
        '8. 装四根库位腿P19、框架P20和P15。用实际空盒检查两侧导边；所有沉头螺钉头不得突出。',
        '9. 用四个台夹固定底架；手托升降台，确认Z五个锁孔位置均能插入M4钢销。再进行空盒操作。'], width=190, size=9, step=5.2)
    paragraphs(c, 220, 260, ['手动取放顺序',
        '1. 空盒在移动托盘，Y完全收回；牵引销穿入料盒牵引耳。',
        '2. 如需移动X/Z，先确认Y已收回。Z拔锁销前先手托升降台，再慢转手轮。',
        '3. 将X置0、Z置0，使两侧承托面同为250。插入Z锁销，并加保持螺母防脱；保持螺母不预紧锁耳。',
        '4. 转Y手轮将空盒推入库位，终点Q=143。不要越过端挡，也不要靠撞击纠正错位。',
        '5. 手动把牵引销提起至少14mm，确认销尖高于牵引耳顶面，再保持提销、反转Y手轮收回取放头。',
        '6. 取回时反向操作：提销伸头、对准牵引孔、轻放销、确认插入，再收回空盒。',
        '停机与禁止事项', 'Z始终先插钢锁销再松手，严禁依赖齿轮摩擦停住。',
        '卡滞时停止并检查，不加长手柄、不用电钻带动、不用电机改装。',
        '空盒过程仍需双手操作，避开齿缝、导槽和托盘下面的夹点。'], width=184, size=9, step=5.2)
    page_codes.append('S01'); c.showPage()

    border(c, 'S02', '导向配合剖面与手轮轴向堆叠', '剖面4:1；轴系3:1')
    fit = cq.Compound.makeCompound([m.parts['C01'].shape, m.parts['C03'].shape])
    view(c, fit, 'right', 30, 165, 4, '打印导向截面：正式参数c=0.35', cache)
    dim_h(c, 54, 126, 243, 229, '18')
    dim_h(c, 70, 110, 181, 189, '10')
    dim_v(c, 23, 165, 189, 30, '6')
    paragraphs(c, 175, 258, ['导向截面坐标，水平为Y、竖向为Z',
        '轨：底座顶Z6；下口宽10；斜面到Z14时宽18；顶面Z16。',
        '槽：下口10.7；斜面起Z5.65；上口18.7；顶Z16.35；滑块底Z6.35。',
        '轨的斜面偏移不等于简单把整条轨缩放；按原CAD截面检查。',
        'C02/C03/C04分别为c=0.20/0.35/0.50试块。只用来评估打印配合。',
        '正式滑台已采用c=0.35；若切片补偿无法使其自由滑动，先停止整机打印并反馈试块结果。'], width=220, size=9, step=5)
    labels = [('金属隔套', -26, 14, 126, (.35, .4, .45)), ('转动件', -24, 12, 112, (.2, .6, .7)),
              ('1.8垫片', -25.8, -24, 98, (.95, .65, .2)), ('1.8垫片', 12, 13.8, 98, (.95, .65, .2)),
              ('固定轴座', 14, 20, 84, (.55, .65, .7)), ('双螺母', 21, 27.4, 70, (.35, .4, .45))]
    for label, a, b, yy, colour in labels:
        x1, x2 = 65+(a+30)*3, 65+(b+30)*3
        c.setFillColorRGB(*colour)
        c.rect(x1*mm, yy*mm, (x2-x1)*mm, 6*mm, fill=1)
        c.setFillColorRGB(0, 0, 0)
        text(c, 16, yy+1, label, 8)
        text(c, x2+3, yy+1, f'Y={fmt(a)}..{fmt(b)}', 8)
    paragraphs(c, 285, 135, ['轴系坐标为单轴局部Y。', '金属隔套：外Ø6、内Ø4.2，L40±0.1。',
        '手轮连接套中心孔Ø6.4，绕光滑隔套转动，不绕螺纹转动。',
        '转动件轴向36，加两片1.8垫片，总39.6；隔套40，名义总游隙0.4。',
        'M4x60穿隔套与固定座；两颗普通M4螺母对锁。只夹紧隔套和固定座，不夹死手轮。',
        '若实际M4垫圈厚度不为1或螺母非3.2，先实测轴向堆叠再装。'], width=118, size=8, step=4.2)
    page_codes.append('S02'); c.showPage()

    border(c, 'B01', '五金与打印清单', '清单')
    y = 261
    for row in m.hardware:
        y = paragraphs(c, 15, y, [f"{row['quantity']} × {row['specification']}", '用途：'+row['purpose']], width=249, size=8, step=3.7)-2
    paragraphs(c, 280, 261, ['打印文件', 'P01..P26为正式打印件；C01..C04为先行试块；H开头只有采购参考STEP，不得打印代替五金。',
        '各件数量以打印清单CSV为准；轴向垫片P04共6件。',
        '每页P/C编号与零件STEP、STL一一对应。',
        '材料与装配', '齿条/齿轮建议同一批PETG；细节与导向先做试块。避免靠提高填充率掩盖间隙错误。',
        '原CAD实体不含切片补偿，孔位需要去毛刺；不得强拧金属螺钉让塑料胀裂。',
        '建议购买M3螺母/螺钉各规格另加10%备用；实际长度不得改为碰到台面的长螺钉。',
        '原始料盒110x120x60未缩小；这是几何验证，不是承载缩比试验。'], size=8.5, step=4.5)
    page_codes.append('B01'); c.showPage()

    for p in m.parts.values():
        if p.process != 'print':
            continue
        b = p.shape.BoundingBox()
        scale = min(1, 110/max(b.xlen, b.ylen, 1), 82/max(b.zlen, b.ylen, 1))
        scale = next(s for s in (1, .5, 1/3, .25, .2, 1/6, .1) if s <= scale+1e-8)
        ratio = '1:1' if scale == 1 else '1:'+fmt(1/scale)
        border(c, p.code, p.code+'  '+p.name, ratio)
        view(c, p.shape, 'top', 23, 172, scale, '俯视 X/Y', cache)
        view(c, p.shape, 'front', 23, 61, scale, '主视 X/Z', cache)
        view(c, p.shape, 'right', 155, 61, scale, '右视 Y/Z', cache)
        quantity = sum(i.part.code == p.code for i in m.items) or 1
        y = paragraphs(c, 280, 263, [f'数量：{quantity}；单位mm；编号即文件名。', '工艺：FDM打印，非承载验收件。',
            '局部坐标原点/投影轴以本页标注和STEP一致。', f'包围盒起点：({fmt(b.xmin)},{fmt(b.ymin)},{fmt(b.zmin)})。',
            'STL已转换为推荐朝向并平移到正坐标；不得据STL原点装配。', '尺寸与孔位：', *p.features,
            '打印/装配说明：', *p.notes], width=125, size=7.6, step=3.7)
        if y < 30:
            raise RuntimeError('Drawing text overflow '+p.code)
        text(c, 18, 38, '投影采用明确X/Y/Z轴；灰色虚线为隐藏轮廓。剖面和配合见S02。', 7)
        page_codes.append(p.code); c.showPage()
    c.save()
    report = {'fingerprint': FINGERPRINT, 'drawing_generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'file': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'pages': page_codes, 'page_count': len(page_codes), 'paper': 'A3 landscape, mm',
              'vectors_from_actual_BRep_HLR': True, 'font_embedded': True,
              'no_loaded_operation_release': True}
    (OUT/'drawings/manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('DRAWINGS', len(page_codes), 'pages', target, flush=True)


if __name__ == '__main__':
    main()
