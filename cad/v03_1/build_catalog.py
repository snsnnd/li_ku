"""Build the V03.1 illustrated catalog page from the CAD manifest."""
from __future__ import annotations

import html
import json
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'model' / 'V03_1'
OUT = MODEL / 'drawings'

MANIFEST = json.loads((MODEL / 'manifest.json').read_text(encoding='utf-8'))
PARTS = {p['name']: p for p in MANIFEST['parts']}
INSTANCES = MANIFEST['instances']
CONNECTIONS = MANIFEST['connections']

CN = {
    # A 底板
    'Base_Panel_0_Located_R1_R1_R1': ('底板 0（左段）', '320×590×6 铝板，带定位与接收孔'),
    'Base_Panel_1_Located_R1': ('底板 1（中段）', '420×590×6 铝板'),
    'Base_Panel_2_Located_R1_R1': ('底板 2（右段）', '510×590×6 铝板'),
    'Base_Splice_60x40': ('底板拼接板', '跨越接缝，4×M5 固定两块底板'),
    # B 货架
    '2020_Rack_Z650': ('2020 铝型材立柱', 'L650，每列 4 根，共 16 根'),
    'Rack_M1p5_24T_X': ('X 向齿条段', 'M1.5 / 20°，24 齿距 = 113.097 mm，共 9 段'),
    'X_Rack_Backbone_R1': ('X 齿条背板', '1040×6×30，齿条安装面连续'),
    'X_Rack_Bolted_Adjustable_Foot': ('X 齿条 L 形支脚', '4×M4 接背板、4 个 M5 长孔接底板，±1 mm 调整'),
    'X_Datum_Bar_1050': ('X 导轨基准条', '1050 长金属基准，M3 导轨螺纹、M5 沉头固定'),
    'X_Stop_Low_Profile': ('X 行程限位块', '低轮廓橡胶缓冲，共 4 个'),
    'Column_Foot_28x40': ('立柱脚板', '28×40×6，落到 X 滑板台面'),
    'Column_Pedestal_28x40': ('立柱脚座', '28×40×14，与脚板配对'),
    'Column_Carrier_RoundSlot': ('立柱连接座', '圆孔 + 腰形槽，吸收装配误差'),
    'Column_Rear_Panel_170x630': ('列后板', '170×630×3，封闭列背'),
    'Column_Datum_Pin_D6': ('立柱定位销', 'Ø6，圆孔 + 菱形槽各一'),
    'Column_Reference_Tag_Mount': ('列基准标签座', '固定列基准 AprilTag'),
    'Shelf_Angle_1': ('层板托角（右）', '20×150×23，M5 进型材槽、M4 接层板'),
    'Shelf_Angle_-1': ('层板托角（左）', '与右件镜像，共 40 件'),
    'Cell_124x130': ('库位隔板', '124×130×10 PETG，20 个库位'),
    'Rear_Panel_Standoff_2': ('后板垫块', '10×2×10，后板与型材之间'),
    'Bin_V03_Marker_Rails': ('料盒（带标识导轨）', '110×136×60，前左留 32 mm 标签位'),
    'Marker_Card_32mm': ('AprilTag 标识卡', '32 mm 外框，黑边 25.6 mm，ID 不作为安全信号'),
    # C X 轴
    'MGN12_X1050': ('X 直线导轨', 'MGN12，L1050，共 2 根'),
    'MGN12H_X': ('X 导轨滑块', 'MGN12H，每根 2 个'),
    'X_Carriage_160x110x8': ('X 滑板', '160×110×8，承载 Z 立柱'),
    'X_Motor_Leg': ('X 电机支脚', '电机外置悬臂支架'),
    'Pinion_M1p5_20T_X': ('X 小齿轮', 'M1.5 / 20 齿，打印件，必须配金属夹紧轮毂'),
    'Metal_Pinion_Hub_X': ('X 金属夹紧轮毂', '候选件，夹紧方式与扭矩未验证'),
    'ZDT_RealMotor_X': ('X 步进电机', '用户提供的参考模型，仅几何'),
    'X_Power_Module_Tray': ('X 电源模块托板', '212×90×4'),
    'Local_Power_Case': ('本地电源盒', '电池仓 + 独立 ESP32 仓'),
    'Local_Power_Lid': ('电源盒盖', '与电源盒配对'),
    'Battery_Candidate_85x65x42': ('电池包（候选）', '仅包络尺寸，电芯/电压/BMS 未定'),
    'ESP32_Controller_Candidate': ('ESP32 控制板（候选）', '仅板级包络'),
    # D Z 轴
    '3030_Z600': ('3030 铝型材立柱', 'L600，升降立柱，共 2 根'),
    'Z_Foot_Angle_30x20x32': ('Z 立柱底角（后）', 'M6 进槽螺母，M6×12 接 X 滑板'),
    'Z_Foot_Angle_Front': ('Z 立柱底角（前）', '与后底角配对，共 4 件'),
    'Z_Top_Motor_Plate_130x60x8': ('Z 顶电机板', '130×60×8，封顶并固定电机模块'),
    'MGN12_Rail_Z500': ('Z 直线导轨', 'MGN12，L500，共 2 根'),
    'MGN12H_Z': ('Z 导轨滑块', 'MGN12H，共 4 个'),
    'Z_Rail_Datum_20x4x500': ('Z 导轨基准条', '20×4×500，5 颗沉头 M5 进槽螺母'),
    'Z_Carriage_130x100x8_R1': ('Z 滑板', '130×100×8，承载 Y 模组'),
    'Z_Rack_Backbone_12x30': ('Z 齿条背板', '12×30×566，由 4 mm 加厚到 12 mm'),
    'Z_Rack_Support_104x8x12': ('Z 齿条支撑', '104×8×12，2×M3 接背板、1×M5 进 3030 后槽'),
    'Rack_M1p5_24T_Z': ('Z 向齿条段', '共 5 段，节距与 X/Y 相同'),
    'Pinion_M1p5_20T_Z': ('Z 小齿轮', '打印件，不得作为制动或防坠'),
    'Metal_Pinion_Hub_Z': ('Z 金属夹紧轮毂', '候选件'),
    'Z_Motor_Plate': ('Z 电机板', '50×4×50'),
    'Z_Motor_Module_Link': ('Z 电机模块连接板', '19×26×6'),
    'Z_Power_Module_Tray': ('Z 电源模块托板', '165×94×16'),
    'Z_Reduction_10to1_CANDIDATE': ('Z 行星减速 10:1（候选）', 'OD42 / L45，未选型'),
    'Z_Reducer_Output_Shaft_CANDIDATE': ('Z 减速输出轴（候选）', 'Ø8 输出，露出 28 mm'),
    'Z_Stop_Rear_Clearance': ('Z 后侧限位块', '橡胶，共 4 个'),
    'Independent_Steel_Safety_Track': ('独立钢制安全轨', '6×30×566，与打印齿条分离'),
    'Safety_Track_Link': ('安全轨连接块', '27×20×12，共 2 件'),
    'NC_Rail_Brake_CANDIDATE': ('常闭导轨制动器（候选）', '仅为外形包络，未建模钳口'),
    'Brake_Module_Link': ('制动模块连接板', '7×25×8'),
    'ZDT_RealMotor_Z': ('Z 步进电机', '用户参考模型'),
    'Camera_CANDIDATE_32x32': ('相机（候选）', '32×18×32，内参/外参未标定'),
    'Camera_Slotted_Mount': ('相机可调支架', '腰形孔调焦，线缆/天线避让待确认'),
    'Y_Power_Tray_On_Z': ('Y 电源托板（固定在 Z）', '90×165×4，随 Z 不随 Y'),
    'Y_Power_Z_Support': ('Y 电源 Z 支架', '阶梯金属支架，2×M4 接 Z 滑板'),
    'Local_Power_Case_Y_Stationary_Rotated': ('Y 本地电源盒（转 90°）', '仍属 Z 节点，需 143 mm 柔性线束'),
    'Local_Power_Lid_Y_Stationary_Rotated': ('Y 电源盒盖（转 90°）', '与转 90° 盒体配对'),
    'Battery_Candidate_85x65x42_Y_Stationary_Rotated': ('Y 电池包（候选，转 90°）', '仅包络'),
    'ESP32_Controller_Candidate_Y_Stationary_Rotated': ('Y 控制板（候选，转 90°）', '仅板级包络'),
    # E Y 轴
    'Y_Spine_TwinGuide': ('Y 双导轨脊板', '82×211×6 金属脊板'),
    'Y_Spine_Metal_Spacer_Left': ('脊板金属垫块', '26×20×11，共 2 件'),
    'MGN9_Rail_Y200': ('Y 直线导轨', 'MGN9，L200，共 2 根'),
    'MGN9H_Y': ('Y 导轨滑块', 'MGN9H，共 2 个'),
    'Y_Module_Base_Short': ('Y 模组底板', '148×60×13，由 X+256 缩短到 X+120'),
    'Y_Motor_Leg': ('Y 电机外支脚', '让开小齿轮全周扫掠'),
    'Motor_Plate_50x50': ('电机转接板', '50×50×4，31×31 M3 孔阵'),
    'Y_Reduction_3to1_CANDIDATE': ('Y 行星减速 3:1（候选）', 'OD42 / L35，未选型'),
    'Y_Reducer_Output_CANDIDATE': ('Y 减速输出轴（候选）', 'Ø8 输出'),
    'Y_Rack_Backbone_R1': ('Y 齿条背板', '4×227×30'),
    'Rack_M1p5_24T_Y': ('Y 向齿条段', '共 2 段，与 X/Z 同相位'),
    'Y_Rack_Tube_Saddle': ('Y 齿条组合鞍座', '同时压脊板、托方管、托齿条背板'),
    'Pinion_M1p5_20T_Y': ('Y 小齿轮', '打印件 + 金属轮毂'),
    'Metal_Pinion_Hub_Y': ('Y 金属夹紧轮毂', '候选件'),
    'Y_Stop_24x4x10': ('Y 限位块', '橡胶，共 2 个'),
    'Tray_Tube_V03': ('取放方管', '25×214×25，薄壁需金属压套'),
    'Tube_End_Plug_V03': ('方管端塞', '21×30×21'),
    'Carrier_Tray_124x130': ('取放托盘', '124×130×10，前开 40 mm 桅杆槽'),
    'Latch_Mast_V03_RoundSlot': ('锁销桅杆', '36×16×92，圆孔 + 腰槽可拆头接口'),
    'Head_Locator_D3': ('取放头定位块', 'Ø3，共 2 件'),
    'Pin_Guide_Cheek': ('销导向颊板', '26×24×4，需铰到衬套配合'),
    'Pin_Flanged_Bushing_4p1x6': ('法兰衬套', 'Ø4.1 内径，可更换青铜衬套'),
    'Latch_Pin_D4x60': ('锁销', 'Ø4×60 磨制钢销，提升 14 mm'),
    'Latch_Scotch_Yoke': ('Scotch 轭', 'R7 曲柄驱动，行程 14 mm'),
    'Latch_Crank_R7': ('锁销曲柄', 'R7，需配合舵机金属花键'),
    'Latch_Roller_D3': ('锁销滚轮', 'Ø3 磨制销 + 挡圈'),
    'Pin_Collar_4x10x5': ('销卡箍', 'Ø10×5，共 2 个'),
    'Roller_Clip_Envelope': ('滚轮挡圈', 'DIN6799，共 2 个'),
    'Latch_Return_Spring_Envelope': ('回位弹簧', '外径 7 / 线径 0.3 / 自由长 19，0.2–1.2 N'),
    'MG90S_Envelope': ('MG90S 舵机', '需实测输出轴与 ≥150° 行程'),
    'Servo_Cradle': ('舵机座', '2×M3 接金属桅杆'),
    'Servo_Cradle_Lid': ('舵机压盖', '独立夹紧盖'),
    'Servo_Horn_Interface_Envelope': ('舵机摇臂接口', '必须匹配实际舵机花键'),
    'ZDT_RealMotor_Y': ('Y 步进电机', '用户参考模型'),
    # F IO
    'IO_Flanged_Leg_BaseToFrame': ('IO 法兰支腿', '40×40×184，4×M5 到底板、1×M5 到框架'),
    'IO_Frame_Matched_Fasteners': ('IO 金属框架', '150×150×6，与支腿/托板孔位对应'),
    'IO_Deck': ('IO 料盒托板', '124×130×10，单箱交换位'),
    'IO_Inner_Shutter': ('内闸门', '手动原型门，开度 +90 mm，未做联锁'),
    'IO_Shutter_Guide_Left': ('内闸门导轨（左）', '8×8×204'),
    'IO_Shutter_Guide_Right': ('内闸门导轨（右）', '8×8×204'),
    'IO_Shutter_Header': ('内闸门横梁', '260×19×4'),
    'IO_Outer_Door': ('外门', '左侧铰接，内外门不得同时开放'),
    'IO_Access_Tunnel_Horizontal': ('人工取放通道板（水平）', '114×138×3，共 2 件'),
    'IO_Access_Tunnel_Side': ('人工取放通道板（侧）', '114×3×106，共 2 件'),
    'IO_Roof': ('IO 顶板', '260×153×3'),
    'IO_Rear_Wall': ('IO 后板', '170×3×198'),
    'IO_Right_Wall': ('IO 右板', '3×154×198'),
    'IO_Left_Upper_Wall': ('IO 左上板', '3×150×104'),
    'IO_Upper_Fixed_Shield': ('IO 上固定挡板', '与关闭的内门重叠 4 mm'),
    'IO_Lower_Fixed_Shield': ('IO 下固定挡板', '170×3×8'),
    'IO_External_Reference_Card': ('IO 外部基准卡', 'AprilTag ID200，贴在左外侧，不是料盒 ID'),
    'IO_Box_Back_Stop': ('料盒后挡', '110×3×8'),
    'Box_Presence_Sensor_CANDIDATE': ('料盒在位传感器（候选）', '12×12×20 包络'),
    # G 防护
    'Guard_Post_740': ('防护立柱', '20×20×740，共 4 根'),
    'Guard_Cross_1200': ('防护横梁', '1200×20×20，共 2 根'),
    'Guard_Side_520': ('防护侧梁', '20×520×20，共 2 根'),
    'Guard_Panel_X-351.5': ('防护板（X−）', '3×590×766'),
    'Guard_Panel_X901.5': ('防护板（X+）', '3×590×766'),
    'Guard_Panel_Y-371.5': ('防护板（Y−）', '1250×3×766'),
    'Guard_Panel_Y221.5': ('防护板（Y+）', '1250×3×766'),
    'Guard_Roof': ('防护顶板', '1256×596×3'),
}

