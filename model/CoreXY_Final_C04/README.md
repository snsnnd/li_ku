# C04 机械收敛版

**目标净货载 1 kg；这是机械几何设计评审交付，不是制造放行或带载运行许可。**

## 打开顺序

1. `viewing/CoreXY_C04_SOLIDS_AP203.step`：优先查看，平铺多实体 AP203；未声称在你的 SolidWorks 中完成 GUI 导入验证。
2. `CoreXY_C04_ASSEMBLY.step`：带实例名称及颜色的总装 STEP。
3. `previews/C04_assembly.png`、`C04_drive_detail.png`：整机及底部传动；预览省略透明防护板，STEP 保留。
4. `drawings/CoreXY机械收敛_C04_评审图.pdf`：A3 评审图、实际 BRep 三视投影和局部构造孔轴表；不是完整制造公差/工艺图。
5. `BOM.csv`、`打印清单.csv`、`采购与金属加工清单.csv`：编号对应 `parts/`；只有 `process=print` 的零件可按 `stl/` 打印。不得打印替代承力金属件。
6. `delivery_audit.json`、`validation.json`、`tests.xml` 和 `SHA256SUMS.txt`：以实际生成并通过审核的证据为准。不存在的文件不表示已完成该步骤。

## 固定架构

- 两台已有 ZDT 电机固定在底部，驱动双层开口 CoreXY；第三台随动，驱动 TR8x2 金属丝杆升降塔。
- 双金属箱梁、双轨承载平台、固定双钢叉；没有独立 Y 推杆电机、释放舵机或牵引销。
- 单货位及独立 IO，配套外侧承托轨和去牵引眼的 110×120×60 料盒。不要混用旧 E01/E02 分件。

## C04 相对 C03 的收敛

- 采用 Phidgets TRM4226_0 / GT2M-06 齿板与背板的厂家尺寸；原图及哈希见 `references/`。CAD 不包含采购件专有 GT2 齿形，不能按光滑包络加工齿板或带轮。
- 端夹中心移至 X±35，左端独立 +X 方向 0..2 mm 螺杆调节，另设槽锁紧；右端固定。每端名义 18 mm 夹持含 9 mm 尾段。行程不是推荐皮带预拉伸量。
- B 电机安装面提高至 Z84（A 仍为 Z78），轴在带轮内支承约 12 mm；下夹紧轮毂本身仍长 6 mm，不能混为一谈。
- 增加带轮夹紧螺钉、肩轴六角孔、内圈垫片、底座/基准条等紧固及头部凹位。
- 横梁恢复与原有孔位对应的 8 颗 M4×10 螺钉，全部归入随 Y 运动的横梁组。端板通孔 Ø4.2、头部凹位 Ø8，梁底壁 Ø3.3 底孔；螺钉用小径包络表示，不用穿透豁免掩盖错位。

## 坐标与路径约束

单位 mm。XY 回缩中心 `(90,-140)`；X 工作 `-90..90`，Y 工作 `-140..3`。货位料盒中心 `(90,158)`、层面 Z380；IO `(-90,158)`、层面 Z293。叉面进入为层面−8，抬升为层面+4；Z 工作 `285..384`。

先回到 Y=−140 通道再横移/大范围升降；进入只能在已对准的货位或 IO 执行，禁止插叉状态横向跨库位。CoreXY 映射 `A=dx+dy`、`B=-dx+dy`，20T GT2 为 40 mm/rev。实际方向、接线和协调控制尚未实现。

244 个合法姿态仅为离散碰撞采样，不等于连续扫掠或实物动态验收。静态总装显示维护销插入；运动检查中移除。手动维护销不等于自动防坠。

## 仍不能放行的项目

实际电机扭矩-转速/温升/轴承径向额定值、采购轮毂和惰轮符合性、夹板拉脱与轮毂滑转试验、肩轴配合预载、全机紧固/公差/工具通道签核、导轨及连接强度、线束、独立自动防下滑、急停/限位/门禁/接地及控制固件仍需完成。IO 满载开门名义顶部余量只有 6 mm，必须计入实物公差与变形验证。

`manufacturing_release_allowed`、`hardware_accepted`、`loaded_operation_allowed` 均保持 false。工程签核、防护和控制完成后，才可安排空行程、空盒及分级加载验收。

## 复现

在仓库根目录使用 Python 3.12，安装 `cad/powered_mvp/requirements.lock.txt`，然后：

```sh
python -B cad/corexy_final/validate_final.py --motion --export
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest cad/corexy_final/test_final.py -q --junitxml=model/CoreXY_Final_C04/tests.xml
python -B cad/corexy_final/deliver_final.py
python -B cad/corexy_final/publish_final.py
```

只需先看预览时，第三步加 `--preview-only`，随后用 `--drawings-only` 补图纸。中文图纸依赖 SimHei 与 DejaVu Sans，可用 `MANUAL_CJK_TTF` 指定中文字体。

本版从保留的 C03 导出分件加载几何；复现需要完整仓库及 Git LFS 内容，不可只复制 `cad/corexy_final/`。评审 ZIP 仅含 C04 交付及本版源码，依赖路径/哈希另列于 `source_dependencies.json`，不重复封装历史版本。
