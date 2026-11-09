"""V03 modular rack-drive research prototype. No V02 output is changed.

Purchased safety, battery and camera envelopes are explicitly NOT selected hardware.
Printed Z teeth are an experimental drive, never a safety restraint.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'cad'/'v02'))
import asrs_v02 as v2
from gears import (MODULE, TEETH, PITCH, RADIUS, SEGMENT_LENGTH, RACK_PITCH_HEIGHT,
                   rack, pinion, z_rack, y_rack)

import cadquery as cq

OUT = ROOT/'model'/'V03'
MOTOR = ROOT/'stl'/'ZDT_X42_L48Motor.STEP'
DEPENDENCIES = [Path(__file__),Path(__file__).with_name('gears.py'),Path(v2.__file__),MOTOR]
FINGERPRINT = hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
box,cyl,fuse,drill,hz,hy,hx = v2.box,v2.cyl,v2.fuse,v2.drill,v2.hz,v2.hy,v2.hx


@dataclass(frozen=True)
class Design(v2.Design):
    column_pitch: float = 180.0


class Item(v2.Instance):
    def located(self, dx=0,dz=0,q=0,pin_lift=0,bin_q=None,io_open=0):
        group = {'xgear':'x','zgear':'z','ygear':'y','io_shutter':'fixed'}.get(self.group,self.group)
        base = v2.Instance(self.name,self.part,self.origin,group)
        if self.group in ('xgear','zgear','ygear'):
            distance,axis = {'xgear':(-dx,(0,0,1)),'zgear':(dz,(0,-1,0)),
                             'ygear':(q,(0,0,1))}[self.group]
            shape = self.part.shape.rotate((0,0,0),axis,math.degrees(distance/RADIUS))
            base.part = v2.Part(self.part.name,shape,self.part.material,self.part.process,
                                self.part.holes,self.part.note)
        result = base.located(dx,dz,q,pin_lift,bin_q)
        if self.group == 'io_shutter': result = result.translate((0,0,90*io_open))
        return result


def remove(m,predicate):
    m.items = [i for i in m.items if not predicate(i)]


def replace(m,old,new):
    for i in m.items:
        if i.part.name == old:i.part = new


def labelled_bin():
    s = v2.make_bin()
    # 32x32 mm paper marker fits between the rails, away from central latch mast.
    for xx in (-53,-19):
        s = s.fuse(box(xx,-60.5,19,2,2,38))
    s = s.fuse(box(-36,-60.5,19,36,2,2))
    return s.clean()


def battery_case():
    # 85x65x42 battery candidate + isolated 40x65 electronics bay, NOT a selected pack.
    shell = box(0,0,0,155,85,50).cut(box(0,0,3,149,79,50))
    shell = shell.fuse(box(17,0,3,2,79,45))
    for xx in (-72,72):
        for yy in (-37,37):
            shell = shell.fuse(box(xx,yy,3,8,8,45))
            shell = shell.cut(cyl(xx,yy,41,1.25,12))
    # Vents only open into controller bay, never straight into the battery bay.
    for yy in (-18,-6,6,18):
        shell = shell.cut(box(76,yy,18,6,6,12))
    shell = shell.cut(cyl(0,-45,15,4,10,(0,1,0)))
    for xx in (-60,60):
        for yy in (-25,25):shell = shell.cut(cyl(xx,yy,-1,2.2,5))
    for xx in (-50,0):
        for yy in (-35,35):shell=shell.cut(box(xx,yy,-1,12,3,5))
    return shell.clean()


def build_model():
    m = v2.build_model()
    old_x, m.x = m.x, 270.
    m.d = Design()
    obsolete = {'base','rack_rear_shear','x_belt','x_drive_pulley','x_idler_pulley','x_motor',
        'x_motor_mount','x_idler_pedestal','x_tension_adjuster','x_belt_clamp','x_clamp_backer',
        'z_screw','z_working_nut','z_safety_nut','z_nut_bridge','z_safety_cage',
        'z_fixed_bearing_housing','z_thrust_end_cap','z_bearing_hanger','z_fixed_radial_bearing',
        'z_thrust_abutment','z_shaft_collar','z_thrust_cross_pin','z_floating_bearing',
        'z_floating_bearing_cap','z_floating_radial_bearing','z_floating_pedestal','z_brake_motor',
        'z_coupling','y_belt','y_drive_pulley','y_idler_pulley','y_idler_axle','y_motor',
        'y_motor_spacer','y_idler_tension_carrier','y_tension_adjuster','y_belt_clamp'}
    obsolete_prefix = ('rail_beam_','x_rail_','rack_post_','rack_pedestal_','rack_foot_',
        'rear_panel_standoff_','guard_','x_motor_leg_','safety_nut_key_','z_thrust_bearing_',
        'y_clamp_nut_','x_stop_')
    remove(m,lambda i:i.name in obsolete or i.name.startswith(obsolete_prefix) or i.part.material=='guard')
    for i in m.items:
        xx,yy,zz = i.origin
        if i.group!='fixed':xx += m.x-old_x
        else:
            match = re.match(r'(?:stored_bin|cell|shelf_angle)_(\d)_',i.name)
            if match:
                c=int(match[1]);xx += m.d.x_positions[c]-v2.Design().x_positions[c]
        i.origin=(xx,yy,zz)
    m.allowed = {} # Old belt clamping exceptions no longer apply.
    x,D = m.x,m.deck

    # Base transport panels; precision rails are still continuous purchased parts.
    for j,(left,right) in enumerate(((-350,-30),(-30,390),(390,900))):
        s=box((left+right)/2,-75,0,right-left,590,6)
        p=m.part(f'Base_Panel_{j}',s,note='Metal plate. Panel joints do not make a traversable rail splice.')
        m.add(f'base_panel_{j}',p)
    for seam in (-30,390):
        hh=[hz(xx,yy,-1,5.5,6) for xx in (-20,20) for yy in (-12,12)]
        p=m.part('Base_Splice_60x40',drill(box(0,0,0,60,40,4),hh),holes=hh,
            note='Four M5 bolts; matched datum and dowel holes to be frozen before machining.')
        for yy in (-80,190):m.add(f'base_splice_{seam}_{yy}',p,(seam,yy,6))

    # Independent four-post rack columns with separate rear diaphragms.
    post=m.parts['2020_Rack_Z650']
    fh=[hz(a,b,-1,5.5,8) for a in (-9,9) for b in (-14,14)]
    fh += [hz(0,0,-1,5.5,8),hz(0,0,-1,9.5,6)]
    foot=m.part('Column_Foot_28x40',drill(box(0,0,0,28,40,6),fh),holes=fh)
    ph=[hz(a,b,-1,5.5,16) for a in (-9,9) for b in (-14,14)]
    ped=m.part('Column_Pedestal_28x40',drill(box(0,0,0,28,40,14),ph),holes=ph)
    for c,xx in enumerate(m.d.x_positions):
        ch=[hz(a,b,-1,6.5,8) for a in (-45,45) for b in (-55,55)]
        ch += [hz(-75,0,-1,6.2,8)]
        ch += [hz(side*75+a,yy+b-75,-1,4.2,8)
            for side in (-1,1) for a in (-9,9) for yy in (10,140) for b in (-14,14)]
        carrier=drill(box(0,0,0,178,170,6),ch)
        slot=v2.slot_y(0,0,-1,8,6.2,8).rotate((0,0,0),(0,0,1),90).translate((75,0,0))
        carrier=carrier.cut(slot)
        cp=m.part('Column_Carrier_RoundSlot',carrier,holes=ch,
            note='One 6.2 round receiver and one 8x6.2 X slot; four M6 mounting bolts. Machine locating fits after first assembly.')
        m.add(f'column_{c}_carrier',cp,(xx,75,6))
        for side in (-1,1):
            for yy in (10,140):
                at=(xx+side*75,yy)
                m.add(f'column_{c}_foot_{side}_{yy}',foot,(*at,26))
                m.add(f'column_{c}_pedestal_{side}_{yy}',ped,(*at,12))
                m.add(f'column_{c}_post_{side}_{yy}',post,(*at,32))
        ph=[hy(a,-1,z,5.5,5) for a in (-75,75) for z in (20,610)]
        panel=m.part('Column_Rear_Panel_170x630',drill(box(0,1.5,0,170,3,630),ph),holes=ph)
        m.add(f'column_{c}_rear_panel',panel,(xx,152,45))
        for a in (-75,75):
            for zz in (65,655):m.add(f'column_{c}_rear_standoff_{a}_{zz}',
                m.parts['Rear_Panel_Standoff_2'],(xx+a,150,zz))
        # Two reusable column-to-base locating studs; round + slot locating pattern.
        pin=m.part('Column_Datum_Pin_D6',cyl(0,0,0,3,12),'steel','purchased',
            note='One round H7 receiver, one diamond/slot receiver. Fit and positional tolerances pending.')
        for off in (-75,75):m.add(f'column_{c}_datum_{off}',pin,(xx+off,75,2))

    # Drill receiving/mounting holes into the correct transport panel, not floating pins.
    for item in m.items:
        if not item.name.startswith('base_panel_'):continue
        shape=item.part.shape;b=shape.BoundingBox()
        for xx in m.d.x_positions:
            for a in (-75,75):
                if b.xmin < xx+a < b.xmax:shape=shape.cut(cyl(xx+a,75,-1,3,8))
            for a in (-45,45):
                for yy in (20,130):
                    if b.xmin < xx+a < b.xmax:shape=shape.cut(cyl(xx+a,yy,-1,2.5,8))
        for seam in (-30,390):
            for a in (-20,20):
                for yy in (-80,190):
                    for off in (-12,12):
                        if b.xmin < seam+a < b.xmax:shape=shape.cut(cyl(seam+a,yy+off,-1,2.1,8))
        for xx in (-225,-75,75,225,375,525,675):
            for yy in (-285,-215):
                if b.xmin < xx < b.xmax:shape=shape.cut(cyl(xx,yy,-1,2.1,8))
        item.part=m.part(item.part.name+'_Located',shape,note=item.part.note)

    # Longer X datum bars/rails accommodate the independent IO bay at X=-150.
    bh=[hz(xx,0,19,2.5,7) for xx in range(-515,516,25)]
    bh += [hz(xx,0,-1,5.5,26) for xx in range(-475,426,150)]
    bh += [hz(xx,0,20,9.5,6) for xx in range(-475,426,150)]
    beam=m.part('X_Datum_Bar_1050',drill(box(0,0,0,1050,30,24),bh),holes=bh,
        note='Continuous metal datum; M3 rail taps and counterbored M5 attachment to base. Bolt lengths/head space require review.')
    rail_s,_=v2.rail_shape(12,8,1050,25)
    rail=m.part('MGN12_X1050',rail_s.rotate((0,0,0),(0,0,1),-90),'steel','purchased')
    xstop=m.part('X_Stop_Low_Profile',box(0,0,0,24,20,8),'rubber','purchased',
        note='Low-profile bumper contacts X plate below local power tray; metal backing and fasteners pending.')
    for yy in (-285,-215):
        m.add(f'x_beam_{yy}',beam,(250,yy,6))
        m.add(f'x_track_{yy}',rail,(250,yy,30))
        for xx in (-250,730):m.add(f'x_stop_{xx}_{yy}',xstop,(xx,yy,43))
    zstop=m.part('Z_Stop_Rear_Clearance',box(0,0,0,24,9,10),'rubber','purchased')
    replace(m,'Z_Stop_24x15x10',zstop)
    for i in m.items:
        if i.name.startswith('z_stop_'):
            xx,yy,zz=i.origin;i.origin=(xx,-236.5,zz)

    # Rack segment types, same tooth family on all axes, integer-pitch segment ends.
    rs=rack();pg=pinion()
    xr=m.part('Rack_M1p5_24T_X',rs.rotate((0,0,0),(1,0,0),-90),'PETG','print',
        note='24 pitches=113.097 mm, 20deg, 12 mm tooth face, four M3 holes. Print lateral face down; coupon first.')
    zr=m.part('Rack_M1p5_24T_Z',z_rack(rs),'PETG','print',note='Experimental printed lift teeth; independent metal catch mandatory.')
    yr=m.part('Rack_M1p5_24T_Y',y_rack(rs),'PETG','print',note='Same pitch/phase as X/Z; align on continuous metal backing.')
    xp=m.part('Pinion_M1p5_20T_X',pg.rotate((0,0,0),(0,0,1),math.degrees(-(x+240)/RADIUS)),
        'PETG','print',note='Sampled involute, 0.30 mm total nominal backlash, metal clamping hub required.')
    zp=m.part('Pinion_M1p5_20T_Z',pg.rotate((0,0,0),(0,0,1),math.degrees((D-65-85)/RADIUS))
        .rotate((0,0,0),(1,0,0),90),'PETG','print',note='Not a brake. Printed tooth failure must not release the lift.')
    bc=m.d.tray_y+m.d.eye_offset_y-50
    yp=m.part('Pinion_M1p5_20T_Y',pg.rotate((0,0,0),(0,0,1),math.degrees((bc+242)/RADIUS)),
        'PETG','print')
    for j in range(9):m.add(f'x_rack_{j}',xr,(-240+j*SEGMENT_LENGTH,-322,66))
    for j in range(5):m.add(f'z_rack_{j}',zr,(x-122,-268,85+j*SEGMENT_LENGTH),'x')
    for j in range(2):m.add(f'y_rack_{j}',yr,(x+70,-242+j*SEGMENT_LENGTH,D-19),'z')
    m.add('x_pinion',xp,(x,-299,60),'xgear')
    m.add('z_pinion',zp,(x-99,-262,D-65),'zgear')
    m.add('y_pinion',yp,(x+93,bc,D-25),'ygear')
    # Continuous metal backings carry segment screws; plastic joints do not carry frame loads.
    xh=[hy(-240+j*SEGMENT_LENGTH+t-270,-4,z,2.5,8)
        for j in range(9) for t in (6*PITCH,18*PITCH) for z in (4,26)]
    bx=m.part('X_Rack_Backbone',drill(box(0,0,0,1040,6,30),xh),holes=xh)
    m.add('x_rack_backbone',bx,(270,-325,51))
    zh=[hx(-3,y,j*SEGMENT_LENGTH+t,2.5,6)
        for j in range(5) for t in (6*PITCH,18*PITCH) for y in (-11,11)]
    bz=m.part('Z_Rack_Backbone',drill(box(0,0,0,4,30,566),zh),holes=zh)
    m.add('z_rack_backbone',bz,(x-124,-268,85),'x')
    bs=m.part('Z_Rack_StandOff',box(0,0,0,96,8,12))
    for zz in (100,625):m.add(f'z_rack_standoff_{zz}',bs,(x-78,-287,zz),'x')
    yh=[hx(-3,-242+j*SEGMENT_LENGTH+t+128.5,z,2.5,6)
        for j in range(2) for t in (6*PITCH,18*PITCH) for z in (4,26)]
    by=m.part('Y_Rack_Backbone',drill(box(0,0,0,4,227,30),yh),holes=yh)
    m.add('y_rack_backbone',by,(x+68,-128.5,D-34),'z')
    ys=m.part('Y_Rack_StandOff',box(0,0,0,25,12,6))
    for yy in (-220,-25):m.add(f'y_rack_standoff_{yy}',ys,(x+53.5,yy,D-46),'z')
    for i in m.items:
        if i.name.startswith('y_spine_spacer_'):
            xx,yy,zz=i.origin;i.origin=(xx,-217 if yy==-110 else -25,zz)
    sph=[hz(xx,yy,-1,2.5,8) for xx in (-13,13) for yy in range(-215,-34,20)]
    sph += [hz(xx,yy,-1,4.5,8) for xx in (-35,35) for yy in (-217,-25)]
    spine=m.part('Y_Spine_TwinGuide',drill(box(0,-119.5,0,82,211,6),sph),holes=sph)
    replace(m,'Y_Spine_82x211x6',spine)
    tube=m.parts['Tray_Al_Tube_25x25x2_L227']
    shortened=tube.shape.intersect(box(0,-121.25,-1,30,213.5,28))
    tube3=m.part('Tray_Tube_V03',drill(shortened,[hz(0,yy,-1,4.5,27) for yy in (-217,-25)]),
        note='Metal compression sleeves still required, including the new Y-spine end supports.')
    replace(m,tube.name,tube3)
    plug=m.parts['Tube_End_Plug']
    plug3=m.part('Tube_End_Plug_V03',drill(plug.shape,[hz(0,11,-12,4.5,25)]))
    replace(m,plug.name,plug3)

    # Use the user's complete 24-solid motor including the rear driver/connectors.
    raw=cq.importers.importStep(str(MOTOR)).val()
    normal=raw.translate((3.1098562568320687,4.685726853742248,-23)).rotate((0,0,0),(1,0,0),180)
    motors={}
    for axis,shape in [('X',normal.rotate((0,0,0),(1,0,0),180)),
                       ('Z',normal.rotate((0,0,0),(1,0,0),90)),
                       ('Y',normal.rotate((0,0,0),(1,0,0),180))]:
        p=v2.Part('ZDT_RealMotor_'+axis,shape,'purchased','purchased',[],
            'User STEP, 24 solids. Geometry only; voltage, mass, torque curve and brake not verified.')
        m.parts[p.name]=p;motors[axis]=p
    m.add('x_real_motor',motors['X'],(x,-299,86),'x')
    m.add('z_real_motor',motors['Z'],(x-99,-201,D-65),'z')
    m.add('y_real_motor',motors['Y'],(x+93,bc,D+36),'y')
    mount_h=[hz(a,b,-1,3.5,6) for a in (-15.5,15.5) for b in (-15.5,15.5)]+[hz(0,0,-1,23,6)]
    mount=m.part('Motor_Plate_50x50',drill(box(0,0,0,50,50,4),mount_h),holes=mount_h,
        note='31x31 M3 pattern; adjust mesh on slotted carrier. Confirm actual motor screw engagement.')
    m.add('x_motor_plate',mount,(x,-299,82),'x')
    zm=m.part('Z_Motor_Plate',mount.shape.rotate((0,0,0),(1,0,0),90))
    m.add('z_motor_plate',zm,(x-99,-246,D-65),'z')
    # A reduction allocation is necessary for the loss of the old low-lead screw's advantage.
    gearbox=cyl(0,0,0,21,45,(0,1,0)).cut(cyl(0,-1,0,4.2,47,(0,1,0)))
    gearbox=gearbox.cut(cyl(0,42.8,0,11.1,3,(0,1,0)))
    gb=m.part('Z_Reduction_10to1_CANDIDATE',gearbox,'purchased','candidate',
        note='10:1 planetary allocation OD42 L45, input5/output8. Ratio/efficiency/backlash/mount drawing unselected; not a brake.')
    m.add('z_reduction_candidate',gb,(x-99,-246,D-65),'z')
    outshaft=m.part('Z_Reducer_Output_Shaft_CANDIDATE',cyl(0,0,0,4,28,(0,-1,0)),
        'steel','candidate',note='8 mm output, 28 mm exposed candidate; integrate actual selected reducer drawing before fabrication.')
    m.add('z_reducer_output_candidate',outshaft,(x-99,-246,D-65),'z')
    m.add('y_motor_plate',mount,(x+93,bc,D-3),'y')
    yg=cyl(0,0,0,21,35).cut(cyl(0,0,-1,4.2,37)).cut(cyl(0,0,32.8,11.1,3))
    ygb=m.part('Y_Reduction_3to1_CANDIDATE',yg,'purchased','candidate',
        note='3:1 gearbox allocation, OD42 L35, input5/output8. Not selected; match actual drawing before manufacturing.')
    m.add('y_reduction_candidate',ygb,(x+93,bc,D+1),'y')
    yshaft=m.part('Y_Reducer_Output_CANDIDATE',cyl(0,0,0,4,28,(0,0,-1)),'steel','candidate')
    m.add('y_reducer_output_candidate',yshaft,(x+93,bc,D+1),'y')
    xl=m.part('X_Motor_Leg',box(0,0,0,6,16,31))
    for off in (-22,22):m.add(f'x_motor_leg_{off}',xl,(x+off,-299,51),'x')
    zlink=m.part('Z_Motor_Module_Link',fuse(box(-79,-237,-40,10,26,6),box(-70,-232,-40,10,8,6)))
    m.add('z_motor_module_link',zlink,(x,0,D),'z')

    # Y has two guide blocks to support the co-moving motor and local battery.
    m.add('y_rail_right',m.parts['MGN9_Rail_Y200'],(x+13,-125,D-40),'z')
    m.add('y_block_right',m.parts['MGN9H_Y'],(x+13,bc,D-40),'y')
    holes=[hz(xx+dx,yy,-1,3.5,6) for xx in (-13,13) for dx in (-7.5,7.5) for yy in (-8,8)]
    plate=drill(fuse(box(0,10,0,56,60,4),box(26,0,-9,4,16,13),
        box(140,0,-9,232,16,4),box(180,-45,-9,120,106,4)),holes)
    plate=drill(plate,[hz(xx,25,-1,3.5,6) for xx in (-10,10)])
    ypplate=m.part('Y_Module_Base',plate,holes=holes,note='Metal base, twin guides. Cantilever/moment must be checked under measured pack mass.')
    replace(m,'Y_Puller_Plate_46x60x4',ypplate)
    # Head module locates independently of its two M3 clamping screws.
    base3=m.part('Y_Module_Base_Located',drill(plate,[hz(xx,35,-1,3,6) for xx in (-10,10)]),
        note=ypplate.note+' Two 3 mm locating pin bores; confirm press fit after machining.')
    replace(m,ypplate.name,base3)
    mast=m.parts['Latch_Mast_36x92_L']
    ms=drill(mast.shape,[hz(-10,5,-27,3.2,6)])
    slot=v2.slot_y(0,0,-27,4.2,3.2,6).rotate((0,0,0),(0,0,1),90).translate((10,5,0))
    ms=ms.cut(slot)
    head=m.part('Latch_Mast_V03_RoundSlot',ms,holes=mast.holes,
        note='Removable head interface: two original M3 clamp screws, one round and one slotted D3 locating receiver.')
    replace(m,mast.name,head)
    hpin=m.part('Head_Locator_D3',cyl(0,0,0,1.5,9),'steel','purchased')
    for xx in (-10,10):m.add(f'head_locator_{xx}',hpin,(x+xx,bc+35,D-29),'y')
    yl=m.part('Y_Motor_Leg',box(0,0,0,6,40,32),note='Outboard metal cantilever bracket, clear of the full pinion swept circle.')
    m.add('y_motor_leg_outboard',yl,(x+115,bc,D-35),'y')
    # Metal hubs, not a printed friction fit on the 5 mm D shaft.
    hub=fuse(cyl(0,0,-2,12,2),cyl(0,0,0,6,12)).cut(cyl(0,0,-3,2.6,18))
    hub=drill(hub,[hz(a,0,-3,3.5,4) for a in (-9,9)])
    hp=m.part('Metal_Pinion_Hub_X',hub.rotate((0,0,0),(0,0,1),math.degrees(-(x+240)/RADIUS)),
        'steel','purchased',note='Candidate flange hub, 5 mm clamp shaft; actual clamp/screws and torque proof pending.')
    m.add('x_pinion_hub',hp,(x,-299,60),'xgear')
    zhub=hub.cut(cyl(0,0,-3,4.1,18))
    hzpart=m.part('Metal_Pinion_Hub_Z',zhub.rotate((0,0,0),(0,0,1),math.degrees((D-65-85)/RADIUS))
        .rotate((0,0,0),(1,0,0),90),'steel','purchased',note=hp.note)
    m.add('z_pinion_hub',hzpart,(x-99,-262,D-65),'zgear')
    hyp=m.part('Metal_Pinion_Hub_Y',zhub.rotate((0,0,0),(0,0,1),math.degrees((bc+242)/RADIUS)),
        'steel','purchased',note=hp.note)
    m.add('y_pinion_hub',hyp,(x+93,bc,D-25),'ygear')

    # Local power nodes: rigidly attached to each axis' moving module.
    case=m.part('Local_Power_Case',battery_case(),'PETG','print',
        note='Pack candidate 85x65x42 + separate ESP32 bay. No battery, BMS, charger or voltage selection is implied.')
    lh=[hz(a,b,-1,2.8,5) for a in (-72,72) for b in (-37,37)]
    lid=m.part('Local_Power_Lid',drill(box(0,0,0,155,85,3),lh),'PETG','print',lh)
    pack=m.part('Battery_Candidate_85x65x42',box(0,0,0,85,65,42),'purchased','candidate',
        note='Packaging allocation ONLY. Cell chemistry, voltage, capacity, current, mass, BMS and enclosure fire behaviour pending.')
    esp=m.part('ESP32_Controller_Candidate',box(0,0,0,40,55,12),'purchased','candidate',
        note='Board envelope, local watchdog/limit inputs/driver interface still to be implemented.')
    tray_h=[hz(xx,yy,-1,3.3,6) for xx in (-60,60) for yy in (-25,25)]
    tray=m.part('Power_Module_Tray',drill(box(0,0,0,165,90,4),tray_h),holes=tray_h,
        note='Four M4 tapped case attachment positions; local pack disconnect only when motion is isolated and Z mechanically supported.')
    for axis,origin,group in [('X',(x+175,-250,55),'x'),('Z',(x+10,-180,D-104),'z'),
                              ('Y',(x+180,bc-90,D+34),'y')]:
        xx,yy,zz=origin
        if axis=='X':
            mt=m.part('X_Power_Module_Tray',fuse(tray.shape,box(-90,35,0,80,20,4)))
        elif axis=='Z':
            mt=m.part('Z_Power_Module_Tray',fuse(tray.shape,box(-10,-45,0,130,8,4),
                box(-10,-46,4,130,4,12)))
        else:mt=tray
        m.add(axis.lower()+'_power_tray',mt,(xx,yy,zz-4),group)
        m.add(axis.lower()+'_power_case',case,origin,group)
        m.add(axis.lower()+'_power_lid',lid,(xx,yy,zz+50),group)
        m.add(axis.lower()+'_battery_candidate',pack,(xx-26.5,yy,zz+4),group)
        m.add(axis.lower()+'_esp32_candidate',esp,(xx+43,yy,zz+4),group)
    yleg=m.part('Y_Power_Module_Leg',box(0,0,0,8,24,65))
    for xx in (145,225):m.add(f'y_power_leg_{xx}',yleg,(x+xx,bc-90,D-35),'y')

    # Independent metal safety track and candidate spring-applied rail brake.
    sh=[hx(-5,0,z,4.2,10) for z in range(15,541,25)]
    safety=m.part('Independent_Steel_Safety_Track',drill(box(0,0,0,6,30,566),sh),'steel',holes=sh,
        note='Separate from printed rack. Hole pattern is for maintenance support, not an automatic ratchet.')
    m.add('z_independent_safety_track',safety,(x+90,-268,85),'x')
    brake=box(0,0,0,36,50,50).cut(box(0,0,-1,6.4,30.4,52))
    bp=m.part('NC_Rail_Brake_CANDIDATE',brake,'safety','candidate',
        note='Unselected commercial normally-engaged brake envelope. Not modelled jaws or a certified catch. NO loaded Z operation yet.')
    m.add('z_brake_candidate',bp,(x+90,-268,D-90),'z')
    sl=m.part('Safety_Track_Link',box(0,0,0,27,20,12))
    for zz in (85,625):m.add(f'safety_track_link_{zz}',sl,(x+73.5,-268,zz),'x')
    bl=m.part('Brake_Module_Link',box(0,0,0,7,25,8))
    m.add('brake_module_link',bl,(x+68.5,-240.5,D-43),'z')

    # Removable tags live on the box, while fixed reference tags live on each rack column.
    binp=m.part('Bin_V03_Marker_Rails',labelled_bin(),'PETG','print',
        note='32x32 mm AprilTag card, front-left offset X=-36 Z=38, rails clear the centre latch. ID is not a safety signal.')
    replace(m,'Bin_110x120_TowEye',binp)
    tag=m.part('Marker_Card_32mm',box(0,0,0,32,.2,32),'purchased','print_paper',
        note='AprilTag36h11, 32 mm OUTER card including quiet margin; black border square=25.6 mm. Use the latter for pose estimation.')
    for i in list(m.items):
        if i.part.name==binp.name:
            xx,yy,zz=i.origin;m.add(i.name+'_marker',tag,(xx-36,yy-61.2,zz+22),i.group)
    ref_mount=m.part('Column_Reference_Tag_Mount',box(0,0,0,36,2,40),'PETG','print',
        note='Fixed reference, distinct ID from box tags. Calibrate column-to-machine transform after reassembly.')
    for c,xx in enumerate(m.d.x_positions):
        m.add(f'column_{c}_reference_mount',ref_mount,(xx-78,-1,250))
        m.add(f'column_{c}_reference_tag',tag,(xx-78,-2.2,254))
    cs=fuse(box(0,0,0,32,6,32),cyl(0,3,16,6,12,(0,1,0)))
    cs=drill(cs,[hy(a,-4,zz,2.2,8) for a in (-12,12) for zz in (4,28)])
    camera=m.part('Camera_CANDIDATE_32x32',cs,
        'purchased','candidate',note='Lens-front mechanical distance about 66..209 mm; camera intrinsics, camera/tool extrinsics and lighting calibration pending.')
    m.add('tool_camera_candidate',camera,(x-36,-220,D+22),'z')
    mount=fuse(box(21,0,-30,16,4,55),box(8,0,18,50,4,4),box(0,0,22,40,4,36))
    for a in (-12,12):
        for zz in (26,50):mount=mount.fuse(cyl(a,2,zz,2.5,1,(0,1,0)))
    for a in (-12,12):
        for zz in (26,50):
            slot=fuse(cyl(a,-3,zz-.75,1.1,8,(0,1,0)),cyl(a,-3,zz+.75,1.1,8,(0,1,0)),
                box(a,1,zz-.75,2.2,8,1.5))
            mount=mount.cut(slot)
    cm=m.part('Camera_Slotted_Mount',mount,
        'PETG','print',note='M3 slotted adjustment and cable/antenna clearance must match selected camera.')
    m.add('tool_camera_mount',cm,(x-36,-226,D),'z')

    add_io(m)
    add_guards(m)
    # Actual instance implementation includes gear rotation and IO shutter state.
    m.items=[Item(i.name,i.part,i.origin,i.group) for i in m.items]
    used={i.part.name for i in m.items};m.parts={k:p for k,p in m.parts.items() if k in used}
    return m


def add_io(m):
    xx,z=-150.,200.
    p=m.part('IO_Deck',v2.deck_plate()[0],'PETG','print',note='Single-box exchange nest, human access from left; not an extra storage cell.')
    m.add('io_deck',p,(xx,65,z-4))
    leg=m.part('IO_Stand_Leg',box(0,0,0,20,20,170))
    for a in (-65,65):
        for yy in (10,140):m.add(f'io_leg_{a}_{yy}',leg,(xx+a,yy,26))
    frame=fuse(box(0,50,0,150,20,6),box(0,105,0,150,20,6),
        box(-65,75,0,10,110,6),box(65,75,0,10,110,6))
    beam=m.part('IO_Metal_Deck_Frame',frame,note='Joined metal support frame; manufacturing joint detail pending, not a printed bridge.')
    m.add('io_deck_frame',beam,(xx,0,190))
    # Inner shutter moves up by 90 mm only while the outer door is closed/locked.
    gate=m.part('IO_Inner_Shutter',box(0,0,0,250,3,104),'guard','cut_panel',
        note='Manual prototype gate; powered latch/dual door interlock not implemented. Open pose +90 mm.')
    m.add('io_inner_shutter',gate,(xx,-6,194),'io_shutter')
    gs=box(0,0,0,8,8,204).cut(box(-2,1,-1,6,3.6,206))
    guide=m.part('IO_Shutter_Guide_Right',gs,'PETG','print')
    guideleft=m.part('IO_Shutter_Guide_Left',gs.rotate((0,0,0),(0,1,0),180).translate((0,0,204)),
        'PETG','print')
    m.add('io_shutter_guide_right',guide,(xx+125,-7,186))
    m.add('io_shutter_guide_left',guideleft,(xx-125,-7,186))
    header_shape=fuse(box(0,4,0,260,8,4),box(-125,-1.5,0,8,19,4),box(125,-1.5,0,8,19,4))
    header=m.part('IO_Shutter_Header',header_shape)
    m.add('io_shutter_header',header,(xx,0,390))
    # Human opening is on left side, not into the gantry aisle.
    side=m.part('IO_Outer_Door',box(0,0,0,3,138,100),'guard','cut_panel',
        note='Hinged left-side access; outer and inner doors must never both permit access.')
    m.add('io_outer_door',side,(-235,69,190))
    # Reach-through tunnel to the OUTSIDE of the main enclosure, not a door trapped inside it.
    tunnel=m.part('IO_Access_Tunnel_Horizontal',box(0,0,0,113.5,138,3),'guard','cut_panel')
    for zz in (187,290):m.add(f'io_tunnel_horizontal_{zz}',tunnel,(-293.25,69,zz))
    tw=m.part('IO_Access_Tunnel_Side',box(0,0,0,113.5,3,106),'guard','cut_panel')
    for yy in (-1.5,139.5):m.add(f'io_tunnel_side_{yy}',tw,(-293.25,yy,187))
    roof=m.part('IO_Roof',box(0,0,0,260,153,3),'guard','cut_panel')
    m.add('io_roof',roof,(xx,76.5,394))
    wall=m.part('IO_Rear_Wall',box(0,0,0,170,3,198),'guard','cut_panel')
    m.add('io_rear_wall',wall,(xx,151.5,196))
    sw=box(0,0,0,3,154.5,198).cut(box(0,-68.75,194,5,8,6))
    sw=sw.cut(box(0,-74.25,98,5,3,102)).cut(box(0,-74.25,-7,5,3,9))
    sidewall=m.part('IO_Right_Wall',sw,'guard','cut_panel')
    m.add('io_right_wall',sidewall,(-63.5,72.75,196))
    us=box(0,0,0,250,3,100)
    for a in (-125,125):us=us.cut(box(a,0,96,8,5,6))
    upper=m.part('IO_Upper_Fixed_Shield',us,'guard','cut_panel',
        note='Overlaps the closed shutter by 4 mm; prevents reaching over the inner door through the human port.')
    m.add('io_upper_fixed_shield',upper,(xx,-1.5,294))
    lower=m.part('IO_Lower_Fixed_Shield',box(0,0,0,170,3,8),'guard','cut_panel')
    m.add('io_lower_fixed_shield',lower,(xx,-1.5,190))
    lu=box(0,0,0,3,150,104).cut(box(0,-71,100,5,8,6))
    leftupper=m.part('IO_Left_Upper_Wall',lu,'guard','cut_panel')
    m.add('io_left_upper_wall',leftupper,(-235,75,290))
    external=m.part('IO_External_Reference_Card',m.parts['Marker_Card_32mm'].shape.rotate((0,0,0),(0,0,1),-90),
        'purchased','print_paper',note='AprilTag36h11 ID200 on the outside left guard, not a box ID.')
    m.add('io_external_reference_tag',external,(-353.2,69,310))
    stop=m.part('IO_Box_Back_Stop',box(0,0,0,110,3,8),'PETG','print')
    m.add('io_back_stop',stop,(xx,128.5,200))
    sensor=m.part('Box_Presence_Sensor_CANDIDATE',box(0,0,0,12,12,20),'purchased','candidate')
    m.add('io_presence_sensor',sensor,(xx+70,90,205))


def add_guards(m):
    # Separate frame, removable panels. Human IO access has its own closed tunnel.
    post=m.part('Guard_Post_740',v2.extrusion(20,740,'Z'))
    cross=m.part('Guard_Cross_1200',v2.extrusion(20,1200,'X'))
    side=m.part('Guard_Side_520',v2.extrusion(20,520,'Y'))
    for xx in (-325,875):
        for yy in (-345,195):m.add(f'guard_post_{xx}_{yy}',post,(xx,yy,6))
        m.add(f'guard_side_top_{xx}',side,(xx,-75,746))
    for yy in (-345,195):m.add(f'guard_cross_{yy}',cross,(275,yy,746))
    for yy in (-371.5,221.5):
        p=m.part(f'Guard_Panel_Y{yy}',box(275,yy,0,1250,3,766),'guard','cut_panel')
        m.add(f'guard_panel_y{yy}',p)
    for xx in (-351.5,901.5):
        shape=box(xx,-75,0,3,590,766)
        if xx<0:shape=shape.cut(box(xx,69,190,5,138,100))
        p=m.part(f'Guard_Panel_X{xx}',shape,'guard','cut_panel')
        m.add(f'guard_panel_x{xx}',p)
    p=m.part('Guard_Roof',box(275,-75,766,1256,596,3),'guard','cut_panel')
    m.add('guard_roof',p)


def export(m,out=OUT):
    for sub in ('parts','stl','viewing'): (out/sub).mkdir(parents=True,exist_ok=True)
    assembly=cq.Assembly(name='ASRS_V03_Rack_Prototype')
    for i in m.items:
        assembly.add(i.located(),name=i.name,color=cq.Color(*v2.COLORS.get(i.part.material,(.6,.6,.6))))
    assembly.save(str(out/'ASRS_Modular_V03.step'))
    # No glass panels in the simple viewer, but the internal safety geometry remains.
    view=cq.Compound.makeCompound([s for i in m.items if i.part.material!='guard' for s in i.located().Solids()])
    cq.exporters.export(view,str(out/'viewing'/'ASRS_V03_INTERIOR_VIEW.step'))
    rows=[]
    for p in m.parts.values():
        cq.exporters.export(p.shape,str(out/'parts'/(p.name+'.step')))
        if p.process=='print':
            cq.exporters.export(p.shape,str(out/'stl'/(p.name+'.stl')),tolerance=.03,angularTolerance=.10)
        b=p.shape.BoundingBox()
        rows.append({'name':p.name,'quantity':sum(i.part.name==p.name for i in m.items),
            'material':p.material,'process':p.process,'solids':len(p.shape.Solids()),
            'volume_mm3':p.shape.Volume(),'extents_mm':[b.xlen,b.ylen,b.zlen],'note':p.note})
    manifest={'fingerprint':FINGERPRINT,'units':'mm','parts':rows,
        'instances':[{'name':i.name,'part':i.part.name,'origin_mm':i.origin,'group':i.group} for i in m.items],
        'storage_coordinates':[[c,r,xx,zz] for c,xx in enumerate(m.d.x_positions) for r,zz in enumerate(m.d.decks)],
        'io_coordinate_mm':[-150,65,200],'metal_safety_brake_selected':False,
        'battery_selected':False,'hardware_accepted':False,'manufacturing_release_allowed':False}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'BOM.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['part','quantity','material','process','note'])
        for p in rows:w.writerow([p[k] for k in ('name','quantity','material','process','note')])
    print(f'EXPORTED {len(rows)} part types / {len(m.items)} instances',flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--export',action='store_true');args=ap.parse_args()
    m=build_model()
    if args.export:export(m)
    bad,accepted=v2.collisions(m.items,m.allowed)
    report={'fingerprint':FINGERPRINT,'unexpected_static_collisions':bad,'explicit_contacts':accepted,
        'static_pass':not bad,'hardware_accepted':False,'manufacturing_release_allowed':False}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'static_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'part_types':len(m.parts),'instances':len(m.items),'collisions':bad},indent=2),flush=True)
    return int(bool(bad))


if __name__=='__main__':raise SystemExit(main())
