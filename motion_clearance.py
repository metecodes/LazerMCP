"""Geometric coaxial and 360-degree swept-disk clearance checks."""
from __future__ import annotations
import math
from shapely.geometry import Point, Polygon
from assembled_view import outline

def _unit(v):
    mag=math.sqrt(sum(float(x)**2 for x in v))
    return [float(x)/mag for x in v] if mag else None
def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _dot(a,b):return sum(x*y for x,y in zip(a,b))

def resolve_motion(parameters):
    """Resolve motion from an explicit connection; retain the old motion object as input compatibility."""
    parameters=parameters if isinstance(parameters,dict) else {}
    motion=dict(parameters.get('motion') or {})
    direct=None
    for row in parameters.get('connections') or []:
        if isinstance(row,dict) and str(row.get('type') or row.get('kind') or '').lower()=='direct_motor_shaft':
            direct=row;break
    if direct:
        aliases={
            'motor_axis':direct.get('motor_axis') or direct.get('shaft_axis'),
            'propeller_center':direct.get('propeller_center') or direct.get('driven_center'),
            'moving_part':direct.get('driven_part') or direct.get('moving_part'),
            'motor_part':direct.get('motor_part'),
            'radius_mm':direct.get('radius_mm'),
            'clearance_mm':direct.get('clearance_mm'),
            'axis_tolerance_mm':direct.get('axis_tolerance_mm'),
            'allowed_contact_parts':direct.get('allowed_contact_parts'),
        }
        motion.update({k:v for k,v in aliases.items() if v is not None})
        motion['drive_type']='direct_motor_shaft';motion['connection_source']='parameters.connections'
    elif str(parameters.get('drive_type') or '').lower()=='direct_motor_shaft':
        motion['drive_type']='direct_motor_shaft'
    return motion

def check_motion_clearance(primitives,motion,thickness=3.0):
    if not isinstance(motion,dict):return {'status':'NOT_VERIFIED','note':'motion geometry is required'}
    drive=str(motion.get('drive_type') or motion.get('connection_type') or '').lower()
    axis=motion.get('motor_axis') or motion.get('axis');center=motion.get('propeller_center') or motion.get('center')
    radius=float(motion.get('radius_mm') or 0);moving=str(motion.get('moving_part') or '')
    if drive=='direct_motor_shaft':
        if not motion.get('motor_part') or not moving:
            return {'status':'NOT_VERIFIED','note':'direct_motor_shaft requires motor_part and driven_part/moving_part endpoints'}
        labels={str(p.get('label') or '') for p in primitives or [] if isinstance(p,dict)}
        if moving not in labels:
            return {'status':'FAIL','note':f'direct_motor_shaft driven part {moving!r} does not exist in generated geometry'}
    if not isinstance(axis,dict) or len(axis.get('origin') or [])!=3 or len(axis.get('direction') or [])!=3 or not isinstance(center,list) or len(center)!=3 or radius<=0:
        return {'status':'NOT_VERIFIED','note':'motor_axis, propeller_center, radius_mm and moving_part are required'}
    origin=[float(x) for x in axis['origin']];direction=_unit(axis['direction']);center=[float(x) for x in center]
    if not direction:return {'status':'FAIL','note':'motion axis direction has zero length'}
    q=[center[i]-origin[i] for i in range(3)];axis_error=math.sqrt(sum(x*x for x in _cross(q,direction)))
    tolerance=float(motion.get('axis_tolerance_mm',.15))
    if axis_error>tolerance:return {'status':'FAIL','note':f'motor shaft axis misses propeller center by {axis_error:.3f} mm'}
    seed=[1,0,0] if abs(direction[0])<.8 else [0,1,0];u=_unit(_cross(direction,seed));v=_cross(direction,u)
    allowed=set(map(str,motion.get('allowed_contact_parts') or []));clearance=float(motion.get('clearance_mm') or .2)
    obstacles=[]
    for part in primitives or []:
        if not isinstance(part,dict) or str(part.get('label') or '') in allowed|{moving}:continue
        pts=outline(part);pose=part.get('placement')
        if not pts or not pose:continue
        try:
            pu,pv=pose['u'],pose['v'];pn=_cross(pu,pv);poly=Polygon(pts)
            if poly.is_valid and poly.area>0:obstacles.append((str(part.get('label')),pose['origin'],pu,pv,pn,poly))
        except (KeyError,TypeError,ValueError):return {'status':'NOT_VERIFIED','note':f'invalid placement on {part.get("label")}' }
    if not obstacles:return {'status':'NOT_VERIFIED','note':'no explicitly placed obstacle geometry for swept-area test'}
    collisions=set();samples=0
    for ri in range(13):
        r=radius*ri/12
        for ai in range(72):
            a=2*math.pi*ai/72;samples+=1
            point=[center[i]+r*(math.cos(a)*u[i]+math.sin(a)*v[i]) for i in range(3)]
            for label,o,pu,pv,pn,poly in obstacles:
                diff=[point[i]-float(o[i]) for i in range(3)];depth=_dot(diff,pn)
                if abs(depth)<=thickness/2+clearance and poly.buffer(clearance).covers(Point(_dot(diff,pu),_dot(diff,pv))):collisions.add(label)
    if collisions:return {'status':'FAIL','note':'360° swept area intersects '+', '.join(sorted(collisions)),'samples':samples,'axis_error_mm':axis_error}
    note=f'360° swept area clear across {samples} geometric samples'
    if drive=='direct_motor_shaft':note='direct_motor_shaft endpoints and coaxial 360° swept area verified; '+note
    return {'status':'PASS','note':note,'samples':samples,'axis_error_mm':axis_error,'connection_type':drive or None}
