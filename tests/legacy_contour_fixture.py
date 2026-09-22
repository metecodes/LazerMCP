from copy import deepcopy
from house_holder import recipe
from toolbox import _materialize_cut_geometry

def legacy_house(thickness=3):
    t=thickness;parts=deepcopy(recipe(thickness=t)[:5])
    for p in parts:
        p['role']='structural'
        p['thickness']=t
        p['slots']=[s for s in p.get('slots',[]) if s.get('mate') and s['mate']['part']!='divider']
        for s in p['slots']:
            if s['w']>s['h']:s['w']=24
            else:s['h']=24
        for tab in p.get('tabs',[]):
            if tab['w']>tab['h']:tab['w']=24
            else:tab['h']=24
        if p.get('tabs'):
            width=90-2*t if p['label']!='floor' else 130-4*t
            height=130 if p['label']!='floor' else 90-2*t
            p['points']=[[0,0],[width,0],[width,height],[0,height]]
        q=_materialize_cut_geometry(p)
        p.clear();p.update(q)
        p.pop('tabs',None)
        p['_cut_geometry']['tabs']=[]
        for s in p['slots']:s.pop('mate',None)
        for s in p['_cut_geometry']['inner_cuts']:s.pop('mate',None)
    return parts
