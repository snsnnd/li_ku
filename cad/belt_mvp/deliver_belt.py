"""E02 true-BRep review drawings, lists and previews, without changing E01."""
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
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from belt_mvp import ROOT, OUT, BASE, FINGERPRINT, build_model, v2
sys.path.insert(0, str(ROOT/'cad/manual_mvp'))
import drawings as util


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def border(c, code, title, scale='说明/示意不按比例'):
    c.setStrokeColorRGB(.1, .15, .2); c.setLineWidth(.45)
    c.rect(8*mm, 8*mm, 404*mm, 281*mm); c.line(8*mm, 25*mm, 412*mm, 25*mm)
    util.text(c, 12, 282, title, 13)
    util.text(c, 12, 274, 'E02 同步带结构优化  /  三台完整ZDT  /  XY GT2 + Z金属TR8x2  /  1kg货载仅为设计目标', 9)
    util.text(c, 12, 18, f'{code} | mm | A3横向 | 比例 {scale} | 设计评审稿，非加工/带载运行放行', 8)
    util.text(c, 12, 12, '采购包络不是制造图；带轮/夹齿/张紧/轴承、全部紧固和独立防坠须实物审核。', 7)
    util.text(c, 302, 12, FINGERPRINT[:20], 7)


def preview(m, filename, pose=None, closeup=False):
    pose = pose or {}
    fig = plt.figure(figsize=(13, 10), dpi=140)
    ax = fig.add_subplot(111, projection='3d', proj_type='ortho'); points = []
    for i in m.items:
        if i.part.material == 'guard' or i.name == 'maintenance_pin' and pose: continue
        if closeup and (i.group in ('fixed', 'io_shutter') or i.name.startswith('guard_')): continue
        s = i.located(**pose); vs, fs = s.tessellate(.5, .2)
        vertices = np.array([v.toTuple() for v in vs]); points.append(vertices)
        colour = v2.COLORS.get(i.part.material, (.6, .6, .6))[:3]
        if 'belt' in i.name: colour = (.12, .16, .20)
        if i.part.process == 'candidate': colour = (.95, .56, .12)
        ax.add_collection3d(Poly3DCollection(vertices[np.asarray(fs)], facecolors=colour, edgecolors=(0, 0, 0, 0),
            shade=True, lightsource=LightSource(310, 45)))
    p = np.concatenate(points); lo, hi = p.min(0), p.max(0)
    ax.set_xlim(lo[0]-10, hi[0]+10); ax.set_ylim(lo[1]-10, hi[1]+10); ax.set_zlim(lo[2]-10, hi[2]+10)
    ax.set_box_aspect(hi-lo); ax.view_init(25, -51); ax.grid(False)
    ax.set_xlabel('X mm'); ax.set_ylabel('Y mm'); ax.set_zlabel('Z mm')
    ax.set_title('E02 / XY GT2 belts + TR8x2 Z / fixed X motor, Y motor rides Z\nGuard panels omitted in preview only / NOT load-accepted')
    path = OUT/'previews'/filename; fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    return path


def info(c, code, title, lines):
    border(c, code, title)
    y = util.paragraphs(c, 18, 260, lines, width=380, size=10, step=6)
    if y < 32: raise RuntimeError('Text overflow '+code)
    c.showPage()


