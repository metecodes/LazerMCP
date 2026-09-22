"""Progressive assembly drawings from explicit, already-validated panel placements."""
from __future__ import annotations
from typing import Any
from assembled_view import outline, preview

_KIND_RANK={'floor':0,'wall':1,'contour':2,'panel':3,'gable':4,'roof':5,'disc':6,'propeller':7}

def _default_order(parts):
    def key(row):
        label=str(row.get('label') or '')
        kind=str(row.get('type') or row.get('kind') or '').lower()
        if label.lower() in {'bottom','floor','taban'}:rank=-1
        elif 'roof' in label.lower() or 'çatı' in label.lower():rank=5
        else:rank=_KIND_RANK.get(kind,3)
        return rank,label
    return [str(p['label']) for p in sorted(parts,key=key)]

def build_assembly_steps(primitives:list[Any]|None,assembly:dict[str,Any]|None,parameters:dict[str,Any]|None=None):
    params=parameters or {}; request=str(params.get('assembly_request') or params.get('user_request') or '').strip()
    if (assembly or {}).get('ok') is not True:
        return {'status':'NOT_AVAILABLE','reason':'Assembly steps require ASSEMBLY PASS.','request':request,'steps':[]}
    canonical=(assembly or {}).get('canonical_mates') or {}
    if canonical.get('active') and (canonical.get('sequence') or {}).get('status')!='PASS':
        return {'status':'BLOCKED','reason':'Verified insertion sequence required.','steps':[]}
    parts=[p for p in (primitives or []) if isinstance(p,dict) and p.get('label') and p.get('placement') and outline(p)]
    if not parts or len(parts)!=len([p for p in (primitives or []) if isinstance(p,dict)]):
        return {'status':'NOT_AVAILABLE','reason':'Assembly drawings require an explicit placement and outline for every physical part. No orientation is guessed.','request':request,'steps':[]}
    labels=[str(p['label']) for p in parts]
    requested=(canonical.get('sequence') or {}).get('order') if canonical.get('active') else params.get('assembly_order')
    if requested is not None:
        if not isinstance(requested,list) or len(requested)!=len(labels) or len(set(map(str,requested)))!=len(labels) or set(map(str,requested))!=set(labels):
            return {'status':'BLOCKED','reason':'parameters.assembly_order must contain every explicit part label exactly once.','request':request,'available_labels':labels,'steps':[]}
        order=list(map(str,requested))
    else:order=_default_order(parts)
    notes=params.get('assembly_notes') or []
    if isinstance(notes,str):notes=[notes]
    sequence=list((assembly or {}).get('sequence') or [])
    steps=[];visible=[]
    thickness=float((assembly or {}).get('thickness') or params.get('thickness') or 3)
    for index,label in enumerate(order,1):
        visible.append(label)
        instruction=str(notes[index-1]) if index-1<len(notes) else (str(sequence[index-1]) if index-1<len(sequence) else f'{label} parçasını doğrulanmış yerleşimine takın.')
        caption=f'Montaj {index}/{len(order)} — {label}: {instruction}'
        svg=preview(parts,thickness,visible_labels=visible,highlight_labels=[label],caption=caption)
        if not svg:return {'status':'BLOCKED','reason':'A verified progressive preview could not be rendered.','request':request,'steps':[]}
        edges=[e for e in ((assembly or {}).get('graph') or {}).get('edges') or [] if label in {str(e.get('from')),str(e.get('to'))}]
        pose=next(p.get('placement') for p in parts if str(p.get('label'))==label)
        steps.append({'step':index,'part':label,'mates':[e.get('to') if str(e.get('from'))==label else e.get('from') for e in edges],'connection_types':[e.get('type') for e in edges],'orientation':{'u':pose.get('u'),'v':pose.get('v')},'assembly_direction':pose.get('normal') or 'along verified mate normal','instruction':instruction,'svg_bytes':svg.encode('utf-8')})
        if canonical.get('active'):
            proof=canonical['sequence']['steps'][index-1]
            steps[-1].update(proof,assembly_direction=proof['insertion_direction'])
    return {'status':'AVAILABLE','legacy_status':'READY','request':request,'order':order,'steps':steps,'physical_fit':'NOT VERIFIED'}
