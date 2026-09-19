"""Fail-closed structural reference checks for photo-derived CAD."""
from __future__ import annotations
import re
from typing import Any
from shapely.geometry import Polygon

PASS='PASS';FAIL='FAIL';NOT_VERIFIED='NOT_VERIFIED'
def _name(value):
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())
def _kind(row):return str(row.get('type') or row.get('kind') or '').lower()
def _points(row):
    raw=row.get('points') or row.get('vertices') or row.get('contour')
    if not raw:return []
    try:return [(float(p[0]),float(p[1])) for p in raw]
    except (TypeError,ValueError,IndexError):return []

def _silhouette_check(reference,generated):
    expected=str(reference.get('expected_outer_shape') or reference.get('silhouette') or '').lower()
    kind=_kind(generated);points=_points(generated)
    if expected in {'contour','silhouette','custom','helicopter'} and (kind not in {'contour','outline','polygon'} or len(points)<3):
        return False,'reference silhouette is not the outer cut contour'
    refpts=reference.get('silhouette_points') or []
    if refpts:
        try:
            a=Polygon([(float(x),float(y)) for x,y in refpts]);b=Polygon(points)
            if not a.is_valid or not b.is_valid or a.area<=0 or b.area<=0:return False,'invalid reference or generated silhouette polygon'
            ax0,ay0,ax1,ay1=a.bounds;bx0,by0,bx1,by1=b.bounds
            an=Polygon([((x-ax0)/(ax1-ax0),(y-ay0)/(ay1-ay0)) for x,y in a.exterior.coords])
            bn=Polygon([((x-bx0)/(bx1-bx0),(y-by0)/(by1-by0)) for x,y in b.exterior.coords])
            distance=max(an.hausdorff_distance(bn),bn.hausdorff_distance(an))
            if distance>float(reference.get('max_normalized_distance',.12)):
                return False,f'outer CUT silhouette differs from reference (normalized distance {distance:.3f})'
        except (TypeError,ValueError,ZeroDivisionError):return False,'silhouette comparison could not be computed'
    if str(generated.get('operation') or 'CUT').upper()!='CUT':return False,'reference structural silhouette is not OUTER_CUT'
    return True,'generated OUTER_CUT represents the mapped reference silhouette'

def check_reference_fidelity(parameters:dict[str,Any]|None,primitives:list[Any]|None):
    params=parameters or {};active=bool(params.get('reference_job') or params.get('reference_mode')=='structural')
    empty={'active':False,'fidelity':[],'outer_cut':[],'part_mapping':[],'mapping':[]}
    if not active:return empty
    refs=params.get('reference_parts')
    if not isinstance(refs,list) or not refs:
        note='reference_parts evidence is required for a photo-derived structural design'
        return {'active':True,'fidelity':[{'status':NOT_VERIFIED,'note':note}],'outer_cut':[{'status':NOT_VERIFIED,'note':'reference structural silhouettes were not supplied'}],'part_mapping':[{'status':NOT_VERIFIED,'note':note}],'mapping':[]}
    generated=[p for p in (primitives or []) if isinstance(p,dict)]
    by_label={_name(p.get('label')):p for p in generated if p.get('label')}
    mapping=[];map_checks=[];outer=[];used=set()
    for index,ref in enumerate(refs,1):
        if not isinstance(ref,dict):map_checks.append({'status':FAIL,'note':f'reference part {index} is not an object'});continue
        refname=str(ref.get('reference_part') or ref.get('name') or f'reference-{index}');target=str(ref.get('generated_part') or '')
        hit=by_label.get(_name(target or refname))
        if not hit:map_checks.append({'status':FAIL,'note':f'{refname}: no generated_part mapping'});continue
        label=str(hit.get('label'));key=_name(label)
        if key in used:map_checks.append({'status':FAIL,'note':f'{refname}: generated part {label} is mapped more than once'});continue
        used.add(key);mapping.append({'reference_part':refname,'generated_part':label,'generated_kind':_kind(hit)})
        map_checks.append({'status':PASS,'note':f'{refname} → {label}'})
        if str(ref.get('role') or 'structural').lower() not in {'engrave','decoration','graphic','text'}:
            ok,note=_silhouette_check(ref,hit);outer.append({'status':PASS if ok else FAIL,'note':f'{refname} → {label}: {note}'})
    expected=sum(int(r.get('count',1)) for r in refs if isinstance(r,dict))
    if expected!=len(mapping):map_checks.append({'status':FAIL,'note':f'reference part mapping count {len(mapping)}/{expected}'})
    return {'active':True,'fidelity':list(map_checks)+list(outer),'outer_cut':outer or [{'status':NOT_VERIFIED,'note':'no structural reference silhouette mapped'}],'part_mapping':map_checks,'mapping':mapping}
