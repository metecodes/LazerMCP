"""Mechanism kinematics over a canonical shaft/hole connection graph."""
from __future__ import annotations
import math
from mechanisms import classify
from motion_clearance import check_motion_clearance
from assembled_view import world

LEGACY={'shaft_rotation','axle','bearing_shaft'}
def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _unit(v):
    m=math.sqrt(sum(float(x)**2 for x in (v or [])));return [float(x)/m for x in v] if m else None
def _part(c):return str(c.get('part') or c.get('driven_part') or c.get('mechanism_part') or '')
def _holes(part):
    rows=[]
    for h in part.get('canonical_holes') or []:
        if isinstance(h,dict) and float(h.get('diameter') or h.get('d') or 0)>0:rows.append({'id':str(h.get('id') or 'center-hole'),'x':float(h.get('x') or 0),'y':float(h.get('y') or 0),'diameter':float(h.get('diameter') or h.get('d'))})
    for i,h in enumerate(part.get('holes') or []):
        if not isinstance(h,dict):continue
        d=float(h.get('d') or h.get('diameter') or 0)
        if d>0:rows.append({'id':str(h.get('id') or h.get('label') or f'hole-{i+1}'),'x':float(h.get('x') or h.get('cx') or 0),'y':float(h.get('y') or h.get('cy') or 0),'diameter':d})
    d=float(part.get('hole') or part.get('d_hole') or 0)
    if d>0 and not any(h['id']=='center-hole' for h in rows):rows.insert(0,{'id':'center-hole','x':0.,'y':0.,'diameter':d})
    return rows
def _hole_world(part,hole):
    pose=part.get('placement') or {};u,v=pose.get('u'),pose.get('v')
    if not isinstance(u,list) or not isinstance(v,list):return None,None
    return world(part,hole['x'],hole['y'],0),_unit(_cross(u,v))
def _schema(label,sid):
    sid=sid or f'{label}-shaft'
    return {'connection':{'type':'shaft_hole','part':label,'shaft':sid,'hole':'center-hole','fit':'rotating'},'hardware':{'id':sid,'type':'shaft','diameter':'number_mm','axis':['x','y','z'],'origin':['x_mm','y_mm','z_mm'],'length':'number_mm'},'required_connection_fields':['type','part','shaft','hole','fit'],'required_hardware_fields':['id','type','diameter','axis','length']}

