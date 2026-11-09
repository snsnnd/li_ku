"""E01 drawings, print/procurement lists and an audited package.

Only writes E01 output. Reuses projection/font primitives, never the M01 labels.
Drawings describe design geometry, not supplier selection or permission to power.
"""
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

from powered_mvp import ROOT, OUT, FINGERPRINT, build_model, v2
sys.path.insert(0, str(ROOT/'cad/manual_mvp'))
import drawings as util


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def border(c, code, title, scale='见视图'):
    c.setStrokeColorRGB(.1, .15, .2); c.setLineWidth(.45)
    c.rect(8*mm, 8*mm, 404*mm, 281*mm)
    c.line(8*mm, 25*mm, 412*mm, 25*mm)
    util.text(c, 12, 282, title, 13)
    util.text(c, 12, 274, '电驱单库位 E01  /  三台实物ZDT外形  /  XY齿条 + Z金属TR8x2  /  1 kg仅为设计目标', 9)
    util.text(c, 12, 18, f'{code} | A3横向 | mm | 比例 {scale} | 设计评审稿，非加工/运行放行', 8)
    util.text(c, 12, 12, '供应商配合、公差、螺纹、紧固和独立防坠未验收；不得按光滑孔/包络实体制作采购件。', 7)
    util.text(c, 302, 12, FINGERPRINT[:20], 7)


def preview(m, name, pose=None):
    pose = pose or {}
    fig = plt.figure(figsize=(13, 10), dpi=140)
    ax = fig.add_subplot(111, projection='3d', proj_type='ortho')
    points = []
    for i in m.items:
        # Omit translucent panels to make the actual mechanisms visible; the
        # complete enclosure is retained in BOTH STEP exports.
        if i.part.material == 'guard' or i.name == 'maintenance_pin' and pose:
            continue
        # Actual located geometry is used for moving/rotating positions.
        shape = i.located(**pose)
        vertices, faces = shape.tessellate(.5, .2)
        v = np.array([p.toTuple() for p in vertices]); points.append(v)
        colour = v2.COLORS.get(i.part.material, (.5, .5, .5))[:3]
        if i.part.process == 'candidate': colour = (.95, .56, .12)
        ax.add_collection3d(Poly3DCollection(v[np.asarray(faces)], facecolors=colour, edgecolors=(0, 0, 0, 0),
            shade=True, lightsource=LightSource(310, 45)))
    p = np.concatenate(points); lo, hi = p.min(0), p.max(0)
    ax.set_xlim(lo[0]-10, hi[0]+10); ax.set_ylim(lo[1]-10, hi[1]+10); ax.set_zlim(lo[2]-10, hi[2]+10)
    ax.set_box_aspect(hi-lo); ax.view_init(24, -51); ax.grid(False)
    ax.set_xlabel('X mm'); ax.set_ylabel('Y mm'); ax.set_zlabel('Z mm')
    ax.set_title('E01 / 3 actual motor CAD models / XY racks + TR8x2 Z / NOT load-accepted\nGuard panels omitted in preview only')
    path = OUT/'previews'/name
    fig.savefig(path, bbox_inches='tight'); plt.close(fig)
    return path


def info_page(c, code, title, lines):
    border(c, code, title, '示意/说明不按比例')
    y = util.paragraphs(c, 18, 260, lines, width=380, size=10, step=6)
    if y < 32: raise RuntimeError('Text overflow '+code)
    c.showPage()


