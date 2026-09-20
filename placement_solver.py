"""Derive only uniquely constrained 90-degree tab/slot placements."""
from __future__ import annotations
import math
from assembled_view import world

def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _sub(a,*terms):return [a[i]-sum(float(scale)*float(vec[i]) for scale,vec in terms) for i in range(3)]
def _direction(tab):
    side=str(tab.get('side') or tab.get('edge') or tab.get('id') or '').strip().lower()
    return side if side in {'l','left','r','right','t','top','b','bottom'} else None

def derive_placements(parts,thickness=3.0):
    lookup={str(p.get('label')):p for p in parts if isinstance(p,dict) and p.get('label')};notes=[]
    changed=True
    while changed:
        changed=False
        for female in lookup.values():
            for slot in female.get('slots') or []:
                mate=slot.get('mate') or {};male=lookup.get(str(mate.get('part') or ''))
                tab=next((t for t in (male or {}).get('tabs') or [] if str(t.get('id'))==str(mate.get('tab'))),None)
                if not male or not tab:continue
                fp,mp=female.get('placement'),male.get('placement');side=_direction(tab)
                if fp and mp:continue
                if not side:
                    notes.append({'status':'PLACEMENT_AMBIGUOUS','part':str((male if not mp else female).get('label')),'reason':'tab needs side/edge or directional L/R/T/B id'});continue
                sx,sy=float(slot.get('x') or 0),float(slot.get('y') or 0);tx,ty=float(tab.get('x') or 0),float(tab.get('y') or 0);half=float(thickness)/2
                if fp and not mp:
                    fu,fv=fp['u'],fp['v'];fn=_cross(fu,fv);mu,mv=fn,fu;mn=_cross(mu,mv)
                    target=world(female,sx,sy,half);origin=_sub(target,(tx,mu),(ty,mv),(half,mn));male['placement']={'origin':origin,'u':mu,'v':mv,'source':'constraint'}
                    notes.append({'status':'DERIVED','part':male.get('label'),'via':f'{female.get("label")} slot → {mate.get("tab")}' });changed=True
                elif mp and not fp:
                    mu,mv=mp['u'],mp['v'];mn=_cross(mu,mv);fn=mu;fu=mv;fv=mn
                    target=world(male,tx,ty,half);origin=_sub(target,(sx,fu),(sy,fv),(half,fn));female['placement']={'origin':origin,'u':fu,'v':fv,'source':'constraint'}
                    notes.append({'status':'DERIVED','part':female.get('label'),'via':f'{male.get("label")}.{mate.get("tab")} → slot'});changed=True
    for p in lookup.values():
        if p.get('placement'):continue
        involved=any(str((s.get('mate') or {}).get('part') or '')==str(p.get('label')) for q in lookup.values() for s in q.get('slots') or []) or bool(p.get('slots'))
        if involved and not any(n.get('part')==p.get('label') and n.get('status')=='PLACEMENT_AMBIGUOUS' for n in notes):notes.append({'status':'PLACEMENT_AMBIGUOUS','part':p.get('label'),'reason':'constraints do not reach an explicitly placed anchor'})
    for note in notes:
        if note.get('status')=='PLACEMENT_AMBIGUOUS' and note.get('part') in lookup:lookup[note['part']]['_placement_error']='PLACEMENT_AMBIGUOUS'
    return notes
