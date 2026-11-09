"""Conservative sizing calculations; NOT FEA, certified selection or load acceptance."""
import importlib.util
import json
import math
from pathlib import Path

from asrs_v02 import OUT, ROOT, build_model, source_sha256

TOOL = ROOT/'tools'/'V02'/'solidworks-automation-skill'/'scripts'/'drive_sizing.py'
RHO = {'aluminum': 2.70e-6, 'steel': 7.85e-6, 'PETG': 1.27e-6,
       'POM': 1.41e-6, 'rubber': 1.2e-6, 'guard': 1.20e-6, 'safety': 7.85e-6}


def part_mass(p):
    if p.name.startswith('NEMA17_NC'):
        return .48, 'assumed vendor maximum; verify including brake'
    if p.name.startswith('NEMA17'):
        return .30, 'assumed vendor maximum; verify'
    if p.name == 'MG90S_Envelope':
        return .014, 'nominal servo mass, verify vendor'
    if p.name.startswith('MGN12H'):
        return .054, 'HIWIN MG catalogue'
    if p.name.startswith('MGN9H'):
        return .026, 'HIWIN MG catalogue'
    if p.name.startswith('MGN12_Rail'):
        return (.455 if 'X700' in p.name else .325), 'HIWIN rail 0.65 kg/m'
    if p.name.startswith('MGN9_Rail'):
        return .076, 'HIWIN rail 0.38 kg/m, 200 mm'
    if p.name.startswith('3030_'):
        return .60, 'conservative assumed 1.0 kg/m; supplier section pending'
    if p.name.startswith('2020_'):
        length = max(p.shape.BoundingBox().xlen, p.shape.BoundingBox().ylen, p.shape.BoundingBox().zlen)
        return .60*length/1000, 'conservative assumed 0.60 kg/m; supplier section pending'
    if p.material == 'purchased':
        return p.shape.Volume()*7.85e-6, 'solid steel equivalent upper estimate'
    return p.shape.Volume()*RHO[p.material], 'B-rep solid volume x density; printed parts are solid upper estimate'


