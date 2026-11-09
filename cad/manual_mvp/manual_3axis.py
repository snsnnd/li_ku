"""Hand-operated one-cell XYZ fit prototype; no motors, no loaded lift release.

Original V03 tooth geometry and full-size V02 bin interface; printed guides,
printed frame and manual pin deliberately do NOT represent the metal machine.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'cad/v03'))
import gears
sys.path.insert(0, str(ROOT/'cad/v02'))
import asrs_v02 as kit

box, cyl, fuse, drill, hz, hy, hx = kit.box, kit.cyl, kit.fuse, kit.drill, kit.hz, kit.hy, kit.hx
OUT = ROOT/'model/Manual_3Axis_MVP'
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in
    (Path(__file__), Path(gears.__file__), Path(kit.__file__)))).hexdigest()
CLEARANCE = .35
DECK = 250.
Z_LOCKS = (-40, -20, 0, 20, 40)


def orient(shape, frame):
    if frame == 'Z':
        return shape.rotate((0, 0, 0), (1, 1, 1), 240)
    if frame == 'Y':
        return shape.rotate((0, 0, 0), (0, 0, 1), 90)
    if frame == 'R':
        return shape.rotate((0, 0, 0), (0, 0, 1), 180)
    return shape


def hex_cut(x, y, z, af, height):
    return cq.Workplane('XY').polygon(6, af*2/math.sqrt(3)).extrude(height).val().rotate(
        (0, 0, 0), (0, 0, 1), 30).translate((x, y, z))


def through_nut(shape, x, y, top, thickness, diameter=3.4, af=5.8, nut_h=2.6):
    shape = shape.cut(cyl(x, y, top-thickness-1, diameter/2, thickness+2))
    return shape.cut(hex_cut(x, y, top-thickness-.1, af, nut_h+.1))


def profile(length, yc, points):
    # YZ normal is +X; explicitly centre its extrusion along the travel axis.
    return cq.Workplane('YZ').polyline([(y+yc, z) for y, z in points]).close().extrude(length).val().translate((-length/2, 0, 0))


def rail_profile(length, yc):
    return profile(length, yc, [(-5, 6), (5, 6), (9, 14), (9, 16), (-9, 16), (-9, 14)])


def guide_void(length, yc, c=CLEARANCE):
    return profile(length, yc, [(-5-c, 5), (5+c, 5), (5+c, 6-c),
        (9+c, 14-c), (9+c, 16+c), (-9-c, 16+c), (-9-c, 14-c), (-5-c, 6-c)])


@dataclass
class Part:
    code: str
    name: str
    shape: cq.Shape
    process: str = 'print'
    notes: list = field(default_factory=list)
    features: list = field(default_factory=list)
    print_axis: str = 'Z'


@dataclass
class Item:
    name: str
    part: Part
    origin: tuple = (0, 0, 0)
    frame: str = 'I'
    group: str = 'fixed'
    axis_mount: bool = False
    rotates: bool = False
    initial_s: float = 0
    raw_offset: tuple = (0, 0, 0)

    def located(self, dx=0, dz=0, q=0, lift=0, stored=False, lock=True):
        s = self.part.shape.translate(self.raw_offset)
        group = self.group.replace('gear_', '')
        if self.axis_mount:
            delta = {'x': dx, 'z': dz, 'y': q}[group]
            if self.rotates:
                s = s.rotate((0, 0, 0), (0, 0, 1), math.degrees(-(self.initial_s+delta+gears.SEGMENT_LENGTH)/gears.RADIUS))
            s = s.rotate((0, 0, 0), (1, 0, 0), 90).translate((self.initial_s, 6, 29))
        s = orient(s, self.frame)
        x, y, z = self.origin
        if group != 'fixed':
            x += dx
        if group in ('z', 'y', 'bin', 'pin', 'lock'):
            z += dz
        if group in ('y', 'pin'):
            y += q
        if group == 'bin':
            if stored:
                x, y, z = 0, 65, DECK
            else:
                y += q
        if group == 'pin':
            z += lift
        return s.translate((x, y, z))


class Model:
    def __init__(self):
        self.parts = {}
        self.items = []
        self.hardware = []

    def part(self, code, name, shape, notes=(), features=(), process='print', print_axis='Z'):
        if not shape.isValid() or len(shape.Solids()) != 1:
            raise ValueError('Invalid/non-single part '+code)
        p = Part(code, name, shape, process, list(notes), list(features), print_axis)
        self.parts[code] = p
        return p

    def add(self, name, part, origin=(0, 0, 0), frame='I', group='fixed', **kwargs):
        i = Item(name, part, origin, frame, group, **kwargs)
        self.items.append(i)
        return i

    def buy(self, name, quantity, purpose):
        self.hardware.append({'specification': name, 'quantity': quantity, 'purpose': purpose})


def build():
    m = Model()
    S = gears.SEGMENT_LENGTH
    rack = m.part('P01', '齿条_原齿形24齿距', gears.rack(),
        ['m1.5 / 20deg；24齿距，L=113.097336；不可取整为113。', '每轴两段，接缝必须共面、共相位。'],
        ['齿宽12；底宽30；底厚6.3；节线高8；齿顶高9.5。', '4x Ø3.4：X=28.274334/84.823002，Y=±11；基准为左端X0/底面Z0。'])
    pinion = m.part('P02', '小齿轮_原渐开线20T', gears.pinion(),
        ['原 V03 齿形；不承担防坠；不得做载荷认证。'],
        ['m1.5 / 20齿 / 20deg；节圆Ø30，齿顶圆Ø33，齿根圆Ø26.25。', '厚12；中心孔Ø12.2；2x Ø3.4，中心X=±9、Y=0。'])
    hub = fuse(cyl(0, 0, -6, 5.9, 32), cyl(0, 0, 12, 12, 4), cyl(0, 0, 26, 19, 4))
    hub = hub.cut(cyl(0, 0, -7, 3.2, 39))
    for xx in (-9, 9):
        hub = hub.cut(cyl(xx, 0, 11, 1.7, 6)).cut(cyl(xx, 0, 25, 3, 6))
    for yy in (-12, 12):
        hub = hub.cut(cyl(0, yy, 25, 3.5, 6))
    hub = m.part('P03', '手轮与齿轮连接套', hub,
        ['只用于空箱手动验证；去掉支撑后不得磨削定位套圆柱。', '打印时套筒端朝下，法兰下方需要支撑。'],
        ['套筒Ø11.8、通孔Ø6.4；Z=-6..26；法兰Ø24，Z12..16。', '手轮Ø38，Z26..30；2xØ6工具孔X±9；2xØ7手指孔Y±12。', '法兰2xØ3.4，X±9；用M3x20穿齿轮锁紧。'])
    shim = m.part('P04', '轴向垫片_1p8', cyl(0, 0, 0, 6, 1.8).cut(cyl(0, 0, -1, 3.2, 4)),
        ['配金属隔套L40；总名义轴向游隙0.4，不得拧紧到夹住转动件。'], ['Ø12 / Ø6.4 / 厚1.8。'])

    # Captive printed sliders; their dovetail profiles print vertically along X.
    carriage = fuse(*[box(0, yc, 6+CLEARANCE, 60, 25, 21-6-CLEARANCE).cut(guide_void(62, yc)) for yc in (-40, 40)],
                     *[box(0, yc, 21, 60, 6, 28) for yc in (-50, 50)],
                     box(0, 0, 49, 60, 112, 6), box(0, 17, 21, 20, 6, 22), box(0, 35, 40, 20, 30, 6))
    for xx in (-20, 20):
        for yy in (-40, -20, 20, 40):
            carriage = carriage.cut(cyl(xx, yy, 48, 1.7, 8))
    carriage = carriage.cut(cyl(0, 13, 29, 2.2, 24, (0, 1, 0)))
    cart = m.part('P05', '通用手动滑台', carriage,
        ['沿X端面朝下打印；先用配合试块检查导向间隙。', '只有X/Y使用；Z用P06带锁孔版。'],
        ['导向中心距80；滑块长60；桥板60x112x6，Z49..55。', '安装孔Ø3.4：X±20，Y±20/±40，穿桥板。', 'M4轴孔：X0,Z29，沿Y；轴座Y14..20。', '截面参照S02：标称间隙0.35，不能按外廓猜滑槽。'], print_axis='X')
    zcart = carriage.fuse(box(0, -61, 49, 24, 22, 6)).cut(cyl(0, -66, 48, 2.2, 8))
    zcart = m.part('P06', 'Z滑台_带手动锁孔', zcart,
        ['必须装钢制M4锁销；打印滑台与齿轮都不是安全防坠器。'],
        ['P05全部尺寸；另加锁耳X±12,Y=-72..-50,Z49..55；Ø4.4位于X0,Y-66。'], print_axis='X')
    stop = box(0, 0, 6, 8, 120, 16).cut(box(0, 0, 5, 10, 36, 12))
    for yy in (-40, 40):
        stop = stop.cut(guide_void(10, yy))
    stop = drill(stop, [hz(0, yy, 5, 3.4, 18) for yy in (-23, 23)])
    stop = m.part('P07', '可拆行程端挡', stop,
        ['滑台从轨道端部装入后，再安装两端挡。不可省略。'], ['8x120，Z6..22；两安装孔Ø3.4位于X0,Y±23；中央通道宽36、顶高17。'], print_axis='X')

    def base(code, width, axis):
        s = fuse(box(0, 0, 0, 240, width, 6), rail_profile(220, -40), rail_profile(220, 40))
        holes = [(-S+j*S+t, yy) for j in range(2) for t in (6*gears.PITCH, 18*gears.PITCH) for yy in (-11, 11)]
        holes += [(xx, yy) for xx in (-106, 106) for yy in (-23, 23)]
        if axis == 'X':
            holes += [(xx, yy) for xx in (-116, 116) for yy in (-40, 40)]
        if axis == 'Z':
            s = s.fuse(box(0, -66, 6, 220, 12, 39))
            for xx in Z_LOCKS:
                s = s.cut(cyl(xx, -66, -1, 2.2, 48))
            holes += [(xx, yy) for xx in (-105, -95) for yy in (-50, 50)]
        if axis == 'Y':
            # Rear upright bracket reliefs; outside the longitudinal rack.
            for yy in (-20, 20):
                s = s.cut(box(-117, yy, -1, 8, 21, 9))
            holes += [(-90, yy) for yy in (-23, 23)]
            # Rotated Y-stage: local X -> world Y, local Y -> -world X.
            holes += [(yy+135+off, xx) for yy in (-128, -28) for xx in (-70, 70) for off in (-10, 10)]
        for xx, yy in holes:
            s = through_nut(s, xx, yy, 6, 6)
        return m.part(code, axis+'轴打印导向底座', s,
            ['导向截面见S02；这是打印滑动导向，不等效于正式金属直线导轨。', '所有M3接收孔下方为5.8对边六角螺母窝，深2.6。'],
            [f'240x{width}x6；导轨长220，中心Y±40；截面顶高16。',
             '齿条左端X=-113.097336/0；两段共8孔，Ø3.4。',
             '端挡安装孔X±106,Y±23；其余孔坐标见本页坐标表。']+
            (['锁孔：X=-40/-20/0/20/40，Y=-66，Ø4.4贯穿；锁条Z6..45。'] if axis == 'Z' else []),
            process='print') , holes

    xb, xholes = base('P08', 120, 'X')
    zb, zholes = base('P09', 150, 'Z')
    yb, yholes = base('P10', 160, 'Y')
    # Store actual drilling schedules, not a hand-transcribed subset.
    for p, holes in [(xb, xholes), (zb, zholes), (yb, yholes)]:
        p.features += [f'M3孔坐标：X={xx:.6f}, Y={yy:.6f}。' for xx, yy in holes]

    # Tower's seated foot and rear fastening flange.
    foot = fuse(box(0, 20, 55, 150, 80, 5), box(0, -3, 60, 150, 6, 30))
    foot = drill(foot, [hz(xx, yy, 54, 3.4, 8) for xx in (-20, 20) for yy in (-20, 20)])
    foot = drill(foot, [hy(xx, -7, zz, 3.4, 9) for xx in (-50, 50) for zz in (75, 85)])
    tower_foot = m.part('P11', 'Z立柱落座底脚', foot,
        ['底面贴X滑台桥板，立柱底面落座；不能只靠背面螺钉吊住。'],
        ['底板150x80x5，Y=-20..60,Z55..60；背板Y=-6..0,Z60..90。', '底板Ø3.4：X±20,Y±20；背板Ø3.4：X±50,Z75/85，沿Y。'])
    # Y stage's stepped brackets meet the Z bridge, and its base has reliefs.
    # Move the horizontal ledge outboard of the rack's underside nut pockets.
    bracket = fuse(box(0, 3, -28, 20, 6, 56), box(-5, 28, -21, 18, 44, 6))
    bracket = drill(bracket, [hy(0, -1, zz, 3.4, 8) for zz in (-20, 20)])
    # The lower upright screw/nut must not run into the horizontal ledge.
    # An open rectangular notch avoids the tangent sliver made by a radius-4
    # cylindrical pocket at the ledge edge X=4 (valid B-rep, non-manifold STL).
    bracket = bracket.cut(box(0, 9.9, -24, 9, 8.2, 10))
    bracket = through_nut(bracket, -3, 30, -15, 6)
    mount = m.part('P12', 'Y台与Z桥板连接角座', bracket,
        ['两件镜像安装；Z桥板前表面贴本件Y0；Y底座贴本件Z-15。'],
        ['立面20x6x56，Z=-28..28；承托面X=-14..4,Y6..50,Z-21..-15。', '立面2xØ3.4：X0,Z±20，沿Y；托面Ø3.4：X-3,Y30，底部M3螺母窝。',
         '下螺母让位槽：X±4.5,Y5.8..14,Z=-24..-14；不可省略。'])

    # Carrier pillars stand outside the entire moving Y bridge/head envelope.
    pillar = fuse(box(0, 0, 0, 18, 30, 6), box(0, 0, 6, 12, 12, 63),
                  box(-7, 0, 69, 34, 16, 6),
                  *[cq.Workplane('XZ').polyline([(-24, 69), (-6, 51), (-6, 69)]).close().extrude(3).val().translate((0, yy, 0)) for yy in (8, -5)])
    pillar = drill(pillar, [hz(0, yy, -1, 3.4, 8) for yy in (-10, 10)])
    pillar = through_nut(pillar, -18, 0, 75, 6, 4.5, 7.2, 3.4)
    pillar = m.part('P13', '承托盘外置支柱', pillar,
        ['共4件；左侧两件绕Z转180度；斜撑面朝托盘内侧。'],
        ['底脚18x30x6；柱12x12，Z6..69；顶帽X=-24..10,Y±8,Z69..75。', '底孔2xØ3.4：X0,Y±10；顶孔Ø4.5：X-18,Y0，M4螺母窝对边7.2深3.4。', '双侧45deg斜撑，Y=-8..-5/5..8；中央留螺钉/螺母通道。'])
    deck_s, _ = kit.deck_plate()
    # All eight nest fasteners must sit below the bin sliding surface.
    for xx in (-52, 52):
        for yy in (-50, 50):
            deck_s = deck_s.cut(cq.Solid.makeCone(2.25, 4.5, 2.25, cq.Vector(xx, yy, 1.75)))
    tray = deck_s.cut(box(0, -3.5, -1, 40, 125, 6))
    tray = m.part('P14', '移动承托盘_沉头孔', tray,
        ['4颗M4沉头螺钉头必须齐平或略低，不得顶起料盒。'],
        ['124x130；底厚4；导边内宽111.2，导边高6。', '4xØ4.5，X±52,Y±50；沉孔Ø9x90deg；中央40宽前开槽，后桥6。'])
    cell = deck_s.fuse(box(0, 64, 4, 124, 2, 6))
    cell = m.part('P15', '单库位托板_沉头孔', cell,
        ['4颗M4沉头螺钉头不得高出滑动面；空箱手动验证。'],
        ['124x130，底厚4；4xØ4.5，X±52,Y±50；沉孔Ø9x90deg。', '侧导边内宽111.2；后挡边Y63..65，高6。'])
    bin_part = m.part('P16', '原尺寸空料盒', kit.make_bin(),
        ['只允许空盒；不加砝码、物料或1kg载荷。'],
        ['箱体110x120x60；底/壁2.4；牵引耳32x18x6，中心Y-67,Z10..16。', '牵引孔Ø6.2，X0,Y-68，沿Z。'])

    # Manual pickup pin: no servo/crank. Head's mast clears the actual U-slot.
    head = fuse(box(0, 20, -30, 100, 100, 4), box(0, 40.5, -26, 36, 6, 80),
                box(0, 52, 22, 26, 30, 6), box(0, 52, 48, 26, 30, 6))
    head = drill(head, [hz(xx, yy, -31, 3.4, 7) for xx in (-20, 20) for yy in (-20, 20)])
    head = head.cut(cyl(0, 60.5, 21, 2.2, 35))
    head = m.part('P17', '手动插销取放头', head,
        ['指南：支撑仅加在导销耳下；孔去毛刺后同轴通铰Ø4.4。', '插销抬高14mm后才回撤；不允许用推箱摩擦代替插销连接。'],
        ['底板100x100x4：X±50,Y=-30..70,Z=-30..-26。', '立板36x6x80，Y37.5..43.5；导销耳Z22..28/48..54。', '销孔Ø4.4：X0,Y60.5；底板4xØ3.4：X±20,Y±20。'])
    pull = cyl(0, 0, 0, 10, 8).cut(cyl(0, 0, -1, 2.2, 10)).cut(cyl(0, 0, 4, 3.8, 5))
    pull = m.part('P18', '插销手拉帽', pull,
        ['套在M4x80半牙螺钉头下；手拉帽不承担货物重量。'], ['Ø20x8；通孔Ø4.4；头部凹窝Ø7.6，深4。'])

    # Front fixed stand, with side-loaded M3 nuts in the post tops.
    leg = fuse(box(0, 0, 0, 32, 32, 6), box(0, 0, 6, 16, 16, 228))
    leg = drill(leg, [hz(a, b, -1, 3.4, 8) for a in (-11, 11) for b in (-11, 11)])
    leg = leg.cut(cyl(0, 0, 221, 1.7, 14)).cut(hex_cut(0, 0, 228, 5.8, 3))
    leg = leg.cut(box(0, 4.5, 228, 6, 9, 3))
    leg = m.part('P19', '单库位支腿', leg,
        ['M3螺母从柱顶侧窗装入；总高234，可加Brim竖打或侧放加支撑。'],
        ['底脚32x32x6；柱16x16，Z6..234；底孔X±11,Y±11。', '顶孔Ø3.4；螺母窗Z228..231，M3六角窝5.8对边。'])
    frame = fuse(box(0, 15, 0, 164, 20, 6), box(0, 115, 0, 164, 20, 6),
                 box(-76, 75, 0, 12, 162, 6), box(76, 75, 0, 12, 162, 6))
    frame = drill(frame, [hz(xx, yy, -1, 3.4, 8) for xx in (-76, 76) for yy in (10, 140)])
    for xx in (-52, 52):
        for yy in (15, 115):
            frame = through_nut(frame, xx, yy, 6, 6, 4.5, 7.2, 3.4)
    stand = m.part('P20', '单库位承托框', frame,
        ['先装M4螺母，再装P15；四角M3连接支腿顶螺母。'],
        ['外宽164，Y=-6..156，厚6；框条见三视图。', '支腿孔Ø3.4：X±76,Y10/140；托板孔Ø4.5：X±52,Y15/115，底部M4窝。'])

    # Three 180 mm floor links per side, with positive bolted seam plates.
    def floor_link(code, index):
        length = (180, 140, 220)[index]
        yc = (-280, -120, 60)[index]
        s = box(0, 0, 0, 25, length, 6)
        holes = [(a, edge+off) for edge in (-length/2, length/2) for a in (-6, 6)
                 for off in ((20,) if edge < 0 else (-20,))]
        if index == 0:
            holes += [(a, y-yc) for a in (-6, 6) for y in (-350, -270)]
        for y in (10, 140):
            if yc-length/2 < y < yc+length/2:
                holes += [(a, y-yc) for a in (-6, 6)]
        holes = sorted(set(holes))
        for a, b in holes:
            s = through_nut(s, a, b, 6, 6)
        return m.part(code, f'底架纵梁第{index+1}段', s,
            ['每侧3段，从后至前顺序安装；底面贴平整台面。'],
            [f'25x{length}x6；孔均Ø3.4，下方M3螺母窝5.8对边深2.6。']+
            [f'孔：X={a},Y={b}。' for a, b in holes])
    links = [floor_link('P'+str(21+j), j) for j in range(3)]
    splice = drill(box(0, 0, 0, 25, 64, 4), [hz(xx, yy, -1, 3.4, 6) for xx in (-6, 6) for yy in (-20, 20)])
    splice = m.part('P24', '底架纵梁拼接板', splice, ['每条接缝4颗M3x12；不能只靠对接边承重。'], ['25x64x4；4xØ3.4：X±6,Y±20。'])
    cross = box(0, 0, 0, 245, 32, 6)
    cross = drill(cross, [hz(xx, 0, -1, 3.4, 8) for xx in (-116, -104, 104, 116)])
    for xx in (-76, 76):
        for a in (-11, 11):
            for b in (-11, 11):
                cross = through_nut(cross, xx+a, b, 6, 6)
    cross = m.part('P25', '底架前横梁', cross, ['两根分别支承前/后排库位支腿。'],
        ['245x32x6；纵梁连接孔X=-116/-104/104/116,Y0。', '支腿孔X=±76±11，Y±11；底部M3螺母窝。'])

    # Hardware with dimensions used by the CAD. Threads intentionally simplified.
    axle = m.part('H01', 'M4x60内六角轴螺钉', fuse(cyl(0, 0, -27, 2, 60), cyl(0, 0, 33, 3.5, 4)), process='buy')
    tube = m.part('H02', '金属光滑隔套_6x4p2x40', cyl(0, 0, -8, 3, 40).cut(cyl(0, 0, -9, 2.1, 42)), process='buy')
    washer = m.part('H03', 'M4平垫圈', cyl(0, 0, 0, 4.5, 1).cut(cyl(0, 0, -1, 2.15, 3)), process='buy')
    nut4 = m.part('H04', 'M4普通六角螺母', hex_cut(0, 0, 0, 7, 3.2).cut(cyl(0, 0, -1, 2.1, 6)), process='buy')
    screw3 = m.part('H05', 'M3x20齿轮连接螺钉', fuse(cyl(0, 0, -4, 1.5, 20), cyl(0, 0, 16, 2.75, 3)), process='buy')
    nut3 = m.part('H06', 'M3螺母', hex_cut(0, 0, -3, 5.5, 3).cut(cyl(0, 0, -4, 1.6, 5)), process='buy')

    # The three identical tooth/guide families differ only in mounting orientation.
    stages = [('X', xb, cart, (0, -310, 0), 'I', 'fixed', 'x', 0),
              ('Z', zb, zcart, (0, -310, 180), 'Z', 'x', 'z', 0),
              ('Y', yb, cart, (0, -135, 165), 'Y', 'z', 'y', -71.5)]
    for axis, b, c, origin, fr, base_group, moving_group, initial in stages:
        low = axis.lower()
        m.add(low+'_base', b, origin, fr, base_group)
        for j in range(2):
            shifted = tuple(a+d for a, d in zip(origin, orient(cq.Vertex.makeVertex(-S+j*S, 0, 6), fr).Center().toTuple()))
            m.add(f'{low}_rack_{j}', rack, shifted, fr, base_group)
        for end in (-106, 106):
            shifted = tuple(a+d for a, d in zip(origin, orient(cq.Vertex.makeVertex(end, 0, 0), fr).Center().toTuple()))
            m.add(f'{low}_stop_{end}', stop, shifted, fr, base_group)
        shifted = tuple(a+d for a, d in zip(origin, orient(cq.Vertex.makeVertex(initial, 0, 0), fr).Center().toTuple()))
        m.add(low+'_carriage', c, shifted, fr, moving_group)
        for name, p, rotates, offset in [('pinion', pinion, True, (0, 0, 0)), ('handwheel', hub, True, (0, 0, 0)),
                ('axle', axle, False, (0, 0, 0)), ('tube', tube, False, (0, 0, 0)),
                ('washer_front', washer, False, (0, 0, 32)), ('washer_rear', washer, False, (0, 0, -15)),
                ('nut', nut4, False, (0, 0, -18.2)), ('jam_nut', nut4, False, (0, 0, -21.4)),
                ('shim_front', shim, False, (0, 0, 30)), ('shim_rear', shim, False, (0, 0, -7.8))]:
            m.add(low+'_'+name, p, origin, fr, 'gear_'+moving_group, axis_mount=True, rotates=rotates, initial_s=initial, raw_offset=offset)
        for off in (-9, 9):
            for label, p in [('gear_bolt', screw3), ('gear_nut', nut3)]:
                m.add(f'{low}_{label}_{off}', p, origin, fr, 'gear_'+moving_group, axis_mount=True, rotates=True,
                      initial_s=initial, raw_offset=(off, 0, 0))

    m.add('tower_foot', tower_foot, (0, -310, 0), group='x')
    m.add('y_mount_left', mount, (-20, -255, 180), group='z')
    # Mirrored bracket retains its normal +Y; mirror its local X only.
    right_mount = m.part('P26', 'Y台连接角座_右', mount.shape.mirror('YZ'), notes=mount.notes,
        features=['P12关于YZ平面镜像；托面孔X+3,Y30；其余尺寸同P12。'])
    m.add('y_mount_right', right_mount, (20, -255, 180), group='z')
    for side in (-1, 1):
        for yy in (-128, -28):
            m.add(f'carrier_pillar_{side}_{yy}', pillar, (side*70, yy, 171), 'I' if side > 0 else 'R', 'z')
    m.add('carrier_tray', tray, (0, -78, 246), group='z')
    m.add('manual_head', head, (0, -206.5, DECK), group='y')
    pickup = m.part('H07', 'M4x80手动牵引销', fuse(cyl(0, 0, 6, 2, 80), cyl(0, 0, 86, 3.5, 4)), process='buy')
    m.add('pickup_pin', pickup, (0, -146, DECK), group='pin')
    m.add('pickup_handle', pull, (0, -146, DECK+82), group='pin')
    m.add('bin', bin_part, (0, -78, DECK), group='bin')

    for side in (-1, 1):
        for j, p in enumerate(links):
            m.add(f'floor_{side}_{j}', p, (side*110, (-280, -120, 60)[j], -6))
        for yy in (-190, -50):
            m.add(f'splice_{side}_{yy}', splice, (side*110, yy, 0))
    for yy in (10, 140):
        m.add(f'floor_cross_{yy}', cross, (0, yy, 0))
        for xx in (-76, 76):
            m.add(f'stand_leg_{xx}_{yy}', leg, (xx, yy, 6))
    m.add('stand_frame', stand, (0, 0, 240))
    m.add('cell', cell, (0, 65, 246))
    lockpin = m.part('H08', 'M4x70手动Z锁销', fuse(cyl(0, -66, -5, 2, 70), cyl(0, -66, 65, 3.5, 4)), process='buy')
    m.add('z_lock_pin', lockpin, (0, -310, 180), 'Z', 'lock')
    m.add('z_lock_washer', washer, (0, -310, 180), 'Z', 'lock', raw_offset=(0, -66, -1))
    m.add('z_lock_nut', nut4, (0, -310, 180), 'Z', 'lock', raw_offset=(0, -66, -4.2))

    # Fit coupons are separate printable files, not fake assembly components.
    m.part('C01', '导向试块_轨', fuse(box(0, 0, 0, 50, 30, 6), rail_profile(50, 0)),
        ['先打印；测试轨不装到整机。'], ['长50，底宽30；截面与正式导向一致。'])
    for code, gap in [('C02', .2), ('C03', .35), ('C04', .5)]:
        s = box(0, 0, 6+gap, 20, 25, 21-6-gap).cut(guide_void(22, 0, gap))
        m.part(code, '导向试块_滑块_'+str(gap), s,
            ['从端部套入C01；正式滑台名义间隙0.35。'], [f'长20，外宽25；截面间隙参数c={gap}。'], print_axis='X')

    for spec, count, use in [
        ('M3x16 内六角螺钉', 50, '齿条24、立柱底脚4、立柱背板4、Y角座立面4/托面2、承托支柱8、取放头4'),
        ('M3x25 内六角螺钉', 12, '三轴端挡，各轴4'),
        ('M3x20 内六角螺钉', 6, '三轴齿轮与手轮，各2；已建模'),
        ('M3x12 内六角螺钉', 32, 'X底座4、库位脚16、前横梁8、库位柱顶4'),
        ('M3x10 内六角螺钉', 16, '底架拼接板；不能改成长螺钉顶住工作台'),
        ('M3 六角螺母，AF5.5，厚2.4', 116, '配上述M3连接；螺母窝名义深2.6，不可换厚螺母强压'),
        ('M4x16 90度沉头螺钉，头径≤9', 8, '移动托盘4、库位托板4；必须沉平'),
        ('M4 六角螺母，AF7', 8, '承托盘与库位托板'),
        ('M4x60 内六角螺钉', 3, '手动齿轮轴，已建模'),
        ('Ø6外径/Ø4.2内径 金属光滑隔套 L40±0.1', 3, '齿轮轴承面；不能用螺纹直接磨打印孔'),
        ('M4平垫圈，OD≤9，厚1', 7, '三轴轴端6、Z锁销1'),
        ('M4普通六角螺母，AF7，厚3.2', 6, '每根手轮轴两颗对锁，不能把轴向转动件夹死；已建模'),
        ('M4x70 半牙螺钉 + M4手拧保持螺母', 1, 'Z定位锁销；保持螺母只防脱，不预紧弯曲锁耳'),
        ('M4x80 半牙螺钉', 1, '手动牵引销；去毛刺倒钝端部，导向处优先光杆'),
        ('工作台夹具', 4, '前后夹紧底架；未夹紧禁止升Z')]:
        m.buy(spec, count, use)
    return m


def print_shape(p):
    s = p.shape
    if p.print_axis == 'X':
        s = s.rotate((0, 0, 0), (0, 1, 0), -90)
    b = s.BoundingBox()
    return s.translate((-b.xmin, -b.ymin, -b.zmin))


def export(m):
    for sub in ('parts', 'stl', 'drawings', 'previews'):
        (OUT/sub).mkdir(parents=True, exist_ok=True)
    assembly = cq.Assembly(name='MANUAL_XYZ_EMPTY_BIN_ONLY')
    for i in m.items:
        colour = (.25, .28, .32) if i.part.process == 'buy' else (.18, .56, .68)
        if i.name.startswith('z_lock'):
            colour = (.95, .55, .1)
        assembly.add(i.located(), name=i.name, color=cq.Color(*colour))
    assembly.save(str(OUT/'Manual_3Axis_Assembly.step'))
    rows = []
    for p in m.parts.values():
        cq.exporters.export(p.shape, str(OUT/'parts'/(p.code+'.step')))
        row = {'code': p.code, 'name': p.name, 'quantity': sum(i.part.code == p.code for i in m.items),
               'process': p.process, 'volume_mm3': p.shape.Volume(), 'notes': p.notes, 'features': p.features}
        b = p.shape.BoundingBox()
        row['local_bounds_mm'] = kit.bbox(p.shape)
        row['extents_mm'] = [b.xlen, b.ylen, b.zlen]
        if p.process == 'print':
            s = print_shape(p)
            cq.exporters.export(s, str(OUT/'stl'/(p.code+'.stl')), tolerance=.03, angularTolerance=.1)
            b = s.BoundingBox()
            row['print_extents_mm'] = [b.xlen, b.ylen, b.zlen]
            row['print_orientation'] = 'X end on bed' if p.print_axis == 'X' else 'local Z bottom on bed'
            if p.code.startswith('C'):
                row['quantity'] = 1
        rows.append(row)
    manifest = {'fingerprint': FINGERPRINT, 'units': 'mm', 'parts': rows,
                'instances': [dict(name=i.name, code=i.part.code, origin=i.origin, frame=i.frame, group=i.group,
                                   axis_mount=i.axis_mount, rotates=i.rotates, initial_s=i.initial_s, raw_offset=i.raw_offset) for i in m.items],
                'motion_limits_mm': {'X': [-50, 50], 'Z': [-40, 40], 'Y': [0, 143]},
                'deck_mm': DECK, 'z_lock_positions_mm': Z_LOCKS, 'hardware': m.hardware,
                'motors_included': False, 'payload_allowed_kg': 0, 'hardware_accepted': False,
                'loaded_operation_allowed': False, 'continuous_collision_detection': False,
                'note': 'Manual empty-bin fit prototype. Not a scale structural certification or replacement for the V03.1 metal machine.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    with (OUT/'打印清单.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['编号', '名称', '数量', '打印文件', '打印朝向', '备注'])
        for r in rows:
            if r['process'] == 'print':
                w.writerow([r['code'], r['name'], r['quantity'], r['code']+'.stl', r['print_orientation'], '；'.join(r['notes'])])
    with (OUT/'五金清单.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['规格', '数量', '用途'])
        for r in m.hardware:
            w.writerow([r['specification'], r['quantity'], r['purpose']])
    print('EXPORTED', len(m.parts), 'part types,', len(m.items), 'instances', flush=True)


if __name__ == '__main__':
    export(build())
