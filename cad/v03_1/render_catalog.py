"""V03.1 illustrated catalog renderer.

Reads model/V03_1/manifest.json plus parts/*.step and produces:
  drawings/parts/<part>_iso.png      shaded isometric part views
  drawings/parts/<part>_line.svg     hidden-line drawing (skipped for supplier motor models)
  drawings/modules/<module>.png      assembled module views
  drawings/steps/step_NN.png         cumulative assembly sequence
Geometry only; this does not constitute a manufacturing release.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import cadquery as cq
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'model' / 'V03_1'
PARTS_DIR = MODEL / 'parts'
OUT = MODEL / 'drawings'

MANIFEST = json.loads((MODEL / 'manifest.json').read_text(encoding='utf-8'))
PARTS = {p['name']: p for p in MANIFEST['parts']}
INSTANCES = MANIFEST['instances']
CONNECTIONS = MANIFEST['connections']

COLORS = {
    'aluminum': (0.79, 0.83, 0.87),
    'steel': (0.60, 0.65, 0.71),
    'PETG': (0.24, 0.63, 0.70),
    'purchased': (0.40, 0.46, 0.52),
    'candidate': (0.90, 0.58, 0.22),
    'guard': (0.68, 0.78, 0.84),
    'rubber': (0.30, 0.32, 0.35),
    'safety': (0.80, 0.32, 0.26),
}

MODULES = [
    ('A_base', 'A · 底板与基础', '三块 6 mm 铝底板、拼接板与工作台锚固面'),
    ('B_rack', 'B · 立体货架', '4 列 × 5 层库位、型材立柱、层板托角、X 齿条与背板'),
    ('C_x', 'C · X 行走模组', '双 MGN12 导轨、X 滑板、X 电机与小齿轮、X 本地电源'),
    ('D_z', 'D · Z 升降模组', '双 3030 立柱、MGN12 升降导轨、Z 齿条背板、防坠与制动'),
    ('E_y', 'E · Y 伸缩取放头', 'Y 脊板双导轨、方管托盘、锁销机构与舵机'),
    ('F_io', 'F · IO 工位', '法兰支腿、金属框架、内闸门与外门、料盒托板'),
    ('G_guard', 'G · 外防护', '立柱、横梁与四周防护板'),
]

MODULE_ORDER = [m[0] for m in MODULES]


def module_of_part(name: str) -> str:
    n = name
    if n.startswith('Base_Panel') or n.startswith('Base_Splice'):
        return 'A_base'
    if n.startswith(('Guard_',)):
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
    # local power nodes: instance name decides, part-level falls back to X node
    if n.startswith(('Local_Power_', 'Battery_Candidate', 'ESP32_Controller')):
        return 'C_x'
    raise KeyError('unmapped part: ' + n)


def module_of_instance(inst: dict) -> str:
    n = inst['name']
    if n.startswith('x_motor_plate'):
        return 'C_x'
    if n.startswith('y_motor_plate'):
        return 'E_y'
    if n.startswith('x_power') or n.startswith('x_battery') or n.startswith('x_esp32'):
        return 'C_x'
    if n.startswith(('z_power', 'z_battery', 'z_esp32')):
        return 'D_z'
    if n.startswith(('y_power', 'y_battery', 'y_esp32')):
        return 'D_z'  # Y node rides on the Z platform
    return module_of_part(inst['part'])


CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def load_mesh(name: str, tol: float = 0.45, ang: float = 0.30):
    if name in CACHE:
        return CACHE[name]
    path = PARTS_DIR / f'{name}.step'
    shape = cq.importers.importStep(str(path)).val()
    verts, faces = shape.tessellate(tol, ang)
    v = np.array([[p.x, p.y, p.z] for p in verts], dtype=np.float64)
    f = np.array(faces, dtype=np.int64)
    CACHE[name] = (v, f)
    return v, f


def polydata(v: np.ndarray, f: np.ndarray) -> vtk.vtkPolyData:
    if len(v) and (v.max(0) - v.min(0)).min() < 0.2:
        f = np.vstack([f, f[:, ::-1]])  # single-sided sheet: give it a back face
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.ascontiguousarray(v), deep=True))
    pd.SetPoints(pts)
    cells = vtk.vtkCellArray()
    flat = np.hstack([np.full((len(f), 1), 3, dtype=np.int64), f]).ravel()
    cells.SetCells(len(f), numpy_to_vtkIdTypeArray(flat, deep=True))
    pd.SetPolys(cells)
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(pd)
    clean.SetTolerance(1e-4)
    clean.PointMergingOn()
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(clean.GetOutputPort())
    normals.SetFeatureAngle(38)
    normals.SplittingOn()
    normals.ConsistencyOn()
    normals.Update()
    return normals.GetOutput()


def make_actor(name: str, tol=0.45, color=None, opacity=1.0):
    v, f = load_mesh(name, tol)
    part = PARTS[name]
    rgb = color if color else COLORS.get(part['material'], (0.6, 0.6, 0.6))
    if name in ('Marker_Card_32mm', 'IO_External_Reference_Card'):
        rgb = (0.95, 0.94, 0.89)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(polydata(v, f))
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*rgb)
    prop.SetOpacity(opacity)
    prop.SetAmbient(0.22)
    prop.SetDiffuse(0.74)
    prop.SetSpecular(0.16)
    prop.SetSpecularPower(24)
    prop.SetInterpolationToPhong()
    prop.BackfaceCullingOff()
    return actor


def new_scene(size=(1500, 1050), bg=(1.0, 1.0, 1.0)):
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(*size)
    rw.SetMultiSamples(8)
    ren = vtk.vtkRenderer()
    ren.SetBackground(*bg)
    ren.SetBackground2(0.96, 0.97, 0.98)
    ren.GradientBackgroundOn()
    ren.SetUseDepthPeeling(0)
    ren.SetUseFXAA(True)
    rw.AddRenderer(ren)
    # camera-relative three-point rig: every orientation stays readable, including thin plates
    specs = [((-0.8, 0.9, 0.9), 0.55), ((1.0, 0.15, 0.85), 0.35), ((0.1, -1.0, 0.5), 0.18),
             ((0.0, 0.0, 1.0), 0.30)]
    for pos, inten in specs:
        light = vtk.vtkLight()
        light.SetPosition(*pos)
        light.SetFocalPoint(0, 0, 0)
        light.SetIntensity(inten)
        light.SetPositional(0)
        light.SetLightTypeToCameraLight()
        ren.AddLight(light)
    return rw, ren


def set_camera(ren, points: np.ndarray, direction=(0.95, -1.0, 0.62), margin=1.06, up=(0, 0, 1),
               window=(1500, 1050)):
    lo, hi = points.min(0), points.max(0)
    base = (lo + hi) / 2
    d = np.array(direction, dtype=float)
    d /= np.linalg.norm(d)
    upv = np.array(up, dtype=float)
    right = np.cross(upv, d)
    right /= np.linalg.norm(right)
    upv = np.cross(d, right)
    rel = points - base
    x, y, z = rel @ right, rel @ upv, rel @ d
    center = base + right * (x.min() + x.max()) / 2 + upv * (y.min() + y.max()) / 2 + d * (z.min() + z.max()) / 2
    half_w = (x.max() - x.min()) / 2
    half_h = (y.max() - y.min()) / 2
    aspect = window[0] / window[1]
    scale = max(half_h, half_w / aspect) * margin
    depth = (z.max() - z.min()) / 2
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetFocalPoint(*center)
    cam.SetPosition(*(center + d * (depth * 3 + 200)))
    cam.SetViewUp(*upv)
    cam.SetParallelScale(max(scale, 1.0))
    ren.ResetCameraClippingRange()


def save_png(rw, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.SetScale(1)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()


def render_part(name: str):
    png = OUT / 'parts' / f'{name}_iso.png'
    rw, ren = new_scene((900, 700))
    actor = make_actor(name, tol=0.30)
    ren.AddActor(actor)
    v, _ = load_mesh(name, 0.30)
    set_camera(ren, v, margin=1.05, window=(900, 700))
    save_png(rw, png)
    rw.Finalize()
    return png


def render_module(module: str):
    items = [i for i in INSTANCES if module_of_instance(i) == module]
    rw, ren = new_scene((1500, 1050))
    all_pts = []
    for inst in items:
        part = PARTS[inst['part']]
        guard = part['material'] == 'guard'
        opacity = 0.30 if (guard and module == 'G_guard') else 1.0
        actor = make_actor(inst['part'], tol=0.55, opacity=opacity)
        actor.SetPosition(*inst['origin_mm'])
        ren.AddActor(actor)
        v, _ = load_mesh(inst['part'], 0.55)
        all_pts.append(v + np.array(inst['origin_mm']))
    pts = np.vstack(all_pts)
    set_camera(ren, pts, margin=1.08)
    out = OUT / 'modules' / f'{module}.png'
    save_png(rw, out)
    rw.Finalize()
    return out, len(items)


STEP_MODULES = ['A_base', 'B_rack', 'C_x', 'D_z', 'E_y', 'F_io', 'G_guard']


def render_steps():
    outs = []
    for idx, upto in enumerate(STEP_MODULES, start=1):
        allowed = set(STEP_MODULES[:idx])
        items = [i for i in INSTANCES if module_of_instance(i) in allowed]
        rw, ren = new_scene((1500, 1050))
        all_pts = []
        for inst in items:
            guard = PARTS[inst['part']]['material'] == 'guard'
            actor = make_actor(inst['part'], tol=0.6, opacity=0.22 if guard else 1.0)
            actor.SetPosition(*inst['origin_mm'])
            ren.AddActor(actor)
            v, _ = load_mesh(inst['part'], 0.6)
            all_pts.append(v + np.array(inst['origin_mm']))
        pts = np.vstack(all_pts)
        set_camera(ren, pts, margin=1.10)
        out = OUT / 'steps' / f'step_{idx:02d}.png'
        save_png(rw, out)
        rw.Finalize()
        outs.append(out)
    # final "complete" view from the opposite side
    rw, ren = new_scene((1500, 1050))
    all_pts = []
    for inst in INSTANCES:
        guard = PARTS[inst['part']]['material'] == 'guard'
        actor = make_actor(inst['part'], tol=0.6, opacity=0.16 if guard else 1.0)
        actor.SetPosition(*inst['origin_mm'])
        ren.AddActor(actor)
        v, _ = load_mesh(inst['part'], 0.6)
        all_pts.append(v + np.array(inst['origin_mm']))
    set_camera(ren, np.vstack(all_pts), direction=(-0.95, -0.85, 0.55), margin=1.08)
    out = OUT / 'steps' / 'step_08.png'
    save_png(rw, out)
    rw.Finalize()
    outs.append(out)
    return outs


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    OUT.mkdir(parents=True, exist_ok=True)
    if which in ('all', 'modules'):
        for m in STEP_MODULES:
            t = time.time()
            out, n = render_module(m)
            print(f'module {m:8s} {n:3d} instances {time.time()-t:5.1f}s -> {out.name}', flush=True)
    if which in ('all', 'steps'):
        for out in render_steps():
            print('step ->', out.name, flush=True)
    if which in ('all', 'parts'):
        for name in sorted(PARTS):
            t = time.time()
            out = render_part(name)
            print(f'part {name:46s} {time.time()-t:5.1f}s', flush=True)


if __name__ == '__main__':
    main()
