"""Sizing targets from V03 geometry and declared candidate masses, not a release."""
import json
import math
from asrs_v03 import OUT,FINGERPRINT,build_model
from gears import MODULE,RADIUS


def mass(p):
    if p.name.startswith('ZDT_RealMotor'):return .50,'assumed complete motor+driver, weigh actual unit'
    if p.name.startswith('Battery_Candidate'):return .45,'assumed protected pack; not selected'
    if p.name.startswith('ESP32_'):return .025,'assumed board and local connector allowance'
    if p.name.startswith('Z_Reduction'):return .35,'assumed gearbox; supplier not selected'
    if p.name.startswith('Y_Reduction'):return .20,'assumed gearbox; supplier not selected'
    if p.name.startswith('NC_Rail_Brake'):return .30,'assumed brake; supplier not selected'
    if p.name.startswith('Camera_CANDIDATE'):return .04,'assumed camera assembly'
    if p.name.startswith(('2020_','Guard_Post','Guard_Cross','Guard_Side')):
        b=p.shape.BoundingBox();return max(b.xlen,b.ylen,b.zlen)*.0006,'assumed aluminium profile 0.60 kg/m'
    if p.name.startswith('3030_'):return .60,'assumed aluminium profile 1.0 kg/m'
    rho={'aluminum':2.70e-6,'steel':7.85e-6,'PETG':1.27e-6,'purchased':7.85e-6,
         'safety':7.85e-6,'guard':1.20e-6,'rubber':1.2e-6,'POM':1.41e-6}
    return p.shape.Volume()*rho[p.material],'CAD solid volume x assumed density'


def main():
    m=build_model();rows=[]
    for i in m.items:
        kg,method=mass(i.part);rows.append({'instance':i.name,'group':i.group,'kg':kg,'method':method})
    z_groups={'z','zgear','y','ygear','bin','pin','roller','crank','spring'}
    zm=sum(r['kg'] for r in rows if r['group'] in z_groups)+1+.45
    xm=sum(r['kg'] for r in rows if r['group'] not in ('fixed','io_shutter'))+1+.9
    ym=sum(r['kg'] for r in rows if r['group'] in {'y','ygear','bin','pin','roller','crank','spring'})+1+.20
    # Conservative first screening: all Y moving mass counted in friction, plus drag allowance.
    g=9.80665;rp=RADIUS/1000
    targets=[]
    for axis,kg,speed,accel,friction,external,ratio,eta in [
        ('X',xm,12,40,.03,4,1,.8),('Z',zm,3,15,0,8,10,.70),('Y',ym,5,25,.35,4,3,.70)]:
        force=kg*accel/1000+friction*kg*g+external+(kg*g if axis=='Z' else 0)
        output=force*rp
        targets.append({'axis':axis,'mass_kg':kg,'initial_speed_mm_s':speed,'initial_accel_mm_s2':accel,
            'ratio':ratio,'assumed_total_efficiency':eta,'force_N':force,'pinion_torque_Nm':output,
            'motor_torque_with_SF2_Nm':2*output/(ratio*eta),
            'motor_speed_rpm':speed/(2*math.pi*RADIUS)*60*ratio,'motor_curve_verified':False})
    force=next(r['force_N'] for r in targets if r['axis']=='Z')
    r={'fingerprint':FINGERPRINT,'mass_breakdown':rows,'cad_empty_mass_estimate_kg':sum(r['kg'] for r in rows),
       'fully_loaded_mass_including_2kg_allowance_kg':sum(r['kg'] for r in rows)+22,
       'motor_targets':targets,
       'printed_Z_tooth_screen':{'assumed_face_width_mm':12,'module_mm':MODULE,
          'assumed_Lewis_form_factor':.30,'nominal_root_stress_MPa':force/(12*MODULE*.30),
          'stress_with_SF2_MPa':2*force/(12*MODULE*.30),
          'allowable_printed_strength_verified':False,'fatigue_creep_and_layer_direction_verified':False,
          'note':'Lewis estimate only, no printer-specific allowable stress. Z is NOT released for a 1 kg loaded run.'},
       'wireless_stop_screen':{'heartbeat_timeout_s_candidate':.25,
          'ideal_X_timeout_plus_deceleration_mm':12*.25+12**2/(2*40),
          'ideal_Y_timeout_plus_deceleration_mm':5*.25+5**2/(2*25),
          'driver_brake_and_sensor_latency_verified':False,
          'note':'Not a safety-rated stop calculation. Local target limits and a separate physical safety chain remain required.'},
       'battery_runtime_example':{'example_only':True,'assumed_Wh':55.5,'usable_fraction_assumed':.65,
          'hours_at_10_20_40_W':[55.5*.65/w for w in (10,20,40)],'pack_voltage_selected':False,
          'note':'This is NOT a measured runtime or a charging specification.'},
       'hardware_accepted':False,'manufacturing_release_allowed':False,
       'blockers':['Actual motor electrical/torque curves and measured mass',
          'Gearbox, independently engaging rail brake, battery/BMS/charger selection',
          'Printed tooth coupon, creep, backlash, pull-out and endurance tests',
          'Complete fastening, bearing, tolerance and local wiring review',
          'Independent safety chain and IO door hardware/firmware validation']}
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/'engineering_checks.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    print(json.dumps({k:r[k] for k in ('cad_empty_mass_estimate_kg','fully_loaded_mass_including_2kg_allowance_kg',
          'motor_targets','printed_Z_tooth_screen')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
