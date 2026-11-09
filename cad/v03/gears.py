"""Sampled involute pinion and conjugate straight rack for prototype coupons (mm).

No helical/undercut corrections, tooth strength rating or printer compensation is implied.
Both members lose 0.15 mm tooth thickness, giving 0.30 mm nominal tangential backlash.
"""
import math
import cadquery as cq

MODULE = 1.5
TEETH = 20
PRESSURE_DEG = 20.0
BACKLASH = .30
PITCH = math.pi*MODULE
RADIUS = MODULE*TEETH/2
SEGMENT_TEETH = 24
SEGMENT_LENGTH = SEGMENT_TEETH*PITCH
RACK_PITCH_HEIGHT = 8.0


def rack(n=SEGMENT_TEETH):
    length = n*PITCH
    base = cq.Solid.makeBox(length, 30, 6.3, cq.Vector(0, -15, 0))
    alpha = math.radians(PRESSURE_DEG)
    half = (PITCH/2-BACKLASH/2)/2
    bottom, top = RACK_PITCH_HEIGHT-1.25*MODULE, RACK_PITCH_HEIGHT+MODULE
    wb = half+(RACK_PITCH_HEIGHT-bottom)*math.tan(alpha)
    wt = half-(top-RACK_PITCH_HEIGHT)*math.tan(alpha)
    teeth = []
    for i in range(n):
        c = (i+.5)*PITCH
        # XZ workplane normal points -Y. Centre the 12 mm tooth face on Y=0.
        tooth = (cq.Workplane('XZ').polyline([(c-wb,bottom),(c+wb,bottom),
                 (c+wt,top),(c-wt,top)]).close().extrude(12).val().translate((0,6,0)))
        teeth.append(tooth)
    result = base.fuse(*teeth).clean()
    for x in (6*PITCH, (n-6)*PITCH):
        for y in (-11,11):
            result = result.cut(cq.Solid.makeCylinder(1.7,8,cq.Vector(x,y,-1)))
    return result.clean()


def pinion():
    a = math.radians(PRESSURE_DEG)
    rb, rf, ra = RADIUS*math.cos(a), RADIUS-1.25*MODULE, RADIUS+MODULE
    inv = lambda angle: math.tan(angle)-angle
    half_pitch = (PITCH/2-BACKLASH/2)/(2*RADIUS)
    def flank_angle(r):
        angle = math.acos(rb/r) if r >= rb else 0
        return half_pitch+inv(a)-inv(angle)
    polar = lambda r, angle: (r*math.cos(angle),r*math.sin(angle))
    points = []
    for k in range(TEETH):
        theta = 2*math.pi*k/TEETH
        ab = flank_angle(rb)
        points.append(polar(rf,theta-ab))
        for j in range(13):
            r = rb+(ra-rb)*j/12
            points.append(polar(r,theta-flank_angle(r)))
        at = flank_angle(ra)
        for j in range(1,5):
            points.append(polar(ra,theta-at+2*at*j/4))
        for j in range(11,-1,-1):
            r = rb+(ra-rb)*j/12
            points.append(polar(r,theta+flank_angle(r)))
        points.append(polar(rf,theta+ab))
        end = theta+2*math.pi/TEETH-ab
        for j in range(1,5):
            points.append(polar(rf,theta+ab+(end-theta-ab)*j/4))
    # Last point coincides with the first; OCC must not receive a zero-length edge.
    points.pop()
    unique=[]
    for p in points:
        if not unique or math.dist(unique[-1],p)>1e-8:unique.append(p)
    points=unique
    shape = cq.Workplane('XY').polyline(points).close().extrude(12).val()
    for x,y,r in ((0,0,6.1),(-9,0,1.7),(9,0,1.7)):
        shape = shape.cut(cq.Solid.makeCylinder(r,14,cq.Vector(x,y,-1)))
    return shape.clean()


def z_rack(shape):
    # Local X->world Z, local Y->world -Y, local Z->world X.
    return shape.rotate((0,0,0),(0,1,0),90).rotate((0,0,0),(1,0,0),180)


def y_rack(shape):
    # Local X->world Y, local Y->world Z, local Z->world X.
    return shape.rotate((0,0,0),(1,1,1),120)
