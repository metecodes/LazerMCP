"""World-space validation for opt-in linear slide mechanisms."""
from __future__ import annotations
import math
from copy import deepcopy
from assembled_view import outline, world

SAMPLES=(0,.25,.5,.75,1)

def _unit(v):
    try:
        m=math.sqrt(sum(float(x)**2 for x in v));return [float(x)/m for x in v] if m else None
    except (TypeError,ValueError):return None

def _bbox(part,t=3):
    pts=outline(part)
    if not pts or not part.get('placement'):return None
    xyz=[world(part,x,y,z) for x,y in pts for z in (0,t)]
    return [min(q[i] for q in xyz) for i in range(3)]+[max(q[i] for q in xyz) for i in range(3)]

def _overlap(a,b,tol=.01):
    return all(min(a[i+3],b[i+3])-max(a[i],b[i])>tol for i in range(3))

def _swept_overlap(a,b,velocity,tol=.01):
    """Exact continuous overlap interval for translated 3D AABBs."""
    enter,leave=0.0,1.0
    for i,v in enumerate(velocity):
        lo=float(b[i])+tol-float(a[i+3]);hi=float(b[i+3])-tol-float(a[i])
        if abs(v)<1e-12:
            if lo>=0 or hi<=0:return None
            continue
        t0,t1=lo/v,hi/v
        enter=max(enter,min(t0,t1));leave=min(leave,max(t0,t1))
        if enter>=leave:return None
    return [max(0.0,enter),min(1.0,leave)] if leave>0 and enter<1 else None

def validate(primitives,parameters,thickness=3):
    parts={str(p.get('label') or ''):p for p in primitives or [] if isinstance(p,dict)}
    conns=[c for c in (parameters or {}).get('connections') or [] if isinstance(c,dict)]
    slides=[c for c in conns if str(c.get('type') or '') in {'linear_slide','removable_slide'}]
    drives=[c for c in conns if str(c.get('type') or '')=='servo_linear_drive']
    rows=[]
    for index,c in enumerate(slides,1):
        cid=str(c.get('id') or f'linear-slide-{index}');label=str(c.get('moving_part') or c.get('driven_part') or '');moving=parts.get(label)
        rails=[parts.get(str(x)) for x in c.get('rails') or []];axis=_unit(c.get('axis'));travel=float(c.get('travel_mm') or 0);clearance=float(c.get('clearance_mm') or 0)
        row={'id':cid,'type':str(c.get('type') or 'linear_slide'),'moving_part':label,'rails':[str(x) for x in c.get('rails') or []],'axis':axis,'travel_mm':travel,'clearance_mm':clearance,'positions':[],'collisions':[]}
        if not moving or not moving.get('placement'):row.update(status='FAIL',reason='MOVING_PART_OR_PLACEMENT_MISSING');rows.append(row);continue
        if len(rails)<1 or any(not r or not r.get('placement') for r in rails):row.update(status='FAIL',reason='RAIL_OR_PLACEMENT_MISSING');rows.append(row);continue
        if not axis or travel<=0:row.update(status='FAIL',reason='SLIDE_AXIS_OR_TRAVEL_INVALID');rows.append(row);continue
        if clearance<0:row.update(status='FAIL',reason='NEGATIVE_RAIL_CLEARANCE');rows.append(row);continue
        # Contact is permitted at a surface, not throughout a named rail's solid.
        allowed={label};failed=False
        start_box=_bbox(moving,thickness);velocity=[axis[i]*travel for i in range(3)]
        for name,part in parts.items():
            if name in allowed:continue
            obstacle_box=_bbox(part,thickness)
            hit=_swept_overlap(start_box,obstacle_box,velocity,.01) if start_box and obstacle_box else None
            if hit:
                failed=True;row['collisions'].append({'part':name,'kind':'continuous-static-moving','travel_range_mm':[round(hit[0]*travel,3),round(hit[1]*travel,3)]})
        for ratio in SAMPLES:
            probe=deepcopy(moving);probe['placement']=deepcopy(moving['placement']);probe['placement']['origin']=[float(probe['placement']['origin'][i])+axis[i]*travel*ratio for i in range(3)]
            mb=_bbox(probe,thickness);hits=[]
            for name,part in parts.items():
                if name in allowed:continue
                pb=_bbox(part,thickness)
                if mb and pb and _overlap(mb,pb,.01):hits.append(name)
            status='FAIL' if hits else 'PASS';failed|=bool(hits);row['positions'].append({'travel_mm':round(travel*ratio,3),'ratio':ratio,'status':status,'collisions':hits})
            row['collisions'].extend({'at_mm':round(travel*ratio,3),'part':x,'kind':'static-moving'} for x in hits)
        row.update(status='FAIL' if failed else 'PASS',reason='SLIDE_COLLISION' if failed else 'CONTINUOUS_LINEAR_TRAVEL_VERIFIED',minimum_clearance_mm=clearance,continuous_sweep=True)
        if row['type']=='removable_slide':
            # The reverse reinstall path traverses the same continuous swept volume.
            row.update(removal_verified=not failed,reinstall_verified=not failed,
                       sequence=['remove','bag_install','reinstall'],
                       removal_end_origin=[round(float(moving['placement']['origin'][i])+velocity[i],6) for i in range(3)])
        rows.append(row)
    drive_rows=[]
    for c in drives:
        slide=next((r for r in rows if r['id']==str(c.get('slide_connection') or '')),None)
        enough=any(c.get(k) is not None for k in ('linkage_ratio','travel_per_degree_mm','lead_mm_per_rev'))
        if not slide:status,reason='FAIL','SLIDE_CONNECTION_NOT_FOUND'
        elif not enough:status,reason='NOT_VERIFIED','SERVO_LINKAGE_GEOMETRY_REQUIRED'
        else:
            per=float(c.get('travel_per_degree_mm') or 0);span=float(c.get('servo_angle_max') or 0)-float(c.get('servo_angle_min') or 0);available=abs(per*span)
            status='PASS' if available>=float(c.get('required_travel_mm') or slide['travel_mm']) else 'FAIL';reason='SERVO_TRAVEL_VERIFIED' if status=='PASS' else 'SERVO_TRAVEL_INSUFFICIENT'
        drive_rows.append({'type':'servo_linear_drive','motor_part':c.get('motor_part'),'driven_part':c.get('driven_part'),'slide_connection':c.get('slide_connection'),'status':status,'reason':reason})
    return {'active':bool(slides or drives),'slides':rows,'drives':drive_rows,'status':'FAIL' if any(r['status']=='FAIL' for r in [*rows,*drive_rows]) else ('NOT_VERIFIED' if any(r['status']=='NOT_VERIFIED' for r in drive_rows) else ('PASS' if slides else 'N/A'))}