MODULES = [
    ('A_base', 'A · 底板与基础', '整机落地的第一层：三块 6 mm 铝板拼成连续台面，拼接板跨缝锁固，四角留 Ø8.5 锚固孔。'),
    ('B_rack', 'B · 立体货架', '4 列 × 5 层、共 20 个库位。型材立柱 + 层板托角 + PETG 库位隔板；X 齿条与基准条在这一层完成校直。'),
    ('C_x', 'C · X 行走模组', '两根 MGN12-1050 导轨承载 160×110×8 滑板，X 电机经 20T 小齿轮驱动 9 段齿条；本地电源节点随 X 移动。'),
    ('D_z', 'D · Z 升降模组', '两根 3030 立柱与 MGN12-500 导轨构成升降轴，12 mm 齿条背板 + 5 个支撑；独立钢安全轨与候选制动器只作包络。'),
    ('E_y', 'E · Y 伸缩取放头', 'Y 脊板双 MGN9 导轨 + 缩短悬臂，方管托盘伸入库位；锁销由 MG90S 经 R7 曲柄与 Scotch 轭提升 14 mm。'),
    ('F_io', 'F · IO 工位', '底板落地的法兰支腿 + 金属框架，单箱交换位由内闸门与外门双重遮挡，外部基准卡 ID200 供视觉定位。'),
    ('G_guard', 'G · 外防护', '4 根立柱 + 横梁/侧梁 + 四周板与顶板。预览隐藏防护板不代表运行时可拆除。'),
]

