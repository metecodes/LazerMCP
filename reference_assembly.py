"""Combine explicit mechanical recipes with provided raster artwork in one compiler pass."""
import base64
import copy
from markings import marking_geom, _norm_name, _box_wall

def compose_reference(primitives, markings, encoded, image_bytes, parameters, output_format):
    if not primitives or not isinstance(markings,list) or not markings:
        raise ValueError('Mechanical reference requires primitives and reference_markings with explicit target_part, x,y and width/height')
    recipe=copy.deepcopy(primitives)
    if not encoded and image_bytes:
        encoded=base64.b64encode(image_bytes).decode()
    for raw in markings:
        item=copy.deepcopy(raw)
        target=item.get('target_part')
        if not target:
            raise ValueError('Every reference marking requires target_part; do not guess the destination panel')
        body,face=_box_wall(target)
        if face and face not in {'front','back','left','right','bottom','lid'}:
            raise ValueError(f'Unknown box face: {face}')
        matches=[p for p in recipe if isinstance(p,dict) and (
            (face and p.get('type')=='box' and (not body or body in {'box','body'} or _norm_name(body)==_norm_name(p.get('label',''))))
            or (not face and _norm_name(target)==_norm_name(p.get('label',''))))]
        if len(matches)!=1:
            raise ValueError(f'Unknown target panel: {target}')
        if 'x' not in item or 'y' not in item or not (item.get('width') or item.get('height')):
            raise ValueError(f'{target}: explicit x,y,width or height required')
        item.setdefault('kind','image')
        if item['kind']=='image':
            item.setdefault('image_base64',encoded)
            item['operation']='engrave'
        if marking_geom(item) is None:
            raise ValueError(f'{target}: missing artwork geometry')
        if face:
            matches[0].setdefault('walls',{}).setdefault(face,{}).setdefault('markings',[]).append(item)
        else:
            matches[0].setdefault('markings',[]).append(item)
    params=dict(parameters or {})
    params['format']=output_format
    params['reference_single_sheet']=True
    params['reference_job']=True
    params['reference_mode']='structural'
    return recipe,params
