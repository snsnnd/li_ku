"""C04: converge C03 architecture; sourced clamps, screw tensioners, explicit stacks.

Mechanical design-freeze candidate, NOT hardware/safety/loaded-run acceptance.
All previous deliveries are immutable inputs, never overwritten.
"""
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

import cadquery as cq
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'cad/corexy_mvp'))
import corexy_mvp as prior
v2=prior.v2
box,cyl,fuse,drill,hz,hy,hx=prior.box,prior.cyl,prior.fuse,prior.drill,prior.hz,prior.hy,prior.hx
BASE=prior.OUT
OUT=ROOT/'model/CoreXY_Final_C04'
DEPENDENCIES=[Path(__file__),*prior.DEPENDENCIES,BASE/'manifest.json',*sorted((BASE/'parts').glob('*.step'))]
FINGERPRINT=hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in DEPENDENCIES)).hexdigest()
HOME_X,HOME_Y,CELL_Z,IO_Z=prior.HOME_X,prior.HOME_Y,prior.CELL_Z,prior.IO_Z
END=35.
CLAMP_SOURCE='https://www.phidgets.com/?prodid=839'


@dataclass
class Item(prior.Item):
    def located(self,dx=0,dy=0,dz=0,door=0,bin_pose=None,tension_a=0,tension_b=0,fast_belt=False):
        if not (0<=tension_a<=2 and 0<=tension_b<=2):raise ValueError('Tension slider outside0..2mm geometry stroke')
        if self.group=='belt':
            axis=self.name[-1];s=belt_shape(axis,HOME_X+dx,HOME_Y+dy,tension_a if axis=='A' else tension_b,not fast_belt)
            return s.translate(self.origin)
        s=super().located(dx,dy,dz,door,bin_pose)
        if self.name.startswith(('terminal_A_L_','terminal_B_L_')):
            s=s.translate((tension_a if self.name.startswith('terminal_A') else tension_b,0,0))
        if self.name in ('motor_A_pinch','motor_B_pinch'):
            axis=self.name[6];centre=find_motor(axis)
            advance=dx+dy if axis=='A' else -dx+dy
            s=s.rotate((*centre,0),(*centre,1),360*advance/40)
        return s


class Model(prior.Model):
    def add(self,name,p,origin=(0,0,0),group='fixed'):
        if any(i.name==name for i in self.items):raise ValueError('Duplicate '+name)
        i=Item(name,p,origin,group);self.items.append(i);return i


def find_motor(axis):return (-prior.W,prior.REAR_A) if axis=='A' else (prior.W,prior.REAR_B)


def find(m,name):return next(i for i in m.items if i.name==name)


def joint(m,a,b,note):m.joints.append({'a':a,'b':b,'purpose':note,'strength_verified':False})


def bolt(m,size,length,direction='down',head=None):
    minor={2:1.5,3:2.4,4:3.1,5:3.9};od={2:3.8,3:5.5,4:7,5:8.5}
    h=head if head is not None else {2:2,3:3,4:4,5:5}[size]
    s=fuse(cyl(0,0,-length,minor[size]/2,length),cyl(0,0,0,od[size]/2,h))
    # Socket recess makes tool access explicit, rather than a featureless cap.
    socket=cq.Workplane('XY').polygon(6,{2:1.5,3:2.5,4:3,5:4}[size]*2/math.sqrt(3)).extrude(h*.65).val().translate((0,0,h*.4))
    s=s.cut(socket)
    if direction!='down':
        ax,angle={'up':((1,0,0),180),'forward':((1,0,0),-90),'backward':((1,0,0),90),
                  'left':((0,1,0),90),'right':((0,1,0),-90)}[direction]
        s=s.rotate((0,0,0),ax,angle)
    return m.part(f'C04_M{size}x{length}_H{h}_{direction}',s,'steel','purchased',
        note=f'Nominal M{size}x{length}, capOD{od[size]}h{h}, thread MINOR diameter envelope. Socket illustrated; actual standard/grade/torque supplier-confirmed. Not a thread manufacturing profile.')


