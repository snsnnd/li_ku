# SolidWorks API 封装说明（SwCadKit）

## 1. 结论先行

本机 SolidWorks 2025（版本号 33.0.0）的官方 C# Interop **已实测可连接、可建模、可保存、可导出**。
封装库位置：`cad/SwCadKit.dll`，源码 `cad/SwCadKit.cs`。
一键构建：`cad/Build.ps1`。

## 2. 环境事实

| 项目 | 实测值 |
|---|---|
| `SLDWORKS.exe` | `D:\SW\SOLIDWORKS\SLDWORKS.exe` |
| 版本 | 33.0.0.5050（SolidWorks 2025 SP0） |
| COM ProgID | `SldWorks.Application`，已注册 |
| 官方 Interop | `D:\SW\SOLIDWORKS\api\redist\SolidWorks.Interop.sldworks.dll` |
| 零件模板 | `C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_part.prtdot` |
| 装配模板 | `C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2025\templates\gb_assembly.asmdot` |

> 模板必须显式传入。本机未配置默认模板，直接调用会报“未设置默认零件模板”。

## 3. 封装了什么

### `SwSession`（会话）

| 成员 | 说明 |
|---|---|
| `Start(bool visible=false)` | 启动并连接 SolidWorks，创建 Modeler |
| `Box(x,y,z,w,d,h)` | 由中心+尺寸直接构造长方体实体（毫米输入） |
| `Cylinder(x,y,z,dx,dy,dz,r,h)` | 构造圆柱实体 |
| `CreatePart(name, body, template, path, material, stlPath)` | 建零件、上色、重建、保存、可选导出 STL |
| `CreateAssembly(template)` | 新建装配体 |
| `OpenAssembly(path)` | 打开已有装配体 |
| `CloseDocumentsUnder(dir)` | 只关闭指定目录下的文档，不动用户其他文件 |
| `Dispose()` | 释放 COM，不强制退出 SolidWorks |

### `SwBody`（实体）

| 成员 | 说明 |
|---|---|
| `Union(tool)` / `Cut(tool)` | 布尔并/差，内部检查错误码且要求结果为单一实体 |
| `BoundsMeters` | 实体包围盒（米，内部用） |

### `SwPartFile`（零件引用）

保存路径 + **包围盒中心**。后者是装配定位的关键数据。

### `SwAssembly`（装配）

| 成员 | 说明 |
|---|---|
| `Add(part, x, y, z)` | 以零件包围盒中心对齐到目标坐标（毫米） |
| `ComponentCount` | 顶层组件数 |
| `GetBoundingBoxMm()` | 先 `UpdateBox()` 再取包围盒并换算毫米 |
| `GetComponentDiagnostics()` | 逐组件包围盒 + 4×4 变换矩阵 |
| `Save(path)` / `Export(path)` | 保存 / 另存为 STEP、PNG 等 |
| `ShowPreview(reverse, centerMm, zoomToBounds)` | 等轴测、可反向、按包围盒缩放、带边线上色 |

## 4. 封装的三个关键坑

### 4.1 AddComponent2 按“包围盒中心”落位

SolidWorks `IAssemblyDoc.AddComponent2(path, x, y, z)` 在本机把组件放在给定坐标处时，是按**零件包围盒中心**对齐，而不是零件原点。
所以长立柱会以中点插到目标点，落位后下探半根长度。

封装做法：建零件时记录 `body.GetBodyBox()` 的中心，`Add()` 时用 `目标坐标 + 包围盒中心`。
这样调用方始终以“这个零件的几何中心要放在哪”来写代码，不再关心原点偏置。

### 4.2 变换矩阵的数组布局

`Component2.Transform.ArrayData` 返回 16 个 double：

```
[0..8]   3×3 旋转矩阵
[9..11]  平移 X/Y/Z（米）
[12]     比例
[13..15] 保留
```

最初把第 8 项当作旋转分量，导致 96 个组件全部误报“旋转异常”。正确判定应检查 `t[0]、t[4]、t[8] ≈ 1`，且 `t[1]、t[2]、t[3]、t[5]、t[6]、t[7] ≈ 0`。

### 4.3 编译器只支持 C# 5

本机使用 `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`，不支持：

- 表达式体属性 `=>`
- `nameof`
- 只读自动属性 `{ get; }`

封装库已全部改为 `{ get; private set; }` 和显式 `get { return ...; }`。
若日后换 Roslyn，可再简化。

## 5. 使用方法

```powershell
# 只编译库和两个可执行程序
D:\立库\cad\Build.ps1

# 编译 + 重建全部模型
D:\立库\cad\Build.ps1 -Run

# 编译 + 重建 + 校验
D:\立库\cad\Build.ps1 -Run -Validate
```

调用示例：

```csharp
using (SwSession cad = SwSession.Start())
{
    SwPartFile cell = cad.CreatePart("Rack_Cell", cad.Box(0,0,0,118,130,4),
        PartTemplate, @"D:\立库\model\Rack_Cell.SLDPRT", material, @"D:\立库\stl\Rack_Cell.stl");

    SwAssembly asm = cad.CreateAssembly(AssemblyTemplate);
    asm.Add(cell, 70, 65, 90);          // 毫米，几何中心
    asm.Save(@"D:\立库\model\Demo.SLDASM");
    asm.Export(@"D:\立库\model\Demo.STEP");
}
```

## 6. 与生成器的关系

`cad/BuildModularAsrs.cs` 只保留**业务参数**（列数、层距、零件形状、装配坐标），
所有 `SolidWorks.Interop.*` 调用都在 `SwCadKit` 内。
以后换库、换机器或加 MCP，只需要替换 `SwCadKit` 的实现，生成器不用改。

## 7. 第三方 SolidWorks MCP 现状（核验于 2026-11-04）

| 项目 | 状态 | 结论 |
|---|---|---|
| `hjbaard/SolidWorks-MCP` | MIT，Python，20 star，2026-11-03 仍在更新（GitHub API 核实） | 社区项目，非官方；驱动本机 SolidWorks，可参考 |
| `alisamsam/Solidworks-MCP` | 检索到，含任意代码执行能力（未逐行审计） | 安全边界差，不建议直接用于生产 |
| `vespo92/SolidworksMCP-TS` | 检索到，作者标注 Alpha（未逐项验证） | 装配能力未完整验证 |
| SolidWorks 官方 LEO | 内建 AI，需 2026 SP3+ 与 3DEXPERIENCE | 非 MCP，按 Token 计费 |

本项目的选择：**不引入第三方 MCP**，直接用官方 Interop 封装成确定性 DLL。理由是可复现、可审计、不依赖外部服务，也不会把图纸发给云端。

## 8. 清理与安全

- 封装库不会调用 `ExitApp()`，生成结束后 SolidWorks 保持打开，方便人工复核。
- 所有写入路径集中在 `model/`、`stl/`，不会修改 SolidWorks 安装目录。
- 覆盖保存前先删除同名旧文件，避免“看起来保存成功、实际仍是旧版”。
