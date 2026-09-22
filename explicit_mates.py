"""Optional explicit connectors bound to authoritative CUT features.

Declarations never create or move manufacturing geometry. Unsupported physical
interfaces remain unverified, even when their type pair is compatible.
"""
from copy import deepcopy
from collections import Counter
import math
from structural_mates import contour_candidates, _frame, _corners, dot,sub,norm
from assembled_view import world

TYPES={'tab','slot','finger','finger_socket','edge','hole','pin','hinge','axle','bearing','rail','slider','custom'}
COMPATIBLE={frozenset(p) for p in [('tab','slot'),('finger','finger_socket'),('pin','hole'),('edge','edge'),('hinge','hinge'),('axle','bearing'),('rail','slider')]}
RECT_TYPES={'tab','slot','finger','finger_socket'}


def prepare_parts(parts):
    result=deepcopy(parts)
    for i,p in enumerate(result):
        if not isinstance(p,dict):continue
        pid=str(p.get('part_id') or p.get('label') or p.get('id') or f'part-{i+1}')
        if p.get('part_id') and p.get('connectors'):
            if p.get('label')!=pid:p.setdefault('display_label',p.get('label'))
            p['label']=pid
        if p.get('connectors'):p.setdefault('label',pid);p['part_id']=pid
        pose=p.get('placement')
        if pose:
            try:
                u,v=[list(map(float,pose[k])) for k in ('u','v')]
                if len(u)!=3 or len(v)!=3 or not all(math.isfinite(x) for x in u+v):raise ValueError()
                un,vn=norm(u),norm(v);original_length_error=max(abs(un-1),abs(vn-1))
                if min(un,vn)<1e-9 or max(abs(un-1),abs(vn-1))>.01:raise ValueError()
                u=[x/un for x in u];v=[x/vn for x in v];skew=dot(u,v)
                if abs(skew)>.002:raise ValueError()
                v=[v[j]-skew*u[j] for j in range(3)];vn=norm(v);v=[x/vn for x in v]
                if any(abs(a-b)>1e-10 for a,b in zip(u+v,pose['u']+pose['v'])):
                    pose['u']=u;pose['v']=v;p['placement_normalization']={'status':'NORMALIZED','max_axis_length_error':original_length_error,'original_dot':skew}
            except (KeyError,TypeError,ValueError):p.setdefault('_mate_prepare_errors',[]).append('INVALID_PLACEMENT_AXES')
        # Explicit per-part mate records can name connectors instead of duplicating mate_id.
        for m in p.get('mates') or []:
            if not isinstance(m,dict) or not m.get('connector_id'):continue
            c=next((c for c in p.get('connectors',[]) if isinstance(c,dict) and c.get('id')==m['connector_id']),None)
            if c is not None:
                target=m.get('target_connector')
                if c.get('mate_id') and c['mate_id']!=target:p.setdefault('_mate_prepare_errors',[]).append('DUPLICATE_MATE')
                else:c['mate_id']=target
    return result


def _world_axis(p,axis):
    _,u,v,n=_frame(p)
    if len(axis)!=3:raise ValueError('MATE_AXIS_MISMATCH')
    q=[float(axis[0])*u[i]+float(axis[1])*v[i]+float(axis[2])*n[i] for i in range(3)]
    size=norm(q)
    if not math.isfinite(size) or size<1e-9:raise ValueError('MATE_AXIS_MISMATCH')
    return [x/size for x in q]


def _resolve(p,c,t):
    position=c.get('position') or []
    if len(position) not in (2,3) or not all(math.isfinite(float(x)) for x in position):raise ValueError('MATE_POSITION_MISMATCH')
    size=[float(c.get(k,0)) for k in ('width_mm','depth_mm','thickness_mm')]
    if not all(math.isfinite(x) and x>0 for x in size) or abs(size[2]-t)>.05:raise ValueError('MATE_DIMENSION_MISMATCH')
    typ=c['type'];kind='tab' if typ in {'tab','finger'} else 'void'
    candidates,_=contour_candidates(p)
    candidates=[f for f in candidates if (f['kind']=='tab')==(kind=='tab')]
    if c.get('feature_id'):candidates=[f for f in candidates if f['feature']==c['feature_id']]
    aligned=[]
    for f in candidates:
        center=[sum(q[i] for q in f['points'])/len(f['points']) for i in (0,1)]
        if norm(sub(center,position[:2]))<=.05:aligned.append(f)
    if len(aligned)!=1:raise ValueError('MATE_POSITION_MISMATCH' if not aligned else 'DUPLICATE_MATE')
    f=aligned[0]
    if abs(f['width']-size[0])>.05 or abs(f['depth']-size[1])>.05:raise ValueError('MATE_DIMENSION_MISMATCH')
    if len(position)==3 and abs(float(position[2])-t/2)>.05:raise ValueError('MATE_POSITION_MISMATCH')
    axis=_world_axis(p,c.get('axis') or [])
    if kind=='tab':expected=_world_axis(p,[*f['direction'],0])
    else:expected=_frame(p)[3]
    if abs(dot(axis,expected))<1-1e-5:raise ValueError('MATE_AXIS_MISMATCH')
    return f,axis