def washer(m,size,outer,thickness=1):
    return m.part(f'C04_Washer_M{size}_OD{outer}_H{thickness}',cyl(0,0,0,outer/2,thickness).cut(cyl(0,0,-1,(size+.4)/2,thickness+2)),'steel','purchased')


def cut_world(m,name,holes,tag):
    i=find(m,name);ox,oy,oz=i.origin
    local=[((x-ox,y-oy,z-oz),axis,d,length) for (x,y,z),axis,d,length in holes]
    p=i.part;i.part=m.part(p.name+'_'+tag,drill(p.shape,local),p.material,p.process,[*p.holes,*local],p.note)


def load_base():
    manifest=json.loads((BASE/'manifest.json').read_text());audit=json.loads((BASE/'delivery_audit.json').read_text())
    if manifest['fingerprint']!=prior.FINGERPRINT or not audit['architecture_geometry_review_package_pass']:raise RuntimeError('C03 baseline stale/failed')
    m=Model()
    for r in manifest['parts']:
        s=cq.importers.importStep(str(BASE/'parts'/(r['code']+'.step'))).val()
        m.parts[r['name']]=v2.Part(r['name'],s,r['material'],r['process'],r['holes'],r['note'])
    for r in manifest['instances']:m.add(r['name'],m.parts[r['part']],tuple(r['origin_mm']),r['group'])
    m.joints=list(manifest['joints'])
    return m


def belt_shape(axis,x=HOME_X,y=HOME_Y,adjust=0,solid=True):
    W,R=prior.W,prior.R;rear=prior.REAR_A if axis=='A' else prior.REAR_B;front=prior.FRONT
    left=x-END+adjust;right=x+END
    if axis=='A':
        a,b,c,d,e=prior.belt_centres(axis,y)
        parts=[prior.segment((left+9,y+R),(-W,y+R)),prior.sector(a,90,180),prior.segment((-W-R,y),(-W-R,rear)),
            prior.sector(b,180,270),prior.segment((-W,rear-R),(W+2*R,rear-R)),prior.sector(c,270,360),
            prior.segment((W+3*R,rear),(W+3*R,front)),prior.sector(d,0,180),prior.segment((W+R,front),(W+R,y)),
            prior.sector(e,0,-90),prior.segment((W,y-R),(right-9,y-R))]
    else:
        a,b,c,d,e=prior.belt_centres(axis,y)
        parts=[prior.segment((right-9,y+R),(W,y+R)),prior.sector(a,90,0),prior.segment((W+R,y),(W+R,rear)),
            prior.sector(b,0,-90),prior.segment((W,rear-R),(-W-2*R,rear-R)),prior.sector(c,270,180),
            prior.segment((-W-3*R,rear),(-W-3*R,front)),prior.sector(d,180,0),prior.segment((-W-R,front),(-W-R,y)),
            prior.sector(e,180,270),prior.segment((-W,y-R),(left+9,y-R))]
    return fuse(*parts) if solid else cq.Compound.makeCompound(parts)


def free_length(axis,x,y,adjust=0):return prior.belt_length(axis,x,y)-40+18+adjust