def make_drawings(m, manifest):
    util.font()
    (OUT/'drawings').mkdir(parents=True, exist_ok=True)
    (OUT/'previews').mkdir(parents=True, exist_ok=True)
    image = preview(m, 'E01_assembly.png')
    preview(m, 'E01_at_IO.png', {'dx': -180, 'dz': -95})
    preview(m, 'E01_transfer.png', {'q': 143})
    target = OUT/'drawings/电驱单库位MVP_E01_工程图.pdf'
    c = canvas.Canvas(str(target), pagesize=(util.W, util.H))
    c.setTitle('电驱单库位MVP E01 — 机械设计评审图，未放行带载')
    c.setAuthor('立库项目')
    codes = []
    border(c, 'A01', '电驱单库位MVP — 总装与使用边界', '预览不按比例')
    c.drawImage(str(image), 10*mm, 45*mm, 260*mm, 215*mm, preserveAspectRatio=True, mask='auto')
    util.paragraphs(c, 280, 260, [
        '不是手动M01改名：装入3台完整ZDT参考外形，保留后置驱动器和接头。',
        '1个货位 + 独立IO；1只原尺寸料盒。',
        'X行程180，Z层面200..295，Y取放143。',
        '连续金属底板610x650x6；整机防护外廓约616x656x523。',
        'XY：m1.5/20°/20T打印齿形，金属夹紧轮毂；直接驱动，不用原减速器。',
        'Z：TR8x2金属丝杆 + 双金属螺母 + 顶端推力/径向支承 + 下浮动支承。',
        '目标货载1 kg不含运动机构自重；扭矩估算含自重和余量。',
        '橙色为未选型包络；图中维护销为手动支撑，运动前必须拔除。',
        '禁止直接上电带载：独立制动、电气限位/门禁/急停及固件尚未实现。',
        '保护板仅在预览中省略，完整STEP保留。'], size=9, step=5)
    codes.append('A01'); c.showPage()
    info_page(c, 'A02', '坐标、导向与装配基准', [
        '坐标：底板下表面Z=0，上表面Z=6；不是旧手动版的Z基准。X=0为轨道中央，Y按STEP坐标。',
        '唯一货位承托面：(90,65,295)；IO承托面：(-90,65,200)；移动托盘中心Y=-78。',
        'X：2x MGN12 L400，Y=-285/-215，轨底Z30；4个长滑块；移动板160x160x8，后伸段承托X电机。',
        'X电机中心：(90,-341)，安装面Z86，齿轮下表面Z60；齿条背板中心Y=-367。',
        'Z：2x3030 L350，X=90±45,Y=-268，端面Z51/401；双MGN12 L250，轨道Z85..335。',
        'Z电机安装面：(90,-268,413)，轴向下；顶板Z401..413，电机安装螺钉从下方沉孔安装。',
        'Y：2xMGN9 L200，X=90±13,Y=-125；运动头及Y电机随取放行程，必须有柔性线束/应力释放。',
        '先调金属导轨平行，再锁整排齿条；不得用单段垫片掩盖齿条高度/接缝误差。',
        '图纸为三视图+孔轴表+关键堆叠说明。采购件外形不是制造图；螺纹/配合需供应商图确认。'])
    codes.append('A02')
    border(c, 'A03', '主承力装配正投影（省略外罩、紧固件及采购候选件）', '各视图1:6')
    names = {'base', 'x_carriage', 'z_top_plate', 'z_carriage', 'z_screw', 'z_nut_bridge',
             'z_working_nut', 'z_safety_nut', 'z_safety_cage', 'z_fixed_bearing_housing',
             'z_bearing_hanger', 'z_floating_pedestal', 'carrier_tray', 'cell_0_1', 'io_deck', 'io_deck_frame'}
    selected = [i.located() for i in m.items if i.name in names or i.name.startswith(('z_post_', 'tray_tube_', 'column_0_post_', 'io_leg_'))]
    shape = cq.Compound.makeCompound(selected)
    cache = {}
    util.view(c, shape, 'top', 23, 153, 1/6, '俯视 X/Y', cache)
    util.view(c, shape, 'front', 23, 51, 1/6, '主视 X/Z', cache)
    util.view(c, shape, 'right', 155, 51, 1/6, '右视 Y/Z', cache)
    util.paragraphs(c, 280, 260, [
        '本页尺寸为所示主承力件包围盒，不是含防护罩的整机外廓。',
        '层面：IO Z200；货位Z295；两者相差95。',
        '货位X90，IO X-90；中心距180。',
        '托盘Y-78，货位Y65，取放距离143。',
        '底板Z0..6；X移动板Z43..51；立柱Z51..401；顶板Z401..413。',
        '省略内容只为读图；三个实际电机和所有CAD实例均在总装STEP中。',
        '承力路径：料盒→托盘/方管→Z板→钢螺母桥→螺母/丝杆→顶端推力支承→顶板/双柱→X板/滑块→双轨/基条→底板/台面。',
        '几何贴合检查不代表连接强度、导轨寿命或动态承载合格。'], size=9, step=5)
    codes.append('A03'); c.showPage()
    info_page(c, 'S01', 'Z丝杆支承与螺母承力堆叠', [
        '丝杆：TR8x2，导程2，不能买TR8x8代替；总长298，模型轴向Z90..388。',
        '加工端：下轴颈Ø6x20，Z90..110；螺纹段Z110..338；上轴颈Ø6x50，Z338..388。',
        '上轴颈/定位套配作Ø2.5横孔：Z362.5。材料、热处理、配作公差和销保持需供应商审核；禁止打印替代。',
        '下支座Z51..95，下壳Z95..103，626ZZ位于Z97..103，下盖Z103..105。下轴承应允许轴向浮动。',
        '顶端：径向626ZZ Z345..351 → 支承垫Z351..354 → 推力轴承Z354..358.5。',
        '定位套Z358.5..366.5，横销中心Z362.5 → 第二推力轴承Z366.5..371 → 钢端盖Z371..375。',
        '顶端轴承壳Z345..371；吊座Z375..401，与顶板Z401贴合。夹紧/预紧与额定推力未验收。',
        '候选联轴器：Ø19x25，Z380..405，下孔6上孔5；丝杆端Z388，电机轴端约Z389，留1mm端间隙。',
        '工作螺母法兰底=层面-62；钢桥底=层面-70，8mm座板；桥上立板高至层面-14。',
        '桥M4通过孔：X=90±23，Z=层面-54/-22。M4x25+垫圈+螺母；两排避开Y导轨/止挡。',
        '第二螺母被钢笼限转、轴向留0.8间隙，只是冗余螺母，不能应对所有断轴/联轴器/断电故障。',
        '独立自动制动器尚未选型。手动维护鞋与D4销只在Z200/Z295停机维护时使用，绝非自动防坠。'])
    codes.append('S01')
    info_page(c, 'S02', '装配顺序与上电前检查', [
        '1. 全面支承金属底板并固定台面；校核台面/锚栓。防护架不能代替轴系承力架。',
        '2. 安装X基条/双轨/4滑块，确认轨螺钉沉头不高于轨道；装移动板及3030立柱。',
        '3. 安装Z双轨/4滑块/升降板；保持手工移动顺畅，再装钢螺母桥和双螺母。',
        '4. 装丝杆上下支承，检查轴承配合、垫片预紧与横销；螺杆应独立转动无卡滞后再连接电机。',
        '5. 安装X后伸电机组件、金属轮毂、打印齿轮，整排调齿隙；安装Y双轨、齿条、运动头和Y电机。',
        '6. X/Y金属夹紧轮毂：5H7轴孔、Ø12齿轮定位；M3夹紧位在局部Y5/Z19；扭矩和轴向保持需实测。',
        '7. 装托盘、金属方管、货位和IO，所有滑动承托面螺钉必须齐平；检查料盒插拔和锁销释放。',
        '8. Y运动头M3x50长螺钉穿过立脚和底部加强筋，以底面螺母锁紧；禁止短螺钉埋入筋内。',
        '9. 限位开关位置只是空间预留，实际支架、触发片、硬限位和接线未实现；不得把CAD包络当成能触发。',
        '10. 选定独立防下滑装置、急停和门禁，完成断电/失控故障检查与线束全行程检查后，才可组织试机。',
        '11. 有防护和二次支撑的前提下，先单轴空行程、空盒，之后分级加载；每步检查温升、失步、蠕变和松动。',
        '12. 现阶段不提供自动存取固件。释放机构、IO门和各传感器仍需接入实际控制系统。'])
    codes.append('S02')
    sizing = json.loads((OUT/'engineering_checks.json').read_text())
    info_page(c, 'S03', '1 kg目标下的驱动估算（非电机验收）', [
        '模型自重按体积/假定密度估算，每台完整电机暂按0.50kg；实际称重及扭矩-转速曲线缺失。',
        *[f"{r['axis']}：含1kg货载及余量的运动质量{r['moving_mass_with_1kg_payload_and_allowance_kg']:.2f} kg；候选速度{r['candidate_initial_speed_mm_s']} mm/s；转速{r['motor_rpm']:.2f} rpm；含SF2所需电机扭矩{r['required_motor_torque_SF2_Nm']:.3f} N·m。" for r in sizing['motor_targets']],
        '上述速度不是控制参数放行。Z效率暂按0.25；XY总效率0.8；摩擦/线束拖曳均为设计假定。',
        '禁止用保持扭矩代替运行扭矩；需核对供电、驱动电流、连续温升和对应转速下的裕量。',
        '丝杆理想压屈/轴向应力仅为筛查，未覆盖根部缺口、横孔、疲劳、推力轴承、连接及动态防坠。',
        '1kg是设计输入，不是额定承载或许可试验载荷。先完成安全链和部件选型，禁止直接带载运行。'])
    codes.append('S03')
    # Every actual printed/machined/cut-panel part receives exact BRep views.
    for row in manifest['parts']:
        if row['process'] not in ('print', 'machined', 'cut_panel'):
            continue
        p = m.parts[row['name']]; b = p.shape.BoundingBox()
        scale = min(1, 108/max(b.xlen, b.ylen, 1), 78/max(b.zlen, b.ylen, 1))
        scale = next(s for s in (1, .5, 1/3, .25, .2, 1/6, .1, .05) if s <= scale+1e-8)
        code = row['code']; border(c, code, code+' '+p.name, '1:'+util.fmt(1/scale))
        cache = {}  # avoid id reuse across parts
        util.view(c, p.shape, 'top', 23, 172, scale, '俯视 X/Y', cache)
        util.view(c, p.shape, 'front', 23, 61, scale, '主视 X/Z', cache)
        util.view(c, p.shape, 'right', 155, 61, scale, '右视 Y/Z', cache)
        lines = [f"数量{row['quantity']}；材料{p.material}；工艺{p.process}。", '原点/方向与分件STEP一致；包围盒起点：',
                 str([round(n, 3) for n in row['bounds_mm'][:3]]),
                 '尺寸是模型几何值，不是制造公差。', p.note or '装配位置见总装STEP和manifest实例表。',
                 '打印件：STL已落床；先查支撑/悬垂。', '金属件不得打印替代；加工公差与螺纹需评审。',
                 f'孔轴表：共{len(p.holes)}项，另见后续表页。', '实体含沉孔/沉头/槽等特征；孔轴表不是完整工艺路线。']
        y = util.paragraphs(c, 280, 260, lines, width=124, size=8, step=4)
        if y < 32: raise RuntimeError('Part note overflow '+code)
        codes.append(code); c.showPage()
        for offset in range(0, len(p.holes), 38):
            suffix = f'{code}-H{offset//38+1}'
            border(c, suffix, code+' 局部孔轴表（钻孔包络，非螺纹定义）')
            util.text(c, 18, 259, '序号 | 起点 X,Y,Z（局部mm） | 轴向 | 直径 | 包络长度', 10)
            y = 250
            for j, (origin, axis, dia, length) in enumerate(p.holes[offset:offset+38], offset+1):
                util.text(c, 18, y, f'{j:03} | '+', '.join(util.fmt(n) for n in origin)+' | '+str(axis)+f' | Ø{util.fmt(dia)} | {util.fmt(length)}', 9)
                y -= 5.3
            util.text(c, 18, 35, '孔轴表来源于设计构造；手工切除的槽/锥面以STEP三维形状及文字说明为准。请核对接收件孔位。', 8)
            codes.append(suffix); c.showPage()
        print('DRAWN', code, p.name, flush=True)
    c.save()
    report = {'fingerprint': FINGERPRINT, 'generator_sha256': sha(Path(__file__)), 'file': target.name,
              'sha256': sha(target), 'page_count': len(codes), 'pages': codes,
              'vectors_from_actual_BRep_HLR': True, 'font_embedded': True,
              'machining_release_allowed': False, 'loaded_operation_allowed': False}
    (OUT/'drawings/manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


def lists(manifest):
    fields = ['code', 'name', 'quantity', 'material', 'process', 'note']
    for filename, rows in [('打印清单.csv', [r for r in manifest['parts'] if r['process'] == 'print']),
                           ('采购与金属加工清单.csv', [r for r in manifest['parts'] if r['process'] != 'print'])]:
        with (OUT/filename).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    # Keep omissions explicit: modeled hardware counts are not a claim of a
    # complete production purchasing kit.
    (OUT/'采购补充与未选型项.md').write_text('''# E01采购边界与补充清单

`采购与金属加工清单.csv`是CAD实际出现的实例数量，不是已经选定品牌或可以一键下单的全套生产BOM。

## 主要选型
- 现有ZDT完整电机3台；实测轴径/轴长/31mm孔距及盲孔深度，提供电气参数和运行曲线。
- MGN12双轨X400、Z250，各4个长滑块；MGN9双轨Y200，各1个长滑块。实际高度、孔距、端距以供应商图为准。
- TR8x2金属丝杆总长298，工作螺纹228；双金属螺母，Ø6加工轴颈；勿用TR8x8替换。
- 626ZZ 2个、F6-12M推力轴承2个；横销、定位套、配合作业和预紧必须审核。
- 联轴器5x6（Ø19x25空间），需有可靠夹紧和额定扭矩，不得打印替代。
- XY自制金属夹紧轮毂各1；角相位不同，分件STEP表示装配相位，不是不同轴孔。

## 尚未选型/未完整建模，不能遗漏
- 独立常闭制动/防下滑装置及实际安装接口、故障安全控制。图中候选包络并非可采购产品。
- 急停、安全门开关/门锁、接触器或合适安全断能方案、电源/保护接地、熔断/短路保护；应按实际驱动器接线规范设计。
- 6个轴端限位仅有候选体积：需要实际开关、安装支架、触发件、归零/硬限位接线及动作距离校核。
- 线束、拖链/柔性支撑、护线套、应力释放；Y电机和释放机构全行程线束未画。
- 柜门铰链/锁扣、PC板连接件、封闭缝隙和台面锚栓需实际选定。
- 型材角码/T螺母、轨道基条/底板、齿条/背板、IO立脚/框架、托盘/方管、螺母法兰/钢笼、轴承壳/顶板等连接的全部非建模螺钉、垫圈和压缩套。
- 这些非建模连接不能直接按孔径猜螺钉长度：需逐项核对叠厚、有效啮合、盲孔底部、工具可达性和防松。总装STEP主要电机/导轨/滑块/桥螺钉已建模，但不是全部紧固件。
- 除XYZ三台电机外，释放执行器、IO门执行器及相关控制仍需按继承机构实际选型，未提供自动程序。

**目前是机械设计评审交付，不是可直接制造/上电/1kg带载的整机放行。**
''', encoding='utf-8')


def main():
    manifest = json.loads((OUT/'manifest.json').read_text())
    if manifest['fingerprint'] != FINGERPRINT: raise RuntimeError('Stale exports')
    m = build_model()
    lists(manifest)
    make_drawings(m, manifest)
    print('DRAWINGS AND LISTS COMPLETE', flush=True)


if __name__ == '__main__':
    main()