def validate_connectors(parts,thickness=3,parameters=None):
    params=parameters or {};rows=[];errors=[];lookup={};owners={}
    for p in parts:
        pid=str(p.get('physical_part_id') or p.get('part_id') or p.get('label') or '')
        if pid in owners:errors.append({'code':'DUPLICATE_PART_ID','part_id':pid})
        owners[pid]=p
        errors.extend({'code':e,'part_id':pid} for e in p.get('_mate_prepare_errors',[]))
        declared=p.get('connectors') or []
        if not isinstance(declared,list):
            errors.append({'code':'INVALID_CONNECTOR_SCHEMA','part_id':pid});continue
        for raw in declared:
            if not isinstance(raw,dict):
                errors.append({'code':'INVALID_CONNECTOR_SCHEMA','part_id':pid});continue
            c=deepcopy(raw);cid=str(c.get('id') or '')
            if not cid or cid in lookup:errors.append({'code':'DUPLICATE_MATE','connector_id':cid});continue
            if c.get('part_id',pid)!=pid:errors.append({'code':'MATE_TARGET_NOT_FOUND','connector_id':cid,'part_id':c.get('part_id')})
            c['part_id']=pid;lookup[cid]=c
    active=bool(lookup) or any(p.get('connectors') for p in parts)
    incoming=Counter(str(c.get('mate_id')) for c in lookup.values())
    occupied={};done=set();verified=[]
    for cid,a in lookup.items():
        target=str(a.get('mate_id') or '');b=lookup.get(target)
        rec={'id':'mate:'+':'.join(sorted((cid,target))),'connector_a':cid,'connector_b':target,'part_a':a['part_id'],'part_b':(b or {}).get('part_id'),'status':'FAIL','checks':{},'locked':False}
        try:
            if not b:raise ValueError('MATE_TARGET_NOT_FOUND')
            if b.get('mate_id')!=cid:raise ValueError('NON_RECIPROCAL_MATE')
            if incoming[target]>1 or incoming[cid]>1:raise ValueError('DUPLICATE_MATE')
            if a['part_id']==b['part_id']:raise ValueError('MATE_TYPE_INCOMPATIBLE')
            if a.get('type') not in TYPES or b.get('type') not in TYPES or frozenset((a['type'],b['type'])) not in COMPATIBLE:
                raise ValueError('NON_COMPLEMENTARY_JOINT' if a.get('type')==b.get('type') and a.get('type') in {'tab','finger'} else 'MATE_TYPE_INCOMPATIBLE')
            if frozenset((cid,target)) in done:continue
            done.add(frozenset((cid,target)));rec['checks']['Reciprocal Mate']='PASS'
            if a['type'] not in RECT_TYPES or b['type'] not in RECT_TYPES:raise ValueError('MATE_GEOMETRY_UNSUPPORTED')
            ap,bp=owners[a['part_id']],owners[b['part_id']];at=float(ap.get('thickness',thickness));bt=float(bp.get('thickness',thickness))
            af,aa=_resolve(ap,a,at);bf,ba=_resolve(bp,b,bt)
            allowance=float(params.get('mate_fit_tolerance_mm',.05))
            if not math.isfinite(allowance) or not 0<=allowance<=.15:raise ValueError('MATE_DIMENSION_MISMATCH')
            if abs(af['width']-bf['width'])>allowance or abs(af['depth']-bt)>allowance or abs(bf['depth']-at)>allowance:
                raise ValueError('MATE_DIMENSION_MISMATCH')
            rec['checks'].update({'Tab Geometry':'PASS','Slot Geometry':'PASS'})
            for c,f in ((a,af),(b,bf)):
                key=c['part_id'],f['feature']
                if key in occupied and occupied[key]!=c['id']:raise ValueError('DUPLICATE_MATE')
                occupied[key]=c['id']
            if abs(dot(aa,ba))<1-1e-5:raise ValueError('MATE_AXIS_MISMATCH')
            av,bv=_corners(ap,af,at),_corners(bp,bf,bt)
            error=max(max(min(norm(sub(x,y)) for y in bv) for x in av),max(min(norm(sub(y,x)) for x in av) for y in bv))
            allowance=float(params.get('mate_fit_tolerance_mm',.05))
            if not math.isfinite(allowance) or not 0<=allowance<=.15:raise ValueError('MATE_DIMENSION_MISMATCH')
            rec.update(world_position_a=[sum(q[i] for q in av)/8 for i in range(3)],world_position_b=[sum(q[i] for q in bv)/8 for i in range(3)],alignment_error_mm=error,axis_a=aa,axis_b=ba)
            if error>allowance:raise ValueError('MATE_POSITION_MISMATCH')
            rec['checks']['World Alignment']='PASS'
            from solid_geometry import part_solid,collision
            if collision(part_solid(ap,at),part_solid(bp,bt)):raise ValueError('MATE_COLLISION')
            rec['checks']['Collision']='PASS'
            rec.update(status='GEOMETRY_VERIFIED',feature_a=af['feature'],feature_b=bf['feature'],male=a['part_id'] if af['kind']=='tab' else b['part_id'],insertion_axis=aa if af['kind']=='tab' else ba)
            verified.append(rec)
        except (ValueError,KeyError,TypeError) as exc:
            rec['code']=str(exc);errors.append({'code':str(exc),'connector_id':cid,'target_connector':target})
        rows.append(rec)
    report={'active':active,'connectors':list(lookup.values()),'connections':rows,'errors':errors,'joints':[],'verified_slots':[],'sequence':{'status':'N/A','steps':[]}}
    if not active:return report
    # A declared assembly order is checked continuously, against installed solids.
    order=params.get('assembly_order')
    if order is None:
        order=[];remaining=set(owners)
        if remaining:order=[sorted(remaining)[0]];remaining.remove(order[0])
        while remaining:
            nxt=next((x for x in sorted(remaining) if any(x in {r['part_a'],r['part_b']} and ({r['part_a'],r['part_b']}-{x})&set(order) for r in verified)),None)
            if nxt is None:break
            order.append(nxt);remaining.remove(nxt)
        order+=sorted(remaining)
    if not isinstance(order,list) or len(order)!=len(owners) or set(order)!=set(owners):
        errors.append({'code':'ASSEMBLY_ORDER_INVALID'});return report
    from solid_geometry import part_solid,insertion_check
    installed=[];steps=[]
    try:
        for pid in order:
            linked=[r for r in verified if pid in {r['part_a'],r['part_b']} and ({r['part_a'],r['part_b']}-{pid})&{n for n,_ in installed}]
            from connection_validation import _role
            structural_installed=[n for n,_ in installed if _role(owners[n])[0]!='decorative']
            if structural_installed and not linked and _role(owners[pid])[0]!='decorative':raise ValueError('DISCONNECTED_STRUCTURAL_COMPONENT')
            direction=None
            if linked:
                axes=[[v*(1 if r['male']==pid else -1) for v in r['insertion_axis']] for r in linked]
                if any(dot(axes[0],a)<1-1e-5 for a in axes):raise ValueError('INSERTION_AXIS_CONFLICT')
                direction=axes[0]
                result=insertion_check(owners[pid],installed,direction,thickness)
                if result['status']!='PASS':raise ValueError(result['code']+':'+','.join(result['obstacles']))
                for r in linked:r['checks']['Insertion']='PASS';r.update(status='PASS',locked=True,reciprocal=True,geometry_verified=True)
            installed.append((pid,part_solid(owners[pid],float(owners[pid].get('thickness',thickness)))))
            steps.append({'step_number':len(steps)+1,'inserted_part':pid,'connected_to':[next(x for x in (r['part_a'],r['part_b']) if x!=pid) for r in linked],'mate_ids':[r['id'] for r in linked],'insertion_direction':direction,'assembled_parts':[p for p,_ in installed]})
        report['sequence']={'status':'PASS','order':order,'steps':steps}
    except (ValueError,KeyError,TypeError) as exc:
        errors.append({'code':str(exc)});report['sequence']={'status':'FAIL','steps':[],'reason':str(exc)}
    for r in rows:
        if r['status']!='PASS':continue
        report['joints'].append({'id':r['id'],'male':r['part_a'],'female':r['part_b'],'kind':'tab-slot','joint_type':'tab_slot','result':'MATCH','via':'explicit reciprocal connectors + CUT geometry + continuous insertion sweep','source':'explicit_connectors','connector_ids':[r['connector_a'],r['connector_b']]})
        for side in ('a','b'):
            if r['feature_'+side].startswith('inner:'):report['verified_slots'].append((r['part_'+side],int(r['feature_'+side].split(':')[1])))
    report['repair_scope']={'locked_mates':[r['id'] for r in rows if r['status']=='PASS'],
                            'failed_connectors':sorted({e.get('connector_id') for e in errors if e.get('connector_id')}),
                            'automatic_geometry_rewrite':False}
    return report