def terminal(m,axis,side):
    # Vendor tooth+back plates18x18.8x4; bolt grid10x9.4. Both belt
    # tangent lines and its full6mm width remain unchanged. No invented GT2 teeth.
    is_top=(axis=='A' and side=='L') or (axis=='B' and side=='R')
    sign=1 if is_top else -1
    x=HOME_X+(-END if side=='L' else END);y=HOME_Y+sign*prior.R;mid=prior.BELT_Z[axis]+3
    low=mid-9.4
    stem_h=124-low
    # Canonical assembly with rear at+Y; mirror around X for the lower tangent.
    p=m.part('C04_Clamp_Receiver_'+axis,box(0,8.7,0,18,8,stem_h),holes=[],
        note='Metal receiver behind sourcedTRM4226 tooth plate. TwoM3 top anchors, fourM2x12 cap screws; belt teeth defined ONLY by supplier part, not this flat envelope.')
    hh=[hy(a,4.6,z+9.4,1.6,8.2) for a in (-5,5) for z in (-4.7,4.7)]
    hh += [hz(a,10.7,stem_h-9,2.5,10) for a in (-5,5)]
    if side=='L':hh += [hx(-4,6.7,118-low,2.5,14)]
    shape=drill(p.shape,hh)
    if sign==-1:shape=shape.mirror('XZ')
    metadata=hh if sign==1 else [((x,-y,z),(a,-b,c),d,length) for (x,y,z),(a,b,c),d,length in hh]
    receiver=m.part(f'C04_Receiver_{axis}_{side}',shape,holes=metadata,note=p.note+(' LEFT:slot travel0..2mm; M3 pull screw atZ118, topanchors4mm off pull axis to avoid intersecting screws. Lock two top bolts after tensioning.' if side=='L' else ' RIGHT:fixed receiver.'))
    prefix=f'terminal_{axis}_{side}_'
    m.add(prefix+'receiver',receiver,(x,y,low),'xy');joint(m,prefix+'receiver','xy_plate','Two M3x16, recessed cap heads; slot locks provide holding, pull screw is adjuster not sole lock')
    tooth=box(0,2.7,-9.4,18,4,18.8);back=box(0,-2.7,-9.4,18,4,18.8)
    holes=[hy(a,-5,z,2.4,10) for a in (-5,5) for z in (-4.7,4.7)]
    tooth=drill(tooth,holes);back=drill(back,holes)
    back=drill(back,[hy(a,-4.8,z,4.4,2.1) for a in (-5,5) for z in (-4.7,4.7)])
    if sign==-1:tooth=tooth.mirror('XZ');back=back.mirror('XZ')
    for label,s in [('tooth',tooth),('cap',back)]:
        p=m.part(f'C04_TRM4226_{label}_Side{sign}',s,'aluminum','purchased_sourced',
            note='PhidgetsTRM4226_0 mechanical drawing:18x18.8x4,4holesØ2.4±.2 on10x9.4 grid; backplate counterboresØ4.4/depth2. '+
                 'Nominal fit envelope ONLY; procure actual GT2M-06 toothplate and backplate; do NOT manufacture tooth form from smooth CAD. M2x12 used with positive receiver pocket/location, proof test required. '+CLAMP_SOURCE)
        m.add(prefix+label,p,(x,y,mid),'xy')
    joint(m,prefix+'tooth',prefix+'receiver','Sourced metal toothplate seated on receiver, fourM2 screws; positive tooth profile from supplier')
    for a in (-5,5):
        for z in (-4.7,4.7):
            m.add(prefix+f'pinch_{a}_{z}',bolt(m,2,12,'backward' if sign==1 else 'forward'),(x+a,y-sign*2.7,mid+z),'xy')
    # Recessed caps stay inside the outer plate face, avoiding the other layer.
    m.allow(prefix+'tooth','belt_'+axis,'Sourced GT2 teeth engage belt; nominal flat envelopes exclude microscopic tooth contact. Actual clamp pullout/endurance must be tested.')
    for a in (-5,5):m.add(prefix+f'lock_{a}',bolt(m,3,16),(x+a,y+sign*10.7,132.9),'xy')
    if side=='L':
        # A fixed pull-lug behind the clamp, above the belt; two vertical screws
        # stay5mm off the pull-screw axis, never crossing its bore.
        lx=HOME_X-13;ly=y+sign*6.7
        h=[hx(-5,0,8,3.4,10)]+[hz(0,b,-1,2.5,16) for b in (-5,5)]
        lug=m.part('C04_Tension_Pull_Lug',drill(box(0,0,0,8,14,14),h),holes=h,
            note='Metal fixed lug seated on XYplate undersideZ124. M3 pull screwZ118; two M3 vertical anchors atY±5 avoid crossing horizontal screw. Full slider stroke0..2, then lock receiver bolts.')
        m.add(f'tension_{axis}_lug',lug,(lx,ly,110),'xy');joint(m,f'tension_{axis}_lug','xy_plate','Two M3x20 top recessed screws, positive seated metal pull-lug')
        for b in (-5,5):m.add(f'tension_{axis}_mount_{b}',bolt(m,3,20),(lx,ly+b,132.9),'xy')
        w=washer(m,3,7)
        wp=m.part('C04_M3_Washer_X',w.shape.rotate((0,0,0),(0,1,0),90),'steel','purchased')
        m.add(f'tension_{axis}_washer',wp,(HOME_X-9,ly,118),'xy')
        m.add(f'tension_{axis}_pull',bolt(m,3,25,'left'),(HOME_X-8,ly,118),'xy')
    return x,y,sign


