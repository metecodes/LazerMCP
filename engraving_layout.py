"""Position text outlines and actual logo paths in mm, independently of kit geometry."""
from __future__ import annotations
import math
from xml.etree import ElementTree as ET
from markings import marking_geom
from number_match_puzzle import _emit
from text_path import to_lasercad_y
from design_engine import import_svg_document

def build_layout(params):
    width, height = float(params.get('width_mm', 300)), float(params.get('height_mm', 400))
    if not all(math.isfinite(v) and 0 < v <= 3000 for v in (width, height)):
        raise ValueError('Layout dimensions must be finite millimetres between 0 and 3000')
    items = params.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 500:
        raise ValueError('engraving_layout requires 1..500 text/path/icon/line items')
    root = ET.Element('svg', {'xmlns':'http://www.w3.org/2000/svg','width':f'{width}mm','height':f'{height}mm','viewBox':f'0 0 {width} {height}'})
    panel = ET.SubElement(root, 'rect', {'id':'engraving-panel','x':'0','y':'0','width':f'{width}','height':f'{height}',
        'fill':'none','stroke':'#FF0000','stroke-width':'.15','data-operation':'CUT','data-operation-origin':'EXPLICIT',
        'data-semantic-role':'outer_contour','data-physical-part':'true'})
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f'Item {i} must be an object')
        kind = item.get('kind', 'text')
        if kind not in {'text','path','icon','line','image'}:
            raise ValueError(f'Item {i}: unsupported kind {kind}')
        operation = str(item.get('operation', 'ENGRAVE')).upper()
        if operation not in {'ENGRAVE','CUT'}:
            raise ValueError(f'Item {i}: operation must be ENGRAVE or CUT')
        geom = marking_geom(item)
        if geom is None or geom.is_empty:
            raise ValueError(f'Item {i}: missing text or actual logo/vector geometry')
        bounds = geom.bounds
        if not all(math.isfinite(v) for v in bounds) or bounds[0] < 0 or bounds[1] < 0 or bounds[2] > width or bounds[3] > height:
            raise ValueError(f'Item {i}: outside layout; coordinates use mm, origin bottom-left')
        group = ET.SubElement(root, 'g', {'data-operation':operation,'data-semantic-role':'text' if kind == 'text' else 'logo', 'id':f'layout-item-{i}'})
        fragment = ET.fromstring('<svg>'+_emit(to_lasercad_y(geom, height), '#FFFF00' if operation=='ENGRAVE' else '#FF0000', .15)+'</svg>')
        for path in fragment:
            path.set('data-operation', operation)
            path.set('data-operation-origin', 'EXPLICIT')
            path.set('data-semantic-role', 'text' if kind == 'text' else 'logo')
            path.set('data-object-id', f'layout-item-{i}')
            group.append(path)
    built = import_svg_document(ET.tostring(root, encoding='unicode'), params)
    built.update({'preset':'engraving_layout','layout_items':len(items),'method':'positioned_vector_layout','physical_part_count':1})
    return built
