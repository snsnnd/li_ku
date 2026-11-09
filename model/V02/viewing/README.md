# 内部结构查看副本

打开 `ASRS_Modular_V02_INTERIOR_VIEW.step`。

- 与已核验 V02 相同的内部结构，共248个实体；仅省略5块外罩板，方便观察。
- 扁平多实体STEP，不依赖原装配层级、颜色或透明显示。
- 不是制造模型，不含运动配合；原权威整机文件仍为上一级的 `ASRS_Modular_V02.step`。
- 电机仍为 V02 占位几何，未替换用户提供的 ZDT 电机。
- 本副本的实体回读记录见 `interior_view_validation.json`。
- 已在SolidWorks实际打开并导出画面，见 `solidworks_view.png`；当前会话已调整为Z轴朝上、带边线上色显示。STEP重新导入不保证保留这一视角。

原STEP在SolidWorks中已读入253个组件/实体，但用户遇到图形区异常，且后续检查时SolidWorks进程退出。尚未确定具体的导入兼容性或图形驱动原因，不把此查看副本当作已定位和修复所有软件故障。