MODULE_ORDER = [m[0] for m in MODULES]

STEP_TEXT = [
    ('底板与拼接', [
        '按 0 → 1 → 2 顺序摆三块底板，接缝对齐；4 块 60×40 拼接板跨越接缝，各 4×M5 锁固。',
        '台面必须落在平整、连续支撑的专用工作台上，不能只垫四角；底板预留 4 个 Ø8.5 锚固孔，锚固件尚未选型。',
        '复核台面平面度后再进入货架安装，后续所有垂直度都以这一步为基准。',
    ]),
    ('货架与 X 齿条', [
        '每列先装脚板（28×40×6）与脚座（28×40×14），再立柱（2020×650），顶部用连接座收口，背面装 170×630 后板。',
        '层板托角逐层安装：M5 进型材槽螺母，M4 接层板/库位；20 个 PETG 库位隔板从上方落入。',
        'X 齿条背板先与 7 个 L 形支脚各 4×M4 连接，支脚再以 4 个 M5 长孔落到底板；X=390 的支脚同时跨两块底板。',
        '整条齿条以基准条校直后统一锁紧，禁止逐段独立调整；9 段齿条按同一相位装入背板。',
    ]),
    ('X 行走模组', [
        '在 X 基准条上装 2 根 MGN12-1050（M3 螺纹 + 沉头 M5 固定），每根 2 个 MGN12H 滑块。',
        'X 滑板（160×110×8）落到 4 个滑块上，手动全程推行确认无卡滞。',
        'X 电机经 50×50 转接板固定，20T 小齿轮与齿条对中；金属夹紧轮毂为候选件，啮合背隙须用试块确认。',
        'X 电源托板、电源盒、电池包与 ESP32 装在滑板上，线束留出全行程弯曲余量。',
    ]),
    ('Z 升降模组', [
        '两根 3030×600 立柱先装前后底角（M6 进槽螺母 + M6×12 接 X 滑板），顶部用 130×60×8 电机板封顶。',
        '装 2 根 MGN12-500 导轨与 4 个滑块，Z 滑板（130×100×8）落座。',
        '12 mm 齿条背板先与 5 个支撑（104×8×12）各 2×M3 连接，支撑再以 1×M5 进 3030 后槽；支撑间距 ≤135 mm。',
        '装 5 段 Z 齿条、Z 电机 + 10:1 减速 + Ø8 输出轴；独立钢安全轨与 2 个连接块单独安装，不依赖打印齿条。',
        'Y 电源托板经阶梯支架固定在 Z 滑板右侧，不接 Y 滑块；Y 电源盒转 90° 安装，留 143 mm 柔性线束。',
    ]),
    ('Y 伸缩取放头', [
        'Y 脊板（82×211×6）经 2 块金属垫块装到 Z 滑板，装 2 根 MGN9-200 与 2 个滑块，再上 Y 底板（148×60×13）。',
        'Y 电机 + 3:1 减速 + 小齿轮装在底板电机孔位；Y 齿条背板经 2 个组合鞍座同时压脊板、托方管、夹背板。',
        '两根 25×214 方管与端塞装到脊板，托盘（124×130）落在方管上；方管紧固必须用金属压套，不能靠螺钉压瘪薄壁。',
        '锁销机构：桅杆 → 上下导向颊板与法兰衬套 → Ø4×60 销 → Scotch 轭 + 2 个卡箍 → R7 曲柄 → MG90S 舵机座与压盖。',
        '回位弹簧、Ø3 滚轮与挡圈最后装；先在台架上手动验证 14 mm 全行程与自回位，再装托盘。',
    ]),
    ('IO 工位', [
        '4 条法兰支腿落到底板，每条 4×M5；金属框架坐到腿顶，每条 1×M5；打印托板 4×M4 与框架孔位对应。',
        '装内闸门左右导轨与横梁，内闸门从上方滑入；外门左侧铰接，内外门不得同时开放。',
        '装人工取放通道板、顶/后/右/左上板与上下固定挡板；上挡板与关闭的内门重叠 4 mm。',
        '装料盒后挡与在位传感器（候选），外部基准卡 ID200 贴在左外侧护板，不与料盒 ID 混用。',
    ]),
    ('外防护', [
        '4 根 740 立柱按底板孔位站立，装 2 根 1200 横梁与 2 根 520 侧梁。',
        '四周防护板与顶板逐块固定；确认内门开度 +90 mm、外门铰链不干涉线束。',
        '防护板为运行必需件；预览图中隐藏只为看清内部结构，不代表可以拆除运行。',
    ]),
    ('接线、标定与空载调试', [
        '三个本地电源节点：X 随 X 滑板、Z 随 Z 滑板、Y 固定在 Z 平台。Y 节点与取放头之间必须留 143 mm 行程的柔性线束。',
        '装相机与标定板：先做相机内参，再做工具/列基准外参；库位标签 32 mm 只用于位姿，不作为安全信号。',
        '接限位、急停与门信号；先断电手动全行程走查，再空载低速点动，最后才讨论逐级加载。',
        'Z 打印齿、候选减速器、金属轮毂与独立防坠均未验收，禁止直接带载自动运行。',
    ]),
]

