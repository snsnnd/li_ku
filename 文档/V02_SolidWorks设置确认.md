# SolidWorks 导入中断后的设置确认

本次原生转换在方管导入处长时间停留，取消后出现`0x800706BE`；清理阶段出现`0x800706BA`（RPC服务器不可用）。

按用户明确选择，没有重启或强制结束SolidWorks，也没有关闭用户原有文档。53件已保存零件保留，**没有完成整机原生装配**。

转换器曾临时修改以下选项，但COM连接断开导致恢复调用失败。下次打开SolidWorks时，请在“工具→选项→系统选项”确认：

| 选项 | 本次导入临时值 | 应如何处理 |
|---|---|---|
| 默认零件模板 | `C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_part.prtdot` | 按您原先的模板习惯恢复/确认 |
| 默认装配模板 | `C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_assembly.asmdot` | 按您原先的模板习惯恢复/确认 |
| 始终使用默认模板 | 开启 | 如习惯每次选择模板，恢复为相应选项 |
| 启用3D Interconnect | 关闭 | 如平时使用该功能，请重新开启 |

失败报告没有可靠保存上述选项的原值，因此没有猜测并写回某个配置。后续版本的转换器已经增加原值记录和恢复回读，但**不宣称这能追溯恢复本次未知原值**。

详细错误与已保存零件见`model/V02/native/solidworks_validation.json`。设置确认不改变本次STEP、STL及Linux端实体检查结果。