def validate(primitives,parameters,thickness=3.0):
    parameters=parameters if isinstance(parameters,dict) else {};parts={str(p.get('label') or ''):p for p in primitives or [] if isinstance(p,dict)}
    hardware={str(h.get('id') or ''):h for h in parameters.get('hardware') or [] if isinstance(h,dict)};connections=[c for c in parameters.get('connections') or [] if isinstance(c,dict)]
    explicit=[c for c in connections if str(c.get('type') or '')=='shaft_hole'];legacy=[c for c in connections if str(c.get('type') or '') in LEGACY]
    graph=[];resolved={};shaft_origins={}
    for c in explicit:
        label=_part(c);part=parts.get(label);sid=str(c.get('shaft') or c.get('hardware') or '');candidates=_holes(part or {});wanted=str(c.get('hole') or '')
        if wanted:chosen=next((h for h in candidates if h['id']==wanted),None);reason=None if chosen else 'SHAFT_HOLE_NOT_FOUND'
        elif len(candidates)==1:chosen=candidates[0];reason=None
        elif len(candidates)>1:chosen=None;reason='AMBIGUOUS_SHAFT_HOLE'
        else:chosen=None;reason='SHAFT_HOLE_NOT_FOUND'
        center,normal=_hole_world(part or {},chosen) if chosen else (None,None);status='PASS' if part and sid and chosen and center else 'FAIL'
        if not part:reason='PART_NOT_FOUND'
        elif not sid:reason='SHAFT_ID_MISSING'
        edge={'shaft':sid,'part':label,'hole':wanted or (chosen or {}).get('id'),'fit':str(c.get('fit') or 'rotating'),'type':'shaft_hole','world_center':center,'world_normal':normal,'hole_diameter_mm':(chosen or {}).get('diameter'),'status':status,'reason':reason}
        graph.append(edge);resolved[label]=(c,chosen,edge)
        if status=='PASS' and sid not in shaft_origins:shaft_origins[sid]=center
    for edge in graph:
        if edge['status']!='PASS':continue
        shaft=hardware.get(edge['shaft']);axis=(shaft or {}).get('axis') or (shaft or {}).get('shaft_axis');origin=(shaft or {}).get('origin') or (shaft or {}).get('shaft_origin') or shaft_origins.get(edge['shaft']);direction=_unit(axis)
        if not shaft:edge.update(status='FAIL',reason='SHAFT_HARDWARE_MISSING');continue
        if not direction or not isinstance(origin,list):edge.update(status='FAIL',reason='SHAFT_AXIS_MISSING');continue
        q=[edge['world_center'][i]-float(origin[i]) for i in range(3)];distance=math.sqrt(sum(x*x for x in _cross(q,direction)));angle=math.degrees(math.acos(min(1,abs(sum(a*b for a,b in zip(direction,edge['world_normal']))))))
        sd=float(shaft.get('diameter') or shaft.get('shaft_diameter') or 0);hd=float(edge.get('hole_diameter_mm') or 0);clearance=hd-sd
        edge.update(shaft_diameter_mm=sd,diametral_clearance_mm=clearance,center_axis_distance_mm=distance,axis_error_deg=angle)
        if sd<=0:edge.update(status='FAIL',reason='MISSING_SHAFT_DIAMETER')
        elif hd<=0:edge.update(status='FAIL',reason='MISSING_HOLE_DIAMETER')
        elif distance>.15 or angle>1:edge.update(status='FAIL',reason='COAXIALITY_FAIL')
        elif clearance<0 or abs(clearance-(float(shaft.get('hole_diameter') or sd+.15)-sd))>.15:edge.update(status='FAIL',reason='SHAFT_HOLE_FIT_FAIL')
        else:edge['reason']='SHAFT_HOLE_VERIFIED'
    rows=[];dispatch={'wheel':'validateWheel','road_roller_drum':'validateRollerDrum','gear':'validateGear','pulley':'validatePulley','disc':'validateStaticDiscOrExplicitMotion','flywheel':'validateFlywheel'}
    for info in classify(primitives):
        if not info['rotating'] or info['type'] in {'propeller','rotor'}:continue
        label,kind=info['part'],info['type'];part=parts.get(label) or {};entry=resolved.get(label);conn,chosen,edge=entry if entry else (None,None,None)
        if conn is None:
            conn=next((c for c in legacy if _part(c)==label),None);candidates=_holes(part)
            if conn and len(candidates)==1:chosen=candidates[0]
            elif conn and len(candidates)>1:rows.append({'part':label,'type':kind,'validator':dispatch.get(kind,'validateMechanism'),'status':'FAIL','reason':'AMBIGUOUS_SHAFT_HOLE','candidate_holes':[h['id'] for h in candidates]});continue
        sid=str((conn or {}).get('shaft') or (conn or {}).get('hardware') or '');shaft=hardware.get(sid);row={'part':label,'type':kind,'validator':dispatch.get(kind,'validateMechanism'),'shaft_id':sid or None,'hole_id':(chosen or {}).get('id'),'fit':str((conn or {}).get('fit') or 'rotating')}
        if not conn or not shaft:
            row.update(status='FAIL',reason='SHAFT_CONNECTION_MISSING',missing=[v for v in ['parameters.connections[]' if not conn else None,'parameters.hardware[]' if not shaft else None] if v],expected_connection_schema=_schema(label,sid));rows.append(row);continue
        if edge and edge['status']=='FAIL':row.update(status='FAIL',reason=edge['reason']);rows.append(row);continue
        candidates=_holes(part)
        if chosen is None:
            if len(candidates)==1:chosen=candidates[0]
            elif len(candidates)>1:row.update(status='FAIL',reason='AMBIGUOUS_SHAFT_HOLE',candidate_holes=[h['id'] for h in candidates]);rows.append(row);continue
            else:row.update(status='FAIL',reason='SHAFT_HOLE_NOT_FOUND');rows.append(row);continue
        center,normal=_hole_world(part,chosen);axis=shaft.get('axis') or shaft.get('shaft_axis');origin=shaft.get('origin') or shaft.get('shaft_origin') or shaft_origins.get(sid)
        if center is None or not isinstance(axis,list) or not isinstance(origin,list):row.update(status='NOT_VERIFIED',reason='PLACEMENT_OR_SHAFT_AXIS_MISSING');rows.append(row);continue
        direction=_unit(axis);q=[float(center[i])-float(origin[i]) for i in range(3)];distance=math.sqrt(sum(x*x for x in _cross(q,direction))) if direction else 1e9;angle=math.degrees(math.acos(min(1,abs(sum(a*b for a,b in zip(direction or [0,0,0],normal or [0,0,0])))))) if direction and normal else 180
        dia=float(shaft.get('diameter') or shaft.get('shaft_diameter') or 0);hole=float(chosen.get('diameter') or shaft.get('hole_diameter') or 0);clearance=hole-dia;desired=float(conn.get('hardware_clearance') if conn.get('hardware_clearance') is not None else parameters.get('hardware_clearance',float(shaft.get('hole_diameter') or dia+.15)-dia));fit_tol=float(conn.get('fit_tolerance_mm') or .15);radius=float(part.get('d') or part.get('diameter') or 0)/2
        motion={'drive_type':'shaft_rotation','motor_axis':{'origin':origin,'direction':axis},'propeller_center':center,'radius_mm':radius,'moving_part':label,'clearance_mm':float(conn.get('clearance_mm') or .2),'allowed_contact_parts':conn.get('allowed_contact_parts') or []};swept=check_motion_clearance(primitives,motion,thickness)
        if dia<=0:status,reason='FAIL','MISSING_SHAFT_DIAMETER'
        elif hole<=0:status,reason='FAIL','MISSING_HOLE_DIAMETER'
        elif distance>float(conn.get('axis_tolerance_mm') or .15) or angle>1:status,reason='FAIL','COAXIALITY_FAIL'
        elif clearance<0 or abs(clearance-desired)>fit_tol:status,reason='FAIL','SHAFT_HOLE_FIT_FAIL'
        elif shaft.get('length') is not None and conn.get('required_length') is not None and float(shaft['length'])<float(conn['required_length']):status,reason='FAIL','SHAFT_LENGTH_FAIL'
        elif swept['status']!='PASS':status,reason=swept['status'],swept['note']
        else:status,reason='PASS','ROTATION_VERIFIED'
        row.update(status=status,reason=reason,world_center=center,hole_axis=normal,shaft_axis=direction,center_axis_distance_mm=distance,axis_error_deg=angle,shaft_diameter_mm=dia,hole_diameter_mm=hole,diametral_clearance_mm=clearance,hardware_clearance_mm=desired,motion_clearance=swept);rows.append(row)
    return {'classifications':classify(primitives),'connection_graph':graph,'checks':rows}