def build_model():
    m=load_base();removed={i.name for i in m.items if i.name.startswith('clamp_')}
    m.items=[i for i in m.items if i.name not in removed]
    m.joints=[j for j in m.joints if j['a'] not in removed and j['b'] not in removed]
    # Verify drive-hub engagement instead of relying on the6mm upper hub overlap.
    # Raise B motor six mm, leave both belt planes and all idler paths unchanged.
    for axis in ('A','B'):
        xx,yy=find_motor(axis);extra=6 if axis=='B' else 0
        find(m,'motor_'+axis).origin=(xx,yy,78+extra)
        foot=box(0,0,0,76,96,6)
        foot=foot.cut(box((-1 if axis=='A' else 1)*2*prior.R,45 if axis=='A' else -45,-1,28,26,8))
        stand=fuse(foot,box(-32,0,6,8,64,66+extra),box(32,0,6,8,64,66+extra),box(0,0,72+extra,76,64,4))
        holes=[hz(a,b,-1,5.5,8) for a in (-32,32) for b in (-40,40)]
        holes += [hz(a,b,71+extra,3.5,7) for a in (-15.5,15.5) for b in (-15.5,15.5)]+[hz(0,0,71+extra,23,7)]
        find(m,'motor_stand_'+axis).part=m.part('C04_Motor_Stand_'+axis,drill(stand,holes),holes=holes,
            note=f'Metal stand, faceZ{78+extra}; base76x96 with opposite-idler clearance notch. Four M5x12 accessible outside legs. B face raised6mm: total shaft-in-pulley support now12mm, not6; lower CLAMP HUB itself remains6mm long. Supplier conformity and torque proof required.')
        for a in (-15.5,15.5):
            for b in (-15.5,15.5):find(m,f'motor_{axis}_flange_{a}_{b}').origin=(xx+a,yy+b,82+extra)
        for a in (-32,32):
            for b in (-40,40):m.add(f'motor_{axis}_base_{a}_{b}',bolt(m,5,12),(xx+a,yy+b,12))
        # Purchased clamping pulley: explicit shaft bore/slit/pinch fastener.
        i=find(m,'motor_'+axis+'_pulley')
        s=fuse(cyl(0,0,0,9,1.5),cyl(0,0,1.5,prior.INNER-.12,6),cyl(0,0,7.5,9,1.5),cyl(0,0,-6,8,6))
        s=s.cut(cyl(0,0,-7,2.5,18)).cut(box(0,5,-6.1,.6,10,6.1))
        hh=[hx(-10,5.5,-3,3.4,10),hx(0,5.5,-3,2.5,10)]
        s=drill(s,hh)
        i.part=m.part('C04_GT2_20T_D5_SplitClamp',s,'purchased','purchased_specified',holes=hh,
            note='Purchase metal GT2/20T/6mm with LOWER splitclamp hub:OD16,length6,bore5H7,slit0.6,M3x12 atY5.5/Z-3. Envelope excludes proprietary GT2 tooth form. Vendor exact clamp/bore/torque drawing required, do not cut teeth from CAD.')
        p=bolt(m,3,12,'right');s=p.shape.translate((-8,5.5,-3))
        pinch=m.part('C04_Pulley_M3x12_Pinch',s,'steel','purchased',note='M3x12 split-collar pinch; rotates with motor pulley. Actual tightening torque and torque-slip test required.')
        m.add('motor_'+axis+'_pinch',pinch,i.origin,'fixed')
    # Explicit bearing inner-ring support and shoulder head sockets.
    for i in list(m.items):
        if i.name.startswith('idler_') and i.name.endswith('_axle'):
            s=i.part.shape;b=s.BoundingBox()
            socket=cq.Workplane('XY').polygon(6,2.5*2/math.sqrt(3)).extrude(2).val().translate((0,0,b.zmax-2))
            i.part=m.part(i.part.name+'_C04_socket',s.cut(socket),'steel','machined',
                note='Custom40Cr tempered shoulder axle, yield>=640MPa supplier-certified; D5h6, M5x0.8-6g x8, root fillet<=0.2, headOD9h3/hex2.5. Threads shown minor. Inner-ring stack/preload and physical rating not accepted.')
            if i.group=='fixed':
                axis=i.name.split('_')[1];base_z=prior.BELT_Z[axis]-1.5
                w=washer(m,5,8)
                m.add(i.name+'_topwasher',w,(i.origin[0],i.origin[1],base_z+8))
        if i.name.startswith('idler_') and i.name.endswith('_stand'):
            h=[hz(a,b,-1,3.4,8) for a in (-8,8) for b in (-7,7)]+[hz(0,0,60,4.2,16)]
            s=fuse(box(0,0,0,26,24,6),box(0,0,6,10,10,68))
            i.part=m.part('C04_Fixed_Idler_Stand',drill(s,h),holes=h,
                note='Metal standZ6..80,26x24foot, four M3x12 screws clear of10x10 upright. Adjustment is at carriage clamp, NOT by unmodelled idler slots. D6 inner spacer supports shoulder axle above.')
            for a in (-8,8):
                for b in (-7,7):m.add(i.name+f'_base_{a}_{b}',bolt(m,3,12),(i.origin[0]+a,i.origin[1]+b,12))
    # Clamps/adjusters and matching XY plate slots/counterbores.
    plate=find(m,'xy_plate');original=plate.part
    ph=[h for h in original.holes if not (h[2]==3.3 and abs(abs(h[0][0])-15)<1e-5 and abs(abs(h[0][1])-prior.R)<1e-5)]
    plate_shape=box(0,0,0,180,156,12)
    anchors=[]
    for axis in ('A','B'):
        for side in ('L','R'):
            x,y,sign=terminal(m,axis,side)
            for a in (-5,5):
                px=x-HOME_X+a;py=y-HOME_Y+sign*10.7
                if side=='L':
                    for dia,z,height in [(3.4,-1,14),(6.2,8.8,5)]:
                        slot=v2.slot_y(0,0,z,dia+2,dia,height).rotate((0,0,0),(0,0,1),90).translate((px+1,py,0))
                        plate_shape=plate_shape.cut(slot)
                else:
                    ph += [hz(px,py,-1,3.4,14),hz(px,py,8.8,6.2,5)]
            if side=='L':
                for b in (-5,5):
                    py=y-HOME_Y+sign*6.7+b
                    ph += [hz(-13,py,-1,3.4,14),hz(-13,py,8.8,6.2,5)]
    plate_shape=drill(plate_shape,ph)
    for xx in (-45,45):plate_shape=plate_shape.cut(cq.Solid.makeCone(8.25,4.25,4,cq.Vector(xx,0,0)))
    plate.part=m.part('C04_XY_Plate_LockSlots_180x156x12',plate_shape,holes=ph,
        note='Metal XYplate. Left A/B endclamps have0..2mm Xslots and recessed M3 heads; right clamps fixed. Pull lugs anchored separately. Slots not listed as cylindrical hole axes: use STEP/section/dedicated detail drawing.')
    for axis in ('A','B'):
        i=find(m,'belt_'+axis)
        i.part=m.part('C04_CoreXY_Open_Belt_'+axis,belt_shape(axis),'rubber','purchased_specified',
            note='OPEN2GT/6mm fibreglass reinforced belt, terminal centres±35,18mm full clamp engagement including9mm each end tail. Two independent layers; neither closed loop nor steel cable. Working rating>=documented selection requirement, actual tension and supplier acceptance pending.')
    # Recessed M5 datum-to-base screws avoid projecting into Y rails.
    for side in (-1,1):
        i=find(m,f'y_datum_{side}');h=[hz(0,yy,19,9.5,7) for yy in (-175,-75,25,125)]
        i.part=m.part('C04_Y_Datum_Recessed',drill(i.part.shape,h),holes=[*i.part.holes,*h],note='Metal24high rail datum with recessed M5x25 head planeZ25, head top30 equals railbase. Thread engagement into8mm base nominal6; verify actual screw/head and tightening.')
        for yy in (-175,-75,25,125):m.add(f'y_datum_base_{side}_{yy}',bolt(m,5,25),(side*205,-100+yy,25))
    # Beam-to-endplate fixings: underside caps recessed into endplate, not buried
    # in the Y guide block. The metal beam wall provides4mm M4 engagement.
    # Existing beam pilots are at X=side*205+/-10, Y=beam centre; the guide
    # fasteners are a further +/-10mm in Y, so these are separate holes.
    for side in (-1,1):
        i=find(m,f'gantry_end_{side}');h=[hz(a,b,-1,8,5.1) for a in (-10,10) for b in (-55,55)]
        i.part=m.part('C04_Gantry_EndPlate_Recessed',drill(i.part.shape,h),holes=[*i.part.holes,*h],note='Bottom M4 caps recessedZ43..47. TwoM4x10 into each boxbeam lower4mm wall; actual thread proof and final tightening required.')
        for a in (-10,10):
            for b in (-55,55):m.add(f'beam_mount_{side}_{a}_{b}',bolt(m,4,10,'up'),(side*205+a,HOME_Y+b,47),'gantry')
    # Base pilots rebuilt from C03 hole table, removing superseded motor/idler
    # foot patterns rather than silently retaining abandoned holes.
    base=find(m,'base');bh=[]
    old_motors=[find_motor(a) for a in ('A','B')]
    old_idlers=[(i.origin[0],i.origin[1]) for i in m.items if i.name.startswith('idler_') and i.name.endswith('_stand')]
    for h in base.part.holes:
        (x,y,z),direction,d,length=h
        superseded=any(abs(abs(x-xx)-28)<1e-4 and abs(abs(y-yy)-26)<1e-4 for xx,yy in old_motors)
        superseded=superseded or any(abs(abs(x-xx)-6)<1e-4 and abs(abs(y-yy)-3)<1e-4 for xx,yy in old_idlers)
        if not superseded:bh.append(h)
    bh += [hz(xx+a,yy+b,-3,4.2,10) for xx,yy in old_motors for a in (-32,32) for b in (-40,40)]
    bh += [hz(xx+a,yy+b,-3,2.5,10) for xx,yy in old_idlers for a in (-8,8) for b in (-7,7)]
    base.part=m.part('C04_Base_660x680x8',drill(box(0,-60,-2,660,680,8),bh),holes=bh,note='Continuous metal base. Updated accessible motor/idler bolt patterns; prior abandoned pilots removed. Bench support and anchors require physical acceptance.')
    # Convert custom item class after additions, while keeping old source frozen.
    m.items=[Item(i.name,i.part,i.origin,i.group) for i in m.items]
    used={i.part.name for i in m.items};m.parts={n:p for n,p in m.parts.items() if n in used}
    return m