def lists(manifest, sizing):
    fields = ['code', 'name', 'quantity', 'material', 'process', 'note']
    for filename, rows in [('打印清单.csv', [r for r in manifest['parts'] if r['process'] == 'print']),
                           ('采购与金属加工清单.csv', [r for r in manifest['parts'] if r['process'] != 'print'])]:
        with (OUT/filename).open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    lines = ['# E02相对E01的结构优化', '',
        '- XY齿条、齿轮、金属背板、长支承脚及自制轮毂取消，改金属带轮+采购GT2同步带。',
        '- X电机固定底座，不再拖动电机和大后伸安装结构；X移动板由160×160减至160×120。',
        '- Y电机固定在Z平台下方，推拉头不再携带0.5kg假定电机质量和外伸支架。',
        '- Y导轨中心距26→52mm；轨/头底座降低6mm，保留原料盒和锁销基准。',
        '- Y皮带侧置，固定电机不侵入存取通道；轻连接臂只带夹爪，不带电机。夹爪须匹配实带齿形。',
        '- 底板610×650→610×590mm，深度减少60mm（9.2%）；防护罩和独立IO保留。',
        '- Z丝杆、双螺母、金属主承力路径保留，不因轻载取消安全需求。', '',
        '## 相同1kg货载、自重密度及余量假设下的比较', '',
        '|轴|E01运动质量kg|E02运动质量kg|E01所需扭矩SF2 N·m|E02所需扭矩SF2 N·m|',
        '|---|---:|---:|---:|---:|']
    for r in sizing['comparison_to_E01']:
        lines.append(f"|{r['axis']}|{r['E01_mass_kg']:.3f}|{r['E02_mass_kg']:.3f}|{r['E01_torque_SF2_Nm']:.3f}|{r['E02_torque_SF2_Nm']:.3f}|")
    lines += ['', '以上是候选低速工况的估算，不是实测或电机合格判定。1kg是货物净质量，不含料盒和机构；Z仍需要搬动整个平台。', '',
        '## 同步带的新增代价',
        '- 需要实际张紧、对中、防松、齿形夹爪和惰轮轴承；柔性伸长及振动未动态仿真。',
        '- 较低驱动扭矩不等于电机轴负荷更小：预紧会增加径向力，必须核对实际ZDT轴承/轴端能力。',
        '- engineering_checks.json中的15N预紧只是算例，不是张紧操作值。带规格、张力和匹配齿形须向供应商确认。',
        '- 两条同步带暂定闭环GT2-1000-6及GT2-400-6；不能买不到就直接换任意长度/带轮，应先调整中心距并重验行程。',
        '- 当前只做机械设计/几何验证，未完成自动存取固件及安全链。']
    (OUT/'E01_E02优化对比.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def drawings(m, manifest, sizing):
    util.font(); (OUT/'previews').mkdir(parents=True, exist_ok=True); (OUT/'drawings').mkdir(parents=True, exist_ok=True)
    image = preview(m, 'E02_assembly.png')
    preview(m, 'E02_at_IO.png', {'dx': -180, 'dz': -95})
    preview(m, 'E02_transfer.png', {'q': 143})
    preview(m, 'E02_moving_structure.png', closeup=True)
    path = OUT/'drawings/同步带单库位MVP_E02_工程图.pdf'
    c = canvas.Canvas(str(path), pagesize=(util.W, util.H)); c.setTitle('同步带单库位MVP E02 — 结构优化评审图，未放行带载')
    codes = []; border(c, 'A01', 'E02结构优化 — 固定电机、侧置Y皮带和紧凑底板')
    c.drawImage(str(image), 10*mm, 45*mm, 260*mm, 215*mm, preserveAspectRatio=True, mask='auto')
    util.paragraphs(c, 280, 260, [
        '三台用户ZDT实物参考模型；保留一货位+独立IO+一只原尺寸料盒。',
        'X：固定电机、GT2-1000-6，20T带轮，中心距480；移动板缩短40mm。',
        'Y：电机固定Z平台下方，GT2-400-6；头部只带轻连接臂和夹爪。',
        '双Y导轨间距26→52mm；皮带侧置避开滑块和存取通道。',
        'X/Y每转40mm；Z仍用金属TR8x2，未降低主承力材料要求。',
        'X180、Z95、Y143mm行程保持；底板深度650→590，缩短60。',
        '1kg算轻货载，但不等于只升降1kg：要加料盒和机构自重。',
        '模型内维护销插入，运动前必须卸载、拔销并确认状态。',
        '橙色采购包络不是已选产品；独立防下滑、安全链和固件仍未实现。',
        '所有文件为机械设计评审，不等于加工/带载运行放行。'], size=9, step=5)
    codes.append('A01'); c.showPage()
    info(c, 'A02', '坐标、行程与安装基准', [
        '底板下表面Z0，上表面Z6；货位(90,65,295)，IO(-90,65,200)；托盘Y-78，取放143。',
        'X双轨L400，Y=-285/-215；移动板Z43..51，160×120，中心Y=-250。',
        'X电机固定安装面(-240,-308,82)，轴向下；带轮下端Z60，皮带Z61.5..67.5；惰轮(240,-308)。',
        'X金属U支座两腿厚8，右腿有两条皮带通过槽；不得装配成堵住回程带的实心腿。',
        'Y双轨L200，X=机架中心±26、Y=-125、轨底=层面-46；滑块中心Y=-196..-53。',
        'Y主支板104×209×6，局部Y=-223..-14，Z=层面-52..-46；右侧金属翼板承托电机/惰轮，后翼避让Z板。',
        'Y电机在(机架中心+85,-40,层面-52)，轴向上；惰轮Y=-220；中心距180，皮带层面-43.5..-37.5。',
        'Y头主体74×56，Z=层面-36..-32；轻连接臂仅传递侧置皮带推拉力，升高定位台到层面-26，料盒接口不变。',
        '52mm导轨间距提高支承跨距；侧置皮带避开完整滑块。垫块内沿X±38、位于Y=-217/-31两端，不可搬到臂的运动区。',
        '支板/两侧IO立脚只有约3mm名义横向间隙，实际供应商尺寸和全行程线束必须复查。'])
    codes.append('A02')
    info(c, 'S01', '同步带、夹爪、惰轮与张紧', [
        '采购同步带，不打印带齿：2mm节距，20T金属带轮，带宽6mm，X闭环节线长1000，Y400。',
        '带轮/皮带CAD只用光滑有效包络，不能作为制造GT2齿形的依据；带轮5mm孔需正向夹紧/双螺钉可靠轴向保持。',
        'X皮带夹：金属主体固定X板，2×M3x30；压力齿爪2×M3x12在皮带上方，避开垂直锚固螺钉。',
        'Y金属夹爪进入轻连接臂凹槽；2×M3x12沿X，位于皮带上方，不允许夹爪或螺钉穿入固定支板。',
        '夹齿模型仅为2mm节距示意：必须匹配实带齿形，实测压紧、拉脱和疲劳，不能只依靠摩擦。',
        '惰轮2×MR105ZZ 5×10×4，肩轴D5、M5接收；隔套只支承轴承内圈。供应商额定负荷/结构必须确认。',
        'X惰轮底座允许向右2mm，4个M4锁紧，M3顶丝调节；Y惰轮钢滑座在支板下方，允许向后2mm，两M3锁紧。',
        '顶丝不是唯一保持件。调整后锁紧槽孔螺钉；不得靠猛拧顶丝给电机轴和轴承过量预紧。',
        '15N预紧仅为径向力估算例，不是操作张力；工作张力及张紧器实际行程需按所购皮带确认。',
        '全行程检查：两股皮带都要通过支座；查看惰轮/回程股与螺钉头、轴承、夹块及防护的间隙。'])
    codes.append('S01')
    info(c, 'S02', '托盘承力、丝杆与安全边界', [
        '货物主承力路径：料盒→托盘→两根25×25×2金属方管/端塞连接→Z升降板→钢螺母桥→丝杆/推力支承→双柱/X导向/底板。',
        'Y支板通过两端垫块挂接方管；夹爪轻连接臂只传递推拉力，不承担整盒货物的竖向重量。',
        '前端Y=-31：2×M4x60沉头穿过托盘及6×4.5×21钢压缩套；后端Y=-217：2×M3x55圆柱头+垫圈，从管顶安装。',
        '后端已有实心金属端塞，配作竖向高度21承担压紧；只开M3通过孔，避开X±5的两条M5轴向螺孔，不能再塞压缩套或扩到6.2。',
        '四处都有17mm端垫块、6mm支板及下垫圈/螺母。不得把支撑移到中间挡住连接臂，也不得省略压缩承托压瘪方管。',
        'Z维持E01结构：TR8x2总长298，工作螺纹Z110..338，下/上Ø6轴颈20/50，横销孔Z362.5。',
        '工作螺母底=层面-62，钢桥底=层面-70；M4桥孔Z=层面-54/-22，维护鞋和钢销保持。',
        '顶端径向626ZZ Z345..351、推力栈Z351..375、吊座Z375..401、顶板Z401..413、电机安装面Z413。',
        '候选5×6联轴器Z380..405；丝杆端Z388，电机轴端约Z389。实际夹紧、轴向保持和轴承预紧必须确认。',
        '1kg货物约9.8N，但Z还要升降平台/电机等自重；托盘伸出也有弯矩。不能把轻载解释成无需设计裕量。',
        '第二螺母、维护销和低导程丝杆都不是完整自动防坠系统；独立装置仍未选定。',
        '限位开关仅候选位置，需实际支架/触发件/接线；急停、门禁、接地、保护、柔性线束和固件均需完善。'])
    codes.append('S02')
    info(c, 'S03', '同口径质量/扭矩对比与试装顺序', [
        *[f"{r['axis']}：含1kg货载及余量的运动质量 E01 {r['E01_mass_kg']:.2f} → E02 {r['E02_mass_kg']:.2f} kg；所需扭矩SF2 {r['E01_torque_SF2_Nm']:.3f} → {r['E02_torque_SF2_Nm']:.3f} N·m。" for r in sizing['comparison_to_E01']],
        '每台完整电机暂按0.50kg，质量/密度和摩擦是假定；未取得实测扭矩曲线，不能宣称电机一定满足。',
        '驱动扭矩降低不等于电机轴受力更小：同步带张紧会增加径向载荷，必须核对轴承能力。',
        '装配顺序：固定底板→校正X轨/滑块→双柱/Z导向/丝杆支承→托盘与压缩套→Y双轨/轻推拉头→XY带轮/皮带/张紧。',
        '先用手转动并逐点检查全行程；检查夹爪齿形、张紧锁紧、两股带路、沉头齐平及线束。',
        '先完成独立防下滑和电气安全链，再组织有防护/二次支撑的空行程和空盒试验，之后分级加载。',
        '当前不允许直接上电带载。几何、理想弹性筛查和PDF审计都不是实物安全验收。'])
    codes.append('S03')
    names = {'base', 'x_carriage', 'z_carriage', 'z_top_plate', 'z_screw', 'y_spine', 'y_puller_plate',
             'carrier_tray', 'cell_0_1', 'io_deck', 'x_fixed_motor_stand', 'x_idler_stand'}
    selected = [i.located() for i in m.items if i.name in names or i.name.startswith(('z_post_', 'tray_tube_', 'column_0_post_', 'io_leg_'))]
    shape = cq.Compound.makeCompound(selected); border(c, 'A03', '主结构正投影（省略防护、采购电机和小五金）', '1:6')
    cache = {}
    for kind, x, y, label in [('top', 23, 160, '俯视 X/Y'), ('front', 23, 51, '主视 X/Z'), ('right', 155, 51, '右视 Y/Z')]:
        util.view(c, shape, kind, x, y, 1/6, label, cache)
    util.paragraphs(c, 280, 260, ['本页尺寸是所示结构件包围盒；整机含防护外廓约616×596×523。',
        '未缩小料盒/货位，不是承重缩比试验。', 'Z升降95，X横移180，Y取放143；进出料窗口独立。',
        '金属支板加宽、局部降低，目的是同时避开滑块、皮带、方管和IO立脚。'], size=9, step=5)
    codes.append('A03'); c.showPage()
    for row in manifest['parts']:
        if row['process'] not in ('print', 'machined', 'cut_panel'): continue
        p = m.parts[row['name']]; b = p.shape.BoundingBox(); code = row['code']
        scale = min(1, 108/max(b.xlen, b.ylen, 1), 78/max(b.zlen, b.ylen, 1))
        scale = next(s for s in (1, .5, 1/3, .25, .2, 1/6, .1, .05) if s <= scale+1e-8)
        border(c, code, code+' '+p.name, '1:'+util.fmt(1/scale)); cache = {}
        for kind, x, y, label in [('top', 23, 172, '俯视 X/Y'), ('front', 23, 61, '主视 X/Z'), ('right', 155, 61, '右视 Y/Z')]:
            util.view(c, p.shape, kind, x, y, scale, label, cache)
        y = util.paragraphs(c, 280, 260, [f"数量{row['quantity']}，材料{p.material}，工艺{p.process}。", '局部原点/坐标同分件STEP；包围盒起点：',
            str([round(n, 3) for n in row['bounds_mm'][:3]]), '模型尺寸不是制造公差。', p.note or '装配位置以总装STEP/manifest为准。',
            '打印仅process=print的分件；金属件不能打印替代。', f'构造孔轴表共{len(p.holes)}项，见后续表页。',
            '槽、沉头、凹口及手工切除特征以三维STEP/文字说明为准；孔轴表不是完整加工工艺。'], width=124, size=8, step=4)
        if y < 32: raise RuntimeError('Part text overflow '+code)
        codes.append(code); c.showPage()
        for offset in range(0, len(p.holes), 38):
            hcode = f'{code}-H{offset//38+1}'; border(c, hcode, code+' 局部孔轴表（包络孔，不是螺纹定义）')
            util.text(c, 18, 259, '序号 | 起点X,Y,Z（mm） | 轴向 | 直径 | 包络长度', 10); y = 250
            for j, (o, axis, dia, length) in enumerate(p.holes[offset:offset+38], offset+1):
                util.text(c, 18, y, f'{j:03} | '+', '.join(util.fmt(n) for n in o)+' | '+str(axis)+f' | Ø{util.fmt(dia)} | {util.fmt(length)}', 9); y -= 5.3
            codes.append(hcode); c.showPage()
        print('DRAWN', code, p.name, flush=True)
    c.save()
    (OUT/'drawings/manifest.json').write_text(json.dumps({'fingerprint': FINGERPRINT, 'generator_sha256': sha(Path(__file__)),
        'file': path.name, 'sha256': sha(path), 'page_count': len(codes), 'pages': codes,
        'vectors_from_actual_BRep_HLR': True, 'font_embedded': True, 'machining_release_allowed': False,
        'loaded_operation_allowed': False}, ensure_ascii=False, indent=2))


def main():
    manifest = json.loads((OUT/'manifest.json').read_text()); sizing = json.loads((OUT/'engineering_checks.json').read_text())
    if manifest['fingerprint'] != FINGERPRINT or sizing['fingerprint'] != FINGERPRINT: raise RuntimeError('Stale E02 geometry')
    m = build_model(); lists(manifest, sizing); drawings(m, manifest, sizing)
    print('E02 DRAWINGS AND LISTS COMPLETE', flush=True)


if __name__ == '__main__':
    main()