KIND_CN = {
    'bolted_face': '端面螺接',
    'bolted_seat': '座面螺接',
    'slot_nut_face': '型材槽螺母',
    'bolted_saddle': '鞍座抱紧 + 侧向螺接',
}

PROCESS_CN = {'purchased': '采购', 'machined': '加工', 'print': '打印', 'cut_panel': '切割',
              'candidate': '候选', 'print_paper': '打印纸质', 'safety': '安全件'}
MATERIAL_CN = {'aluminum': '铝', 'steel': '钢', 'PETG': 'PETG', 'purchased': '采购件',
               'guard': '防护板', 'rubber': '橡胶', 'safety': '安全件'}


def module_of_part(name: str) -> str:
    n = name
    if n.startswith('Base_Panel') or n.startswith('Base_Splice'):
        return 'A_base'
    if n.startswith('Guard_'):
        return 'G_guard'
    if n.startswith('IO_') or n.startswith('Box_Presence'):
        return 'F_io'
    if n.startswith(('Shelf_Angle', 'Cell_', 'Bin_V03', 'Marker_Card', 'Column_', '2020_Rack',
                     'Rear_Panel_Standoff', 'X_Rack_Backbone', 'Rack_M1p5_24T_X',
                     'X_Rack_Bolted_Adjustable_Foot', 'X_Datum_Bar', 'X_Stop_Low_Profile')):
        return 'B_rack'
    if n.startswith(('MGN12_X1050', 'MGN12H_X', 'X_Carriage', 'X_Motor_Leg', 'X_Power_Module',
                     'Pinion_M1p5_20T_X', 'Metal_Pinion_Hub_X', 'ZDT_RealMotor_X')):
        return 'C_x'
    if n.startswith(('3030_Z600', 'Z_Foot_Angle', 'Z_Top_Motor_Plate', 'MGN12_Rail_Z500',
                     'MGN12H_Z', 'Z_Rail_Datum', 'Z_Carriage', 'Z_Rack_', 'Rack_M1p5_24T_Z',
                     'Pinion_M1p5_20T_Z', 'Metal_Pinion_Hub_Z', 'Z_Motor_', 'Z_Power_',
                     'Z_Reduction', 'Z_Reducer_', 'Z_Stop_', 'Independent_Steel_Safety_Track',
                     'Safety_Track_Link', 'NC_Rail_Brake', 'Brake_Module_Link', 'ZDT_RealMotor_Z',
                     'Camera_', 'Y_Power_', 'Local_Power_Case_Y', 'Local_Power_Lid_Y',
                     'Battery_Candidate_85x65x42_Y', 'ESP32_Controller_Candidate_Y')):
        return 'D_z'
    if n.startswith(('Y_Spine', 'MGN9', 'Y_Module_Base', 'Y_Motor_Leg', 'Motor_Plate_50x50',
                     'Y_Reduction', 'Y_Reducer_', 'Y_Rack_Backbone', 'Rack_M1p5_24T_Y',
                     'Y_Rack_Tube_Saddle', 'Pinion_M1p5_20T_Y', 'Metal_Pinion_Hub_Y',
                     'Y_Stop_24x4x10', 'Tray_Tube', 'Tube_End_Plug', 'Carrier_Tray',
                     'Latch_', 'Head_Locator', 'Pin_Guide_', 'Pin_Flanged_',
                     'Pin_Collar', 'Roller_Clip', 'MG90S_', 'Servo_', 'ZDT_RealMotor_Y')):
        return 'E_y'
    if n.startswith(('Local_Power_', 'Battery_Candidate', 'ESP32_Controller')):
        return 'C_x'
    raise KeyError(n)


