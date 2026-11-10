# 立库机械原型项目

Project CAD, engineering, documentation, and verification source. 包含 V02/V03/V03.1 基准、手动验证样机、带电机单库位 MVP、同步带优化、CoreXY 初始重构和收敛版本。

仓库名（origin）为 `snsnnd/li_ku`。

## 主要入口

- **[最新版：C04 机械收敛版](model/CoreXY_Final_C04/README.md)**（目标 1 kg，非制造/带载放行）
- [C04 优先查看 STEP](model/CoreXY_Final_C04/viewing/CoreXY_C04_SOLIDS_AP203.step) · [整机预览](model/CoreXY_Final_C04/previews/C04_assembly.png)

历史交付保留，不覆盖旧证据：

- [最小三轴验证装置](最小三轴验证装置_先读我.md)
- [电驱单库位 MVP E01](电驱单库位MVP_先读我.md)
- [同步带优化 MVP E02](同步带优化MVP_E02_先读我.md)
- [CoreXY 整体重构 C03](CoreXY整体重构_C03_先读我.md)

## 当前状态

CAD 几何与离散检查可复现；实物选型、强度/温度验证、独立防下滑和电气安全仍为明确放行门槛。1 kg 是设计目标，不得视为已经批准带载运行。

版本的生成与验证由 `cad/` 下对应 Python 模块执行；历史交付文件保持不变，避免用新结果覆盖旧证据。