def export(m):
    for sub in ('parts','stl','viewing','drawings','previews'):(OUT/sub).mkdir(parents=True,exist_ok=True)
    asm=cq.Assembly(name='COREXY_C04_MECHANICAL_FREEZE_CANDIDATE_NOT_LOAD_ACCEPTED')
    for i in m.items:
        color=(.95,.56,.12) if i.part.process=='candidate' else v2.COLORS.get(i.part.material,(.6,.6,.6))
        asm.add(i.located(),name=i.name,color=cq.Color(*color))
    asm.save(str(OUT/'CoreXY_C04_ASSEMBLY.step'))
    comp=cq.Compound.makeCompound([s for i in m.items for s in i.located().Solids()]);STEPControl_Writer()
    schema=Interface_Static.CVal_s('write.step.schema');mode=Interface_Static.IVal_s('write.step.assembly')
    try:
        if not Interface_Static.SetCVal_s('write.step.schema','AP203') or not Interface_Static.SetIVal_s('write.step.assembly',0):raise RuntimeError('flatSTEP settings unavailable')
        writer=STEPControl_Writer()
        if writer.Transfer(comp.wrapped,STEPControl_AsIs)!=IFSelect_RetDone:raise RuntimeError('STEP transfer')
        if writer.Write(str(OUT/'viewing/CoreXY_C04_SOLIDS_AP203.step'))!=IFSelect_RetDone:raise RuntimeError('STEP write')
    finally:Interface_Static.SetCVal_s('write.step.schema',schema);Interface_Static.SetIVal_s('write.step.assembly',mode)
    rows=[]
    for k,p in enumerate(sorted(m.parts.values(),key=lambda p:(p.process,p.name)),1):
        code=f'F{k:03}';b=p.shape.BoundingBox();cq.exporters.export(p.shape,str(OUT/'parts'/(code+'.step')))
        row={'code':code,'name':p.name,'quantity':sum(i.part.name==p.name for i in m.items),'material':p.material,'process':p.process,'solids':len(p.shape.Solids()),'volume_mm3':p.shape.Volume(),'bounds_mm':v2.bbox(p.shape),'extents_mm':[b.xlen,b.ylen,b.zlen],'holes':p.holes,'note':p.note}
        if p.process=='print':cq.exporters.export(p.shape.translate((-b.xmin,-b.ymin,-b.zmin)),str(OUT/'stl'/(code+'.stl')),tolerance=.03,angularTolerance=.1)
        rows.append(row)
    manifest={'version':'C04','fingerprint':FINGERPRINT,'units':'mm','parts':rows,'instances':[{'name':i.name,'part':i.part.name,'origin_mm':i.origin,'group':i.group} for i in m.items],'joints':m.joints,
        'allowed_contacts':[{'a':a,'b':b,'reason':n} for (a,b),n in m.allowed.items()],
        'architecture':'C03 topology frozen:two fixed A/B motors, travelling TR8x2 tower, rigid fork',
        'target_payload_kg':1,'motor_quantity':3,'AB_fixed':True,'independent_Y_pusher':False,'clamp_reference':'Phidgets TRM4226_0 GT2M-06 tooth+backplate pair',
        'terminal_centres_relative_X_mm':[-35,35],'left_tension_slider_stroke_mm':[0,2],'right_terminal_fixed':True,
        'motor_faces_Z_mm':{'A':78,'B':84},'B_shaft_in_pulley_mm':12,'lower_clamping_hub_length_mm':6,'base_mm':[660,680,8],
        'cell':[90,158,380],'io':[-90,158,293],'Z_fork_range_mm':[285,384],
        'A_nominal_belt_path_including_clamped_tails_mm':free_length('A',HOME_X,HOME_Y),'B_nominal_belt_path_including_clamped_tails_mm':free_length('B',HOME_X,HOME_Y),
        'mechanical_design_frozen':True,'manufacturing_release_allowed':False,'loaded_operation_allowed':False,'hardware_accepted':False,
        'motor_performance_verified':False,'automatic_brake_selected':False,'safety_circuit_implemented':False,'control_firmware_implemented':False,'maintenance_pin_shown_installed':True,
        'note':'Design freeze of modeled mechanical interfaces only. Supplier conformity, full connector hardware review, controls, independent fall protection and physical load tests are explicit separate gates.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    with (OUT/'BOM.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['code','name','quantity','material','process','note'],extrasaction='ignore');w.writeheader();w.writerows(rows)
    print('C04 EXPORTED',len(rows),'types',len(m.items),'instances',flush=True)


if __name__=='__main__':
    m=build_model();bad,accepted=v2.collisions(m.items,m.allowed)
    print(json.dumps({'static':bad,'accepted':accepted,'types':len(m.parts),'instances':len(m.items)},indent=2),flush=True)