def esc(s):
    return html.escape(str(s), quote=True)


def fmt_dims(e):
    return '×'.join(f'{v:.0f}' if abs(v - round(v)) < 0.05 else f'{v:.1f}' for v in e)


def build():
    part_module = {name: module_of_part(name) for name in PARTS}
    inst_by_part = Counter(i['part'] for i in INSTANCES)
    module_parts = OrderedDict((m, []) for m in MODULE_ORDER)
    for name in sorted(PARTS, key=lambda n: (MODULE_ORDER.index(part_module[n]), n)):
        module_parts[part_module[name]].append(name)

    # module instance counts
    def mod_of_inst(i):
        n = i['name']
        if n.startswith('x_motor_plate'):
            return 'C_x'
        if n.startswith('y_motor_plate'):
            return 'E_y'
        if n.startswith(('x_power', 'x_battery', 'x_esp32')):
            return 'C_x'
        if n.startswith(('z_power', 'z_battery', 'z_esp32', 'y_power', 'y_battery', 'y_esp32')):
            return 'D_z'
        return part_module[i['part']]

    inst_count = Counter(mod_of_inst(i) for i in INSTANCES)

    css = '''
:root{--paper:#f7f6f2;--card:#ffffff;--ink:#1d2328;--muted:#6d7882;--line:#ddd9d0;
--accent:#0e6f68;--accent2:#b4641c;--soft:#eef2f1}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.7 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
code,.mono{font-family:"Cascadia Mono","Consolas","SFMono-Regular",monospace}
.side{position:fixed;inset:0 auto 0 0;width:224px;padding:30px 22px;background:#fbfaf7;
border-right:1px solid var(--line);overflow:auto}
.brand{font-weight:700;letter-spacing:.14em;font-size:11px;color:var(--muted)}
.brand b{display:block;font-size:17px;letter-spacing:.02em;color:var(--ink);margin-top:6px}
.side nav{margin-top:26px;display:grid;gap:2px}
.side a{color:#3d474f;text-decoration:none;font-size:13.5px;padding:7px 10px;border-radius:6px}
.side a:hover{background:var(--soft);color:var(--accent)}
.side a.sub{padding-left:22px;font-size:12.5px;color:var(--muted)}
.side .rule{height:1px;background:var(--line);margin:18px 0}
main{margin-left:224px;padding:44px 48px 90px;max-width:1500px}
.hero .kicker{font-size:11px;letter-spacing:.22em;color:var(--accent);font-weight:700}
h1{font-size:40px;line-height:1.15;margin:10px 0 12px;letter-spacing:-.01em}
.lede{max-width:760px;color:#46525b;font-size:16px;margin:0}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 12px;font-size:12.5px;color:#43505a}
.chip b{color:var(--accent)}
.hero fig{margin:26px 0 0}
.hero img{width:100%;border:1px solid var(--line);border-radius:12px;background:#fff}
figcaption{font-size:12px;color:var(--muted);margin-top:8px}
h2{font-size:23px;margin:64px 0 6px;letter-spacing:-.01em}
h2 .num{color:var(--accent);font-weight:700;margin-right:10px;font-size:14px;letter-spacing:.1em}
.sub{color:var(--muted);margin:0 0 22px;font-size:13.5px}
.specs{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:22px}
.spec{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.spec b{display:block;font-size:22px;letter-spacing:-.01em}
.spec span{font-size:12px;color:var(--muted)}
.modgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.modcard{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.modcard img{width:100%;aspect-ratio:3/2;object-fit:contain;background:#fff;border-bottom:1px solid var(--line);cursor:zoom-in}
.modcard .mb{padding:14px 16px 16px}
.modcard h3{margin:0 0 6px;font-size:16px}
.modcard p{margin:0;font-size:12.8px;color:var(--muted);line-height:1.6}
.modcard .count{margin-top:10px;font-size:11.5px;color:var(--accent);letter-spacing:.04em}
.tools{position:sticky;top:0;z-index:5;background:rgba(247,246,242,.94);backdrop-filter:blur(6px);
padding:14px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;margin-top:20px}
.tools input{flex:1;max-width:420px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;
background:#fff;font:inherit;font-size:13.5px;outline:none}
.tools input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(14,111,104,.10)}
.tools span{font-size:12px;color:var(--muted)}
.modsect{margin-top:38px}
.modsect h3{font-size:17px;margin:0 0 4px}
.modsect .mdesc{font-size:13px;color:var(--muted);margin:0 0 16px}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(224px,1fr));gap:14px}
.part{background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.part figure{margin:0;background:#fff;border-bottom:1px solid #efede7}
.part img{width:100%;aspect-ratio:9/7;object-fit:contain;display:block;cursor:zoom-in}
.pbody{padding:11px 12px 13px;display:flex;flex-direction:column;gap:5px}
.pname{font-size:13.6px;font-weight:600;line-height:1.35;display:flex;justify-content:space-between;gap:8px}
.pname i{font-style:normal;color:var(--accent);font-weight:600;font-size:12px;white-space:nowrap}
.pcode{font-size:10.5px;color:#8a949c;word-break:break-all;line-height:1.3}
.meta{display:flex;flex-wrap:wrap;gap:5px;align-items:center;font-size:11px;color:var(--muted)}
.badge{border-radius:4px;padding:1px 6px;font-size:10.5px;background:#eef2f1;color:#36605d}
.badge.print{background:#e6f3f4;color:#1d6d75}
.badge.machined{background:#eef0f4;color:#44536a}
.badge.purchased{background:#f0efec;color:#6b6257}
.badge.candidate{background:#fdf0e2;color:#a2570f}
.badge.safety{background:#fbe9e6;color:#a33a2c}
.badge.guard{background:#eef2f5;color:#4c6172}
.badge.cut_panel{background:#efefec;color:#5f5d55}
.badge.print_paper{background:#f4f1ea;color:#6d6455}
.pnote{font-size:11.3px;color:#7a858e;line-height:1.5;margin:2px 0 0}
.steps{display:grid;gap:18px;margin-top:26px}
.step{display:grid;grid-template-columns:minmax(280px,44%) 1fr;background:#fff;border:1px solid var(--line);
border-radius:12px;overflow:hidden}
.step img{width:100%;height:100%;object-fit:contain;background:#fff;border-right:1px solid var(--line);cursor:zoom-in}
.steptext{padding:20px 24px}
.stepno{font-size:11px;letter-spacing:.2em;color:var(--accent);font-weight:700}
.steptext h3{margin:4px 0 10px;font-size:18px}
.steptext ul{margin:0;padding-left:18px;display:grid;gap:6px}
.steptext li{font-size:13.2px;color:#46525b}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;font-size:12.6px;border-bottom:1px solid #eeece6;vertical-align:top}
th{background:#f1f0eb;font-size:11px;letter-spacing:.08em;color:#5c666e;font-weight:600}
tr:last-child td{border-bottom:none}
td code{font-size:11px;color:#6f7a83}
td b{font-weight:600}
.note-box{background:#fff8ec;border:1px solid #eedfc4;border-radius:12px;padding:18px 22px;margin-top:22px}
.note-box h3{margin:0 0 8px;font-size:15px;color:#8a5a12}
.note-box ul{margin:0;padding-left:18px;font-size:13px;color:#5d5244}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:14px;font-size:12.5px;color:var(--muted)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.boundary{background:#fbeceb;border:1px solid #eccac6;border-radius:12px;padding:20px 24px;margin-top:26px}
.boundary h3{margin:0 0 8px;font-size:15px;color:#8f2f24}
.boundary ul{margin:0;padding-left:18px;font-size:13px;color:#5c4340}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);font-size:11.5px;color:#8a949c}
#lb{position:fixed;inset:0;background:rgba(24,28,31,.86);display:none;align-items:center;justify-content:center;
z-index:50;padding:4vh 4vw;cursor:zoom-out}
#lb.on{display:flex}
#lb figure{margin:0;max-width:100%;max-height:100%;display:flex;flex-direction:column;align-items:center;gap:10px}
#lb img{max-width:100%;max-height:86vh;background:#fff;border-radius:8px}
#lb figcaption{color:#e8e5df;font-size:12.5px}
@media(max-width:900px){.side{display:none}main{margin-left:0;padding:26px 18px 60px}h1{font-size:29px}
.step{grid-template-columns:1fr}.step img{border-right:none;border-bottom:1px solid var(--line)}}
@media print{.side,.tools,#lb{display:none}main{margin:0;padding:0}.part,.modcard,.step{break-inside:avoid}}
'''

    nav = ['<div class="brand">ASRS / V03.1<b>结构图册</b></div><nav>',
           '<a href="#overview">总览与读图</a>',
           '<a href="#modules">模块划分</a>',
           '<a href="#parts">零件图册</a>']
    for mid, title, _ in MODULES:
        nav.append(f'<a class="sub" href="#parts-{mid}">{title.split("·")[0].strip()} {title.split("·")[1].strip()}</a>')
    nav.append('<div class="rule"></div>')
    nav.append('<a href="#assembly">组装顺序</a>')
    nav.append('<a href="#interfaces">装配接口表</a>')
    nav.append('<a href="#boundary">放行边界</a>')
    nav.append('</nav>')

    body = []
    body.append(f'''<header class="hero" id="overview">
<div class="kicker">AUTOMATED STORAGE / MODULAR V03.1</div>
<h1>结构图册与装配说明</h1>
<p class="lede">从 <code>model/V03_1</code> 的实际 CAD 几何生成：127 类零件、376 个组件、42 处已建模接口。
按 A–G 七个模块拆解零件外形、模块装配形态与整机装配顺序。所有图像为几何渲染，不是制造图，也不是运行放行文件。</p>
<div class="chips">
<span class="chip"><b>4×5</b> 库位布局</span>
<span class="chip"><b>1253×593×766</b> mm 外形</span>
<span class="chip"><b>127</b> 类零件</span>
<span class="chip"><b>376</b> 个组件</span>
<span class="chip"><b>67.8</b> kg 空机估算</span>
<span class="chip"><b>1</b> kg 单箱设计输入</span>
</div>
<figure><img src="assembly_isometric.png" alt="V03.1 整机轴测图（隐藏防护板）">
<figcaption>整机轴测：隐藏防护板，橙色为未选型候选件。轴系 X 向右、Y 向观察者、Z 向上，单位 mm。</figcaption></figure>
</header>

<h2><span class="num">00</span>读图说明</h2>
<p class="sub">颜色只表示材料/工艺状态，尺寸取自 STEP 包围盒；配合、公差与紧固件长度不在此图册范围内。</p>
<div class="specs">
<div class="spec"><b>X 1250</b><span>行走行程，9 段齿条</span></div>
<div class="spec"><b>Y 593</b><span>伸缩行程，2 段齿条</span></div>
<div class="spec"><b>Z 766</b><span>升降高度，5 段齿条</span></div>
<div class="spec"><b>M1.5 / 20°</b><span>齿条模数、压力角；每段 24 齿距</span></div>
<div class="spec"><b>113.097</b><span>mm 每段齿条长度</span></div>
<div class="spec"><b>20</b><span>个库位 + 1 个独立 IO 位</span></div>
</div>
<div class="legend">
<span><i style="background:#c9d2d8"></i>铝（加工/型材）</span>
<span><i style="background:#9aa6b0"></i>钢（导轨/销/采购）</span>
<span><i style="background:#3da0ad"></i>PETG 打印件</span>
<span><i style="background:#e69438"></i>候选/未选型</span>
<span><i style="background:#adbdc8"></i>防护板</span>
<span><i style="background:#4c5054"></i>橡胶</span>
</div>
''')

    # modules
    body.append('<h2 id="modules"><span class="num">01</span>模块划分</h2>')
    body.append('<p class="sub">按装配功能拆分，而不是按 manifest 的 group 字段（group 表示运动层级：X 滑板承载 Z，Z 滑板承载 Y）。</p><div class="modgrid">')
    for mid, title, desc in MODULES:
        n_types = len(module_parts[mid])
        body.append(f'''<article class="modcard"><img src="modules/{mid}.png" alt="{esc(title)}">
<div class="mb"><h3>{esc(title)}</h3><p>{esc(desc)}</p>
<div class="count">{n_types} 类零件 · {inst_count[mid]} 个组件</div></div></article>''')
    body.append('</div>')

    # parts
    body.append('<h2 id="parts"><span class="num">02</span>零件图册</h2>')
    body.append('<p class="sub">每张卡片为一个零件编号（同一编号可能装多件）。点击图片可放大；下方搜索框可按中文名、编号或模块过滤。</p>')
    body.append('<div class="tools"><input id="q" type="search" placeholder="搜索：齿轮 / MGN12 / cell / E_y …" autocomplete="off"><span id="qcount">127 类零件</span></div>')
    for mid, title, desc in MODULES:
        body.append(f'<section class="modsect" id="parts-{mid}" data-mod="{mid}">')
        body.append(f'<h3>{esc(title)} <span style="color:#9aa3aa;font-weight:400;font-size:12.5px">（{len(module_parts[mid])} 类 / {inst_count[mid]} 件）</span></h3>')
        body.append(f'<p class="mdesc">{esc(desc)}</p><div class="pgrid">')
        for name in module_parts[mid]:
            p = PARTS[name]
            cn, remark = CN.get(name, (name, ''))
            qty = inst_by_part.get(name, p['quantity'])
            proc = p['process']
            badge = f'<span class="badge {esc(proc)}">{PROCESS_CN.get(proc, proc)}</span>'
            mat = MATERIAL_CN.get(p['material'], p['material'])
            note = p.get('note') or ''
            note_html = f'<p class="pnote">备注：{esc(note)}</p>' if note else ''
            key = f'{cn} {name} {mat} {mid}'.lower()
            body.append(f'''<article class="part" data-key="{esc(key)}">
<figure><img src="parts/{esc(name)}_iso.png" loading="lazy" alt="{esc(cn)} {esc(name)}"></figure>
<div class="pbody">
<div class="pname"><span>{esc(cn)}</span><i>×{qty}</i></div>
<code class="pcode">{esc(name)}</code>
<div class="meta">{badge}<span>{esc(mat)}</span><span>{fmt_dims(p['extents_mm'])} mm</span></div>
<p class="pnote">{esc(remark)}</p>
{note_html}
</div></article>''')
        body.append('</div></section>')

    # assembly
    body.append('<h2 id="assembly"><span class="num">03</span>组装顺序</h2>')
    body.append('<p class="sub">按“先固定、后运动，先基准、后齿条”的顺序。每一步都以下层已锁固的基准为准，不能靠调整齿条齿段来补偿装配误差。</p><div class="steps">')
    for idx, (title, items) in enumerate(STEP_TEXT, start=1):
        lis = ''.join(f'<li>{esc(t)}</li>' for t in items)
        body.append(f'''<article class="step"><img src="steps/step_{idx:02d}.png" alt="装配步骤 {idx:02d} {esc(title)}">
<div class="steptext"><div class="stepno">STEP {idx:02d}</div><h3>{esc(title)}</h3><ul>{lis}</ul></div></article>''')
    body.append('</div>')

    # interfaces
    body.append('<h2 id="interfaces"><span class="num">04</span>装配接口表</h2>')
    body.append('<p class="sub">以下 42 处为 CAD 中显式建模的连接及配对孔位；其余原始接头未逐一做紧固认证。螺钉长度、扭矩、工具空间与 T 型螺母型号仍待实物确认。</p>')
    body.append('<table><thead><tr><th style="width:26%">连接件 A</th><th style="width:26%">连接件 B</th><th style="width:18%">方式</th><th>紧固件</th></tr></thead><tbody>')
    for c in CONNECTIONS:
        a, b = c['a'], c['b']
        pa = next((i['part'] for i in INSTANCES if i['name'] == a), a)
        pb = next((i['part'] for i in INSTANCES if i['name'] == b), b)
        ca = CN.get(pa, (pa, ''))[0]
        cb = CN.get(pb, (pb, ''))[0]
        body.append(f'<tr><td><b>{esc(ca)}</b><br><code>{esc(a)}</code></td>'
                    f'<td><b>{esc(cb)}</b><br><code>{esc(b)}</code></td>'
                    f'<td>{esc(KIND_CN.get(c["kind"], c["kind"]))}</td><td>{esc(c["fasteners"])}</td></tr>')
    body.append('</tbody></table>')

    body.append('''<h2 id="boundary"><span class="num">05</span>放行边界</h2>
<p class="sub">本图册由几何文件生成，只说明“长什么样、怎么装”，不说明“能不能承载、能不能运行”。</p>
<div class="boundary"><h3>以下项目仍未验收，制造/硬件放行标志全部为 false</h3><ul>
<li><b>Z 打印齿：</b>承载、疲劳与蠕变未验收；背板加强不等于齿强度合格，空载也必须先完成独立防坠。</li>
<li><b>独立防坠/制动：</b><code>NC_Rail_Brake_CANDIDATE</code> 只是外形包络，没有钳口、动态捕获或认证证据。</li>
<li><b>驱动链：</b>三轴电机曲线、10:1 / 3:1 减速器、金属夹紧轮毂、Ø8 输出轴支承与轴向锁定均未选型定型。</li>
<li><b>紧固：</b>配对孔不等于螺钉长度、旋入深度、扭矩、防松、工具空间和 T 型螺母已经确认。</li>
<li><b>安全与电气：</b>工作台、锚固、安全门、门联锁、限位、急停、电池/BMS/充电器与整机供电尚未实机验收。</li>
<li><b>线束与视觉：</b>Y 节点 143 mm 柔性线束的弯曲半径/寿命未验证；相机内参、手眼外参与光照未标定。</li>
</ul></div>
<div class="note-box"><h3>可以做什么</h3><ul>
<li>按本图册做受控的局部手动试装：先底板，再货架，再 X/Z/Y 单轴，最后 IO 与防护。</li>
<li>每完成一个模块，手动全行程走查，确认无卡滞、无干涉、螺钉不顶死运动件。</li>
<li>任何带载、通电或多轴联动，都必须先完成对应模块的实测与工程复核。</li>
</ul></div>
<footer>数据源：model/V03_1/manifest.json、parts/*.step、BOM.csv · 渲染：VTK 离屏轴测 · 单位 mm · 几何原型，非制造放行文件。</footer>''')

    js = '''
const lb=document.getElementById('lb');const lbimg=lb.querySelector('img');const lbcap=lb.querySelector('figcaption');
document.querySelectorAll('.part img,.modcard img,.step img,.hero img').forEach(img=>{
  img.addEventListener('click',()=>{lbimg.src=img.src;lbcap.textContent=img.alt||'';lb.classList.add('on');});
});
lb.addEventListener('click',()=>lb.classList.remove('on'));
document.addEventListener('keydown',e=>{if(e.key==='Escape')lb.classList.remove('on');});
const q=document.getElementById('q');const qc=document.getElementById('qcount');
const parts=[...document.querySelectorAll('.part')];
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
  parts.forEach(p=>{const hit=!v||p.dataset.key.includes(v);p.style.display=hit?'':'none';if(hit)n++;});
  qc.textContent=v?`${n} 类零件匹配`:'127 类零件';
  document.querySelectorAll('.modsect').forEach(s=>{
    const any=[...s.querySelectorAll('.part')].some(p=>p.style.display!=='none');
    s.style.display=any?'':'none';});
});
'''
    doc = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>V03.1 结构图册与装配说明</title>
<style>{css}</style></head>
<body>
<aside class="side">{''.join(nav)}</aside>
<main>{''.join(body)}</main>
<div id="lb"><figure><img alt=""><figcaption></figcaption></figure></div>
<script>{js}</script>
</body></html>'''
    target = OUT / 'V03_1_结构图册.html'
    target.write_text(doc, encoding='utf-8')
    print(target, len(doc), 'chars')


if __name__ == '__main__':
    build()
