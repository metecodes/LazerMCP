"""Kinematics and hardware checks dispatched by semantic mechanism type."""
from __future__ import annotations
import math
from mechanisms import classify,mechanism_type
from motion_clearance import check_motion_clearance

def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _unit(v):
    m=math.sqrt(sum(float(x)**2 for x in v));return [float(x)/m for x in v] if m else None

def validate(primitives,parameters,thickness=3.0):
    parts={str(p.get('label') or ''):p for p in primitives or [] if isinstance(p,dict)};hardware={str(h.get('id') or ''):h for h in parameters.get('hardware') or [] if isinstance(h,dict)}
    connections=[c for c in parameters.get('connections') or [] if isinstance(c,dict)];rows=[]
    for info in classify(primitives):
        if not info['rotating']:continue
        label,kind=info['part'],info['type'];part=parts.get(label) or {}
        if kind in {'propeller','rotor'}:continue
        conn=next((c for c in connections if str(c.get('driven_part') or c.get('part') or '')==label and str(c.get('type') or '') in {'shaft_rotation','axle','bearing_shaft'}),None)
        hw_id=str((conn or {}).get('shaft') or (conn or {}).get('hardware') or ((part.get('mechanism') or {}).get('shaft') if isinstance(part.get('mechanism'),dict) else '') or '')
        shaft=hardware.get(hw_id)
        row={'part':label,'type':kind,'validator':{'wheel':'validateWheel','road_roller_drum':'validateRollerDrum','gear':'validateGear','pulley':'validatePulley','disc':'validateStaticDiscOrExplicitMotion','flywheel':'validateFlywheel'}.get(kind,'validateMechanism')}
        if not conn or not shaft:
            expected_id=hw_id or f'{label}-shaft'
            row.update(status='FAIL',reason='SHAFT_CONNECTION_MISSING',missing=['parameters.connections[]' if not conn else None,'parameters.hardware[]' if not shaft else None],expected_connection_schema={
                'connection':{'type':'shaft_rotation','shaft':expected_id,'driven_part':label,'hardware_clearance':0.15,'required_length':'number_mm','allowed_contact_parts':[]},
                'hardware':{'id':expected_id,'type':'shaft','diameter':'number_mm','axis':['x','y','z'],'origin':['x_mm','y_mm','z_mm'],'length':'number_mm'},
                'required_connection_fields':['type','shaft','driven_part'],
                'required_hardware_fields':['id','type','diameter','axis','origin','length']})
            row['missing']=[v for v in row['missing'] if v];rows.append(row);continue
        pose=part.get('placement');origin=shaft.get('origin') or shaft.get('shaft_origin');axis=shaft.get('axis') or shaft.get('shaft_axis')
        if not pose or not isinstance(origin,list) or not isinstance(axis,list):row.update(status='NOT_VERIFIED',reason='PLACEMENT_OR_SHAFT_AXIS_MISSING');rows.append(row);continue
        direction=_unit(axis);normal=_unit(_cross(pose['u'],pose['v']));center=pose['origin'];q=[float(center[i])-float(origin[i]) for i in range(3)];distance=math.sqrt(sum(x*x for x in _cross(q,direction))) if direction else 1e9;angle=math.degrees(math.acos(min(1,abs(sum(a*b for a,b in zip(direction or [0,0,0],normal or [0,0,0])))))) if direction and normal else 180
        dia=float(shaft.get('diameter') or shaft.get('shaft_diameter') or 0);hole=float(part.get('hole') or part.get('d_hole') or 0);clearance=float((conn or {}).get('hardware_clearance') if (conn or {}).get('hardware_clearance') is not None else parameters.get('hardware_clearance',.15));fit_tol=float((conn or {}).get('fit_tolerance_mm') or .15)
        fit_error=abs((hole-dia)-clearance);radius=float(part.get('d') or part.get('diameter') or 0)/2
        motion={'drive_type':'shaft_rotation','motor_axis':{'origin':origin,'direction':axis},'propeller_center':center,'radius_mm':radius,'moving_part':label,'clearance_mm':float((conn or {}).get('clearance_mm') or .2),'allowed_contact_parts':(conn or {}).get('allowed_contact_parts') or []}
        swept=check_motion_clearance(primitives,motion,thickness)
        if distance>float((conn or {}).get('axis_tolerance_mm') or .15):status,reason='FAIL','COAXIALITY_FAIL'
        elif angle>1:status,reason='FAIL','AXIS_NORMAL_MISMATCH'
        elif dia<=0 or hole<=0 or fit_error>fit_tol:status,reason='FAIL','SHAFT_HOLE_FIT_FAIL'
        elif shaft.get('length') is not None and (conn or {}).get('required_length') is not None and float(shaft['length'])<float(conn['required_length']):status,reason='FAIL','SHAFT_LENGTH_FAIL'
        elif swept['status']!='PASS':status,reason=swept['status'],swept['note']
        else:status,reason='PASS','ROTATION_VERIFIED'
        row.update(status=status,reason=reason,center_axis_distance_mm=distance,axis_normal_error_deg=angle,shaft_diameter_mm=dia,hole_diameter_mm=hole,hardware_clearance_mm=clearance,motion_clearance=swept);rows.append(row)
    return {'classifications':classify(primitives),'checks':rows}