def main():
    m = build_model()
    masses = []
    for i in m.items:
        kg, method = part_mass(i.part)
        masses.append({'instance': i.name, 'part': i.part.name, 'group': i.group, 'kg': kg, 'method': method})
    z_mass = sum(v['kg'] for v in masses if v['group'] in ('z', 'y', 'pin', 'bin', 'crank', 'roller', 'spring'))
    z_mass += m.d.payload_kg + .35  # Explicit allowance for fasteners, harness, retainers.
    x_mass = sum(v['kg'] for v in masses if v['group'] != 'fixed') + m.d.payload_kg + .70
    bin_mass = part_mass(m.parts['Bin_110x120_TowEye'])[0] + m.d.payload_kg
    if not TOOL.is_file():
        raise FileNotFoundError('Download pinned auxiliary tool first: '+str(TOOL))
    spec = importlib.util.spec_from_file_location('reviewed_drive_sizing', TOOL)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    specs = [
        {'id': 'X', 'load': {'mass_kg': x_mass, 'incline_deg': 0, 'friction_coeff': .02, 'external_force_n': 3},
         'motion': {'distance_mm': 450, 'max_speed_mm_s': 50, 'accel_mm_s2': 100, 'dwell_s': 1, 'round_trip': True},
         'transmission': {'type': 'belt', 'pulley_radius_mm': 20/math.pi, 'efficiency': .85},
         'motor': {'has_brake': False, 'rotor_inertia_kgcm2': .054}},
        {'id': 'Z', 'load': {'mass_kg': z_mass, 'incline_deg': 90, 'friction_coeff': 0, 'external_force_n': 5},
         'motion': {'distance_mm': 380, 'max_speed_mm_s': 8, 'accel_mm_s2': 30, 'dwell_s': 2, 'round_trip': True},
         'transmission': {'type': 'lead_screw', 'lead_mm': 2, 'efficiency': .25,
                          'screw_diameter_mm': 8, 'screw_length_mm': 550},
         'motor': {'has_brake': True, 'rotor_inertia_kgcm2': .054}},
        {'id': 'Y', 'load': {'mass_kg': bin_mass+.30, 'incline_deg': 0,
                            'friction_coeff': .35, 'external_force_n': 3},
         'motion': {'distance_mm': m.d.transfer, 'max_speed_mm_s': 20, 'accel_mm_s2': 50,
                    'dwell_s': 1, 'round_trip': True},
         'transmission': {'type': 'belt', 'pulley_radius_mm': 20/math.pi, 'efficiency': .80},
         'motor': {'has_brake': False, 'rotor_inertia_kgcm2': .054}},
    ]
    drives = [mod.evaluate_drive(s, {'driveTorqueSafetyFactor': 2}) for s in specs]
    # Cantilever tubes: 25x25x2, two rails, conservative tip load, 2x dynamic factor.
    I = (25**4-21**4)/12
    tube_load = (bin_mass+.15)*9.80665*2/2
    L, E = 215, 69000
    deflection = tube_load*L**3/(3*E*I)
    stress = tube_load*L*12.5/I
    # TR8x2 root d=6 mm, unsupported length .51 m, pinned/pinned conservative Euler screen.
    screw_I = math.pi*6**4/64
    buckling = math.pi**2*200000*screw_I/510**2
    axial = z_mass*9.80665*2
    report = {
        'generator_sha256': source_sha256(), 'review_required': True, 'release_allowed': False,
        'mass_breakdown': masses, 'z_design_moving_mass_kg': z_mass,
        'x_design_moving_mass_kg': x_mass, 'bin_plus_payload_kg': bin_mass,
        'drive_specs': specs, 'drive_results': drives,
        'minimum_motor_curve_targets': [{
            'axis': r['driveId'], 'speed_rpm': r['result']['n_max_rpm'],
            'required_torque_nm_with_SF2': r['result']['t_peak_nm']*2,
            'selected_motor_verified': False} for r in drives],
        'tube_screen': {'I_mm4': I, 'effective_length_mm': L, 'dynamic_factor': 2,
                        'bending_stress_MPa': stress, 'tip_deflection_mm': deflection,
                        'joint_flexibility_included': False, 'prototype_target_deflection_mm': .5},
        'screw_euler_screen': {'root_diameter_mm_assumed': 6, 'length_mm': 510,
                               'critical_force_N': buckling, 'design_axial_force_N': axial,
                               'ratio': buckling/axial, 'critical_speed_verified': False},
        'secondary_nut_catch_screen': {
            'catch_gap_mm': .8, 'assumed_stopping_deflection_mm': .05,
            'linear_spring_peak_estimate_N': 2*z_mass*9.80665*(1+.8/.05),
            'minimum_design_catch_force_N': 1200,
            'cross_pin_diameter_mm': 2.5,
            'cross_pin_double_shear_MPa_at_1200N': 1200/(2*math.pi*2.5**2/4),
            'shaft_local_bearing_MPa_screen': 1200/(2.5*(6-2.5)),
            'minimum_pin_supplier_double_shear_N': 2500,
            'dynamic_catch_test_passed': False,
            'note': 'Stopping deflection is an assumption, not measured. Steel cage, four M3 bolts, threads, bearing stack and cross-drilled shaft require impact/FEA review.'},
        'brake': {'specified_min_holding_torque_nm': .30, 'normally_engaged': True,
                  'supplier_selected': False, 'emergency_dynamic_braking_certified': False},
        'pin': {'nominal_diameter_mm': 4, 'target_drag_force_limit_N': 12,
                'single_shear_stress_at_limit_MPa': 12/(math.pi*4**2/4),
                'eye_bearing_stress_MPa': 12/(4*6), 'printed_eye_coupon_test_required': True},
        'limitations': ['Not FEA; no joint/preload/contact stiffness verification',
                        'Motor curves and bearing/screw supplier drawings still required',
                        'Brake does not protect against screw fracture',
                        'Four M6 table anchors mandatory; tabletop capacity and anchor pullout unverified',
                        'Torque/current alone is not a certified force limiter'],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'engineering_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('z_design_moving_mass_kg', 'x_design_moving_mass_kg',
                                           'minimum_motor_curve_targets', 'tube_screen', 'screw_euler_screen')}, indent=2))


if __name__ == '__main__':
    main()
