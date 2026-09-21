"""General, product-neutral semantic composition over laser SVG geometry."""
from __future__ import annotations
import copy, json, math, uuid
from xml.etree import ElementTree as ET
import numpy as np
from shapely.affinity import affine_transform, rotate, scale, translate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from shapely.ops import polylabel
from svgpathtools import Line, parse_path
from svgpathtools.parser import parse_transform
from svgpathtools.path import transform
from manufacturing import classify_element, finish_manufacturing_svg
from markings import marking_geom
from number_match_puzzle import _emit

OPS={'CUT','ENGRAVE','SCORE','GUIDE','UNKNOWN'}
DRAW={'path','rect','circle','ellipse','line','polyline','polygon'}

def _id(prefix):return prefix+'_'+uuid.uuid4().hex[:10].upper()
def create_text(content, **kw):
    if not str(content).strip():raise ValueError('text content is required')
    explicit='position' in kw
    return {'id':kw.pop('id',_id('TXT')),'type':'text','content':str(content),'semantic_role':'text','operation':kw.pop('operation','ENGRAVE'),'position':kw.pop('position',{'x':0,'y':0}),'_position_explicit':explicit,'size':kw.pop('size',{'width':0,'height':float(kw.get('font_size',6))}),'rotation':float(kw.pop('rotation',0)),'parent_part_id':kw.pop('parent_part_id',None),'source':kw.pop('source','native_text'),'locked':bool(kw.pop('locked',False)),'font_family':kw.pop('font_family','Arial'),'font_weight':kw.pop('font_weight','normal'),'font_size':float(kw.pop('font_size',6)),'letter_spacing':float(kw.pop('letter_spacing',0)),'line_height':float(kw.pop('line_height',1.1)),'alignment':kw.pop('alignment','center'),**kw}
def create_vector_graphic(d=None, **kw):
    if not d and not kw.get('points'):raise ValueError('vector path or points required')
    explicit='position' in kw
    role=kw.pop('semantic_role',kw.pop('graphic_type','illustration'))
    return {'id':kw.pop('id',_id('GFX')),'type':'graphic','d':d,'points':kw.pop('points',None),'semantic_role':role,'operation':kw.pop('operation','ENGRAVE'),'position':kw.pop('position',{'x':0,'y':0}),'_position_explicit':explicit,'size':kw.pop('size',{'width':0,'height':0}),'rotation':float(kw.pop('rotation',0)),'parent_part_id':kw.pop('parent_part_id',None),'source':kw.pop('source','native_vector'),'locked':bool(kw.pop('locked',False)),**kw}
def create_image_reference(image_base64, **kw):
    if not isinstance(image_base64,str) or not image_base64:raise ValueError('image_base64 is required')
    explicit='position' in kw
    return {'id':kw.pop('id',_id('GFX')),'type':'image_reference','image_base64':image_base64,'semantic_role':kw.pop('semantic_role','illustration'),'operation':'ENGRAVE','position':kw.pop('position',{'x':0,'y':0}),'_position_explicit':explicit,'size':kw.pop('size',{'width':kw.pop('width',0),'height':kw.pop('height',0)}),'rotation':float(kw.pop('rotation',0)),'parent_part_id':kw.pop('parent_part_id',None),'source':kw.pop('source','reference_image'),'locked':bool(kw.pop('locked',False)),'trace_quality':kw.pop('trace_quality','exact'),'crop':kw.pop('crop',[]),'foreground':kw.pop('foreground','auto'),**kw}
def import_svg_graphic(svg, **kw):
    from design_engine import import_svg_document
    built=import_svg_document(svg,{'svg_default_operation':'ENGRAVE'});doc=inspect_design(built['svg_bytes'])
    geoms=[o['_geom'] for o in doc['_objects'] if o['operation']=='ENGRAVE']
    if not geoms:raise ValueError('SVG graphic has no ENGRAVE vector geometry')
    geom=unary_union(geoms);fragment=ET.fromstring('<svg>'+_emit(geom,'#FFFF00',.15)+'</svg>')
    return create_vector_graphic(' '.join(p.get('d','') for p in fragment),source='imported_svg',**kw)

def create_primitive(kind, **kw):
    kind=str(kind).lower();w=float(kw.pop('width',10));h=float(kw.pop('height',w));r=float(kw.pop('radius',min(w,h)/2));points=kw.pop('points',None);provided_d=kw.pop('d',None)
    if kind=='rectangle':d=f'M0 0 H{w} V{h} H0 Z'
    elif kind=='rounded_rectangle':
        corner=min(r,w/2,h/2);d=f'M{corner} 0 H{w-corner} A{corner} {corner} 0 0 1 {w} {corner} V{h-corner} A{corner} {corner} 0 0 1 {w-corner} {h} H{corner} A{corner} {corner} 0 0 1 0 {h-corner} V{corner} A{corner} {corner} 0 0 1 {corner} 0 Z'
    elif kind=='line':d=f'M0 0 L{w} {h}'
    elif kind=='circle':d=f'M{r} 0 A{r} {r} 0 1 1 {r} {2*r} A{r} {r} 0 1 1 {r} 0 Z'
    elif kind=='ellipse':d=f'M{w/2} 0 A{w/2} {h/2} 0 1 1 {w/2} {h} A{w/2} {h/2} 0 1 1 {w/2} 0 Z'
    elif kind in {'polyline','polygon'}:
        if not points:raise ValueError('points required')
        d='M'+' L'.join(f'{float(p[0])} {float(p[1])}' for p in points)+(' Z' if kind=='polygon' else '')
    elif kind in {'path','bezier','arc'}:
        d=provided_d
        if not d:raise ValueError('d path required')
    else:raise ValueError('kind must be line, polyline, rectangle, rounded_rectangle, circle, ellipse, arc, polygon, bezier or path')
    return create_vector_graphic(d,graphic_type='primitive',size={'width':w,'height':h},source='native_primitive:'+kind,**kw)
def edit_object(obj, changes):
    out=copy.deepcopy(obj)
    if out.get('locked'):raise ValueError('object is locked')
    for key,value in changes.items():
        if key not in {'id','type'}:out[key]=value
    if 'position' in changes:out['_position_explicit']=True
    return out

def _doc_size(root):
    def n(value):
        import re
        m=re.search(r'[-+0-9.eE]+',value or '');return float(m.group()) if m else None
    vb=[float(x) for x in (root.get('viewBox') or '').replace(',',' ').split()]
    return ((n(root.get('width')) or (vb[2] if len(vb)==4 else 0)),(n(root.get('height')) or (vb[3] if len(vb)==4 else 0)))
def _parents(root):return {c:p for p in root.iter() for c in p}
def _matrix(el,parents,width=0,height=0):
    chain=[]
    while el is not None:chain.append(el);el=parents.get(el)
    out=np.eye(3)
    for node in reversed(chain):out=out@parse_transform(node.get('transform') or '')
    root=chain[-1] if chain else None
    if root is not None:
        try:
            vb=[float(v) for v in (root.get('viewBox') or '').replace(',',' ').split()]
            if len(vb)==4 and vb[2] and vb[3] and width and height:
                viewport=np.array([[width/vb[2],0,-vb[0]*width/vb[2]],[0,height/vb[3],-vb[1]*height/vb[3]],[0,0,1]])
                out=viewport@out
        except ValueError:pass
    return out
def _path_geoms(el,parents,width,height):
    tag=el.tag.split('}')[-1]
    if tag!='path':
        from shapely.geometry import Point
        try:
            if tag=='rect':raw=box(float(el.get('x',0)),float(el.get('y',0)),float(el.get('x',0))+float(el.get('width')),float(el.get('y',0))+float(el.get('height')))
            elif tag in {'circle','ellipse'}:
                cx,cy=float(el.get('cx',0)),float(el.get('cy',0));raw=Point(cx,cy).buffer(1,resolution=48);raw=scale(raw,float(el.get('r') or el.get('rx')),float(el.get('r') or el.get('ry')),origin=(cx,cy))
            elif tag=='line':raw=LineString([(float(el.get('x1',0)),float(el.get('y1',0))),(float(el.get('x2',0)),float(el.get('y2',0)))])
            elif tag in {'polyline','polygon'}:
                import re
                nums=[float(v) for v in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',el.get('points',''))];coords=list(zip(nums[::2],nums[1::2]));raw=Polygon(coords) if tag=='polygon' else LineString(coords)
            else:return []
            matrix=_matrix(el,parents,width,height);a,b,c,d,e,f=matrix[0,0],matrix[1,0],matrix[0,1],matrix[1,1],matrix[0,2],matrix[1,2];raw=affine_transform(raw,[a,c,b,d,e,f]);return [affine_transform(raw,[1,0,0,-1,0,height])]
        except (TypeError,ValueError):return []
    if not el.get('d'):return []
    raw_path = parse_path(el.get('d'))
    if el.get('data-holding-nicks') and classify_element(el,parents)[0] == 'CUT':
        from svgpathtools import Path as SVGPath
        from holding_nicks import NICK_MM
        subs = list(raw_path.continuous_subpaths())
        if subs and all(abs(subs[i].end-subs[(i+1)%len(subs)].start) <= NICK_MM + .8 for i in range(len(subs))):
            segments = []
            for i, sub in enumerate(subs):
                segments.extend(sub)
                end = subs[(i+1)%len(subs)].start
                if abs(sub.end-end) > 1e-9:
                    segments.append(Line(sub.end,end))
            raw_path = SVGPath(*segments)
    path=transform(raw_path,_matrix(el,parents,width,height));result=[]
    for sub in path.continuous_subpaths():
        pts=[]
        for seg in sub:
            count=1 if isinstance(seg,Line) else max(3,min(200,math.ceil(seg.length()/.35)))
            if not pts:pts.append(seg.start)
            pts.extend(seg.point(i/count) for i in range(1,count+1))
        coords=[(p.real,height-p.imag) for p in pts]
        if len(coords)>2 and sub.isclosed() and el.get('data-object-type') not in {'text','graphic','image_reference'}:
            poly=Polygon(coords)
            result.append(poly if poly.is_valid else poly.buffer(0))
        elif len(coords)>1:result.append(LineString(coords))
    return result
def inspect_design(svg):
    root=ET.fromstring(svg.encode() if isinstance(svg,str) else svg);width,height=_doc_size(root);parents=_parents(root)
    objects=[]
    for i,el in enumerate(root.iter()):
        if el.tag.split('}')[-1] not in DRAW:continue
        op,role,origin=classify_element(el,parents)
        for j,geom in enumerate(_path_geoms(el,parents,width,height)):
            if geom.is_empty:continue
            objects.append({'id':el.get('data-object-id') or el.get('id') or f'OBJ_{i}_{j}','type':el.get('data-object-type') or ('geometry' if op=='CUT' else 'graphic'),'content':el.get('data-content') or '', 'semantic_role':role,'operation':op,'position':{'x':geom.centroid.x,'y':geom.centroid.y},'size':{'width':geom.bounds[2]-geom.bounds[0],'height':geom.bounds[3]-geom.bounds[1]},'rotation':0,'parent_part_id':el.get('data-parent-part-id'),'source':origin,'locked':el.get('data-locked')=='true','bounds':list(geom.bounds),'_geom':geom})
    combined=[]
    for oid in {o['id'] for o in objects if o['id'].startswith(('TXT_','GFX_'))}:
        rows=[o for o in objects if o['id']==oid]
        if not rows:continue
        geom=unary_union([o['_geom'] for o in rows]);row=rows[0].copy();row['_geom']=geom;row['bounds']=list(geom.bounds);row['position']={'x':geom.centroid.x,'y':geom.centroid.y};row['size']={'width':geom.bounds[2]-geom.bounds[0],'height':geom.bounds[3]-geom.bounds[1]};combined.append(row)
        objects=[o for o in objects if o['id']!=oid]
    objects.extend(combined)
    cuts=[o for o in objects if o['operation']=='CUT' and o['_geom'].geom_type in {'Polygon','MultiPolygon'} and o['_geom'].area>1]
    frames={id(o) for o in cuts if width and height and (o['_geom'].bounds[2]-o['_geom'].bounds[0])>=width*.95 and (o['_geom'].bounds[3]-o['_geom'].bounds[1])>=height*.95 and sum(o['_geom'].covers(c['_geom']) for c in cuts if c is not o)>=2}
    parts=[]
    for obj in cuts:
        geom=obj['_geom']
        if id(obj) in frames:continue
        containers=[c for c in cuts if c is not obj and id(c) not in frames and c['_geom'].covers(geom)]
        if containers:continue
        pid=obj['id'];obj['semantic_role']='part_outer';obj['parent_part_id']=pid
        features=[]
        for candidate in cuts:
            if candidate is not obj and geom.covers(candidate['_geom']):
                candidate['semantic_role']='cut_feature';candidate['parent_part_id']=pid;features.append(candidate['id'])
        parts.append({'id':pid,'bounds':list(geom.bounds),'area':geom.area,'feature_ids':features,'_geom':geom})
    clean=lambda row:{k:v for k,v in row.items() if not k.startswith('_')}
    return {'width_mm':width,'height_mm':height,'objects':[clean(o) for o in objects],'parts':[clean(p) for p in parts],'unknown_count':sum(o['operation']=='UNKNOWN' for o in objects),'_root':root,'_objects':objects,'_parts':parts}

def compute_safe_design_area(svg,part_id,safe_margin=3,mechanical_clearance=1):
    doc=inspect_design(svg);part=next((p for p in doc['_parts'] if p['id']==part_id),None)
    if not part:raise ValueError(f'part not found: {part_id}')
    margin=max(float(safe_margin),0);safe=part['_geom'].buffer(-margin)
    features=[o['_geom'] for o in doc['_objects'] if o['parent_part_id']==part_id and o['semantic_role']=='cut_feature']
    if features:safe=safe.difference(unary_union(features).buffer(max(0,float(mechanical_clearance))))
    return {'part_id':part_id,'safe_margin':margin,'mechanical_clearance':mechanical_clearance,'bounds':list(safe.bounds) if not safe.is_empty else [],'area':safe.area,'wkt':safe.wkt,'_geom':safe,'document':doc}
def get_part_bounds(svg,part_id):
    row=compute_safe_design_area(svg,part_id,0,0);return {'part_id':part_id,'bounds':row['document']['parts'][next(i for i,p in enumerate(row['document']['parts']) if p['id']==part_id)]['bounds']}

def _element_geom(item):
    typ=item.get('type')
    if typ=='text':
        lines=str(item.get('content','')).splitlines() or [''];size=float(item.get('font_size',6));lh=float(item.get('line_height',1.1));bits=[]
        from text_path import layout_text
        for index,line in enumerate(lines):
            geom=layout_text(line,0,-index*size*lh,size,y_up=True,anchor='center',baseline='center',letter_spacing_mm=float(item.get('letter_spacing',0)),font_weight=str(item.get('font_weight','normal')))
            if geom is not None:bits.append(geom)
        geom=unary_union(bits) if bits else None
    elif typ in {'graphic','image_reference'}:
        mark={'kind':'image' if typ=='image_reference' else 'path','d':item.get('d'),'points':item.get('points'),'image_base64':item.get('image_base64'),'crop':item.get('crop',[]),'ink_color':item.get('ink_color',''),'foreground':item.get('foreground','auto'),'threshold':item.get('threshold'),'trace_quality':item.get('trace_quality','exact'),'width':item.get('size',{}).get('width') or item.get('width'),'height':item.get('size',{}).get('height') or item.get('height'),'x':0,'y':0,'operation':'engrave'}
        geom=marking_geom(mark)
    else:raise ValueError(f'unsupported semantic object: {typ}')
    if geom is None or geom.is_empty:raise ValueError('element has no vector geometry')
    return geom
def _placed(item,safe,features):
    geom=_element_geom(item);placement=item.get('placement','center');zone=safe
    region=item.get('target_box') or item.get('region')
    if region:
        if isinstance(region,dict):rx,ry,rw,rh=map(float,(region.get('x',0),region.get('y',0),region.get('width',0),region.get('height',0)))
        elif len(region)==4:rx,ry,rw,rh=map(float,region)
        else:raise ValueError('target_box must be {x,y,width,height} or [x,y,width,height]')
        if rw<=0 or rh<=0:raise ValueError('target_box width and height must be positive')
        zone=safe.intersection(box(rx,ry,rx+rw,ry+rh))
        if zone.is_empty:raise ValueError('target_box does not intersect safe design area')
    minx,miny,maxx,maxy=zone.bounds;scale_factor=1.0
    wanted=item.get('size') or {}
    if wanted.get('width') or wanted.get('height'):
        gb=geom.bounds;ratio=min(float(wanted.get('width') or 1e99)/max(gb[2]-gb[0],1e-9),float(wanted.get('height') or 1e99)/max(gb[3]-gb[1],1e-9))
        geom=scale(geom,xfact=ratio,yfact=ratio,origin='centroid');scale_factor*=ratio
    if item.get('type')=='text' and item.get('auto_fit',True):
        gb=geom.bounds;fit_w=float(item.get('max_width') or (maxx-minx));fit_h=float(item.get('max_height') or (maxy-miny));ratio=min(1.0,fit_w/max(gb[2]-gb[0],1e-9),fit_h/max(gb[3]-gb[1],1e-9))
        effective=float(item.get('font_size',6))*scale_factor*ratio
        if effective<float(item.get('min_font_size',1.5)):raise ValueError(f'text cannot fit target area above minimum font size {item.get("min_font_size",1.5)} mm')
        if ratio<1:geom=scale(geom,xfact=ratio,yfact=ratio,origin='centroid');scale_factor*=ratio
    gb=geom.bounds;hw=(gb[2]-gb[0])/2;hh=(gb[3]-gb[1])/2
    anchors={'center':((minx+maxx)/2,(miny+maxy)/2),'top_center':((minx+maxx)/2,maxy-hh),'bottom_center':((minx+maxx)/2,miny+hh),'bottom_left':(minx+hw,miny+hh),'bottom_right':(maxx-hw,miny+hh),'top_left':(minx+hw,maxy-hh),'top_right':(maxx-hw,maxy-hh)}
    constraints=item.get('constraints') or []
    if isinstance(constraints,str):constraints=[constraints]
    if item.get('anchor_feature_id'):
        feature=next((g for fid,g in features if fid==item['anchor_feature_id']),None)
        if feature is None:raise ValueError('anchor feature not found')
        target=(feature.centroid.x+float(item.get('offset_x',0)),feature.centroid.y+float(item.get('offset_y',0)))
    elif item.get('_position_explicit') and isinstance(item.get('position'),dict):target=(float(item['position'].get('x',(minx+maxx)/2)),float(item['position'].get('y',(miny+maxy)/2)))
    else:target=anchors.get(placement,anchors['center'])
    if 'center_x' in constraints:target=((minx+maxx)/2,target[1])
    if 'center_y' in constraints:target=(target[0],(miny+maxy)/2)
    gb=geom.bounds;geom=translate(geom,target[0]-(gb[0]+gb[2])/2,target[1]-(gb[1]+gb[3])/2)
    if item.get('rotation'):geom=rotate(geom,float(item['rotation']),origin='centroid')
    attempts=0
    while attempts<5 and not zone.covers(geom):
        ratio=min((maxx-minx)/max(geom.bounds[2]-geom.bounds[0],1e-6),(maxy-miny)/max(geom.bounds[3]-geom.bounds[1],1e-6),.85)
        geom=scale(geom,xfact=ratio,yfact=ratio,origin='centroid')
        scale_factor*=ratio
        fit_zone=max((list(zone.geoms) if hasattr(zone,'geoms') else [zone]),key=lambda g:g.area);p=polylabel(fit_zone,tolerance=.25)
        geom=translate(geom,p.x-geom.centroid.x,p.y-geom.centroid.y);attempts+=1
    if item.get('type')=='text' and float(item.get('font_size',6))*scale_factor<float(item.get('min_font_size',1.5)):raise ValueError('automatic fitting would make text smaller than min_font_size')
    return geom,attempts,scale_factor
def _signature(item,geom):return (item.get('type'),str(item.get('content','')).casefold().strip(),item.get('parent_part_id'),tuple(round(v,1) for v in geom.bounds))
def compose_design(svg,elements,safe_margin=3,mechanical_clearance=1,duplicate_policy='replace'):
    if not isinstance(elements,list) or not elements:raise ValueError('elements required')
    if duplicate_policy not in {'replace','ask'}:raise ValueError('duplicate_policy must be replace or ask')
    doc=inspect_design(svg);root=doc['_root'];height=doc['height_mm'];existing={};added=[];issues=[];parents=_parents(root)
    for old in doc['_objects']:
        if old['id'].startswith(('TXT_','GFX_')):existing[_signature(old,old['_geom'])]=old['id']
    group=ET.SubElement(root,'{http://www.w3.org/2000/svg}g',{'id':'ENGRAVE-COMPOSITION','data-operation':'ENGRAVE'})
    for raw in elements:
        item=copy.deepcopy(raw);item.setdefault('id',_id('TXT' if item.get('type')=='text' else 'GFX'));item.setdefault('operation','ENGRAVE');item.setdefault('semantic_role','text' if item.get('type')=='text' else 'illustration');item.setdefault('locked',False);item.setdefault('source','composition')
        if item['operation']!='ENGRAVE':issues.append({'status':'FAIL','object_id':item['id'],'note':'composition text/graphics must explicitly use ENGRAVE'});continue
        pid=item.get('parent_part_id');safe_info=compute_safe_design_area(svg,pid,safe_margin,mechanical_clearance);safe=safe_info['_geom'];features=[(o['id'],o['_geom']) for o in safe_info['document']['_objects'] if o['parent_part_id']==pid and o['semantic_role']=='cut_feature']
        try:geom,attempts,scale_factor=_placed(item,safe,features)
        except ValueError as exc:issues.append({'status':'FAIL','object_id':item['id'],'note':str(exc)});continue
        sig=_signature(item,geom)
        if sig in existing:
            if duplicate_policy=='ask':issues.append({'status':'WARNING','object_id':item['id'],'note':'semantic duplicate skipped; choose replace to overwrite'});continue
            oldid=existing[sig]
            for node in list(root.iter()):
                if node.get('data-object-id')==oldid and parents.get(node) is not None:parents[node].remove(node)
            issues.append({'status':'WARNING','object_id':item['id'],'note':'semantic duplicate replaced'})
        existing[sig]=item['id']
        if not safe.covers(geom):issues.append({'status':'FAIL','object_id':item['id'],'note':'cannot fit inside safe design area'});continue
        svggeom=affine_transform(geom,[1,0,0,-1,0,height]);fragment=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'+_emit(svggeom,'#FFFF00',.15)+'</svg>')
        for path in fragment:
            path.set('data-object-id',item['id']);path.set('data-object-type',item['type']);path.set('data-parent-part-id',pid);path.set('data-semantic-role',item['semantic_role']);path.set('data-operation','ENGRAVE');path.set('data-operation-origin','EXPLICIT');path.set('data-source',item['source']);path.set('data-locked',str(bool(item['locked'])).lower());path.set('data-content',item.get('content',''));group.append(path)
        added.append({**item,'bounds':list(geom.bounds),'repair_attempts':attempts,'effective_font_size':float(item.get('font_size',0))*scale_factor if item.get('type')=='text' else None,'scale_factor':scale_factor})
    raw=ET.tostring(root,encoding='utf-8',xml_declaration=True);final,manufacturing=finish_manufacturing_svg(raw)
    validation=validate_composition(final,safe_margin,mechanical_clearance)
    return {'success':not any(x['status']=='FAIL' for x in issues+validation['issues']),'svg':final.decode(),'objects':added,'issues':issues+validation['issues'],'manufacturing':manufacturing,'validation':validation}
def validate_composition(svg,safe_margin=3,mechanical_clearance=1):
    doc=inspect_design(svg);issues=[];seen=set()
    semantic=[o for o in doc['_objects'] if o['type']=='graphic' and o['parent_part_id']]
    for obj in semantic:
        try:safe=compute_safe_design_area(svg,obj['parent_part_id'],safe_margin,mechanical_clearance)['_geom']
        except ValueError:issues.append({'status':'FAIL','object_id':obj['id'],'note':'parent part missing'});continue
        if obj['operation']=='UNKNOWN':issues.append({'status':'FAIL','object_id':obj['id'],'note':'UNKNOWN operation'})
        if not safe.covers(obj['_geom']):issues.append({'status':'FAIL','object_id':obj['id'],'note':'outside safe design area or intersects mechanical feature'})
        sig=(obj['parent_part_id'],tuple(round(v,1) for v in obj['_geom'].bounds))
        if sig in seen:issues.append({'status':'WARNING','object_id':obj['id'],'note':'possible duplicate graphic/text'})
        seen.add(sig)
        if max(obj['size'].values())<.5:issues.append({'status':'WARNING','object_id':obj['id'],'note':'engraving detail may be too small'})
    for index,left in enumerate(semantic):
        for right in semantic[index+1:]:
            if left['parent_part_id']!=right['parent_part_id']:continue
            overlap=box(*left['_geom'].bounds).intersection(box(*right['_geom'].bounds))
            if overlap.area>.05:
                issues.append({'status':'FAIL','object_id':right['id'],'note':f"composition bounds overlap {left['id']}"})
    if doc['unknown_count']:issues.append({'status':'FAIL','object_id':None,'note':f"UNKNOWN operations: {doc['unknown_count']}"})
    return {'status':'FAIL' if any(i['status']=='FAIL' for i in issues) else 'WARNING' if issues else 'PASS','issues':issues,'object_count':len(semantic),'part_count':len(doc['_parts'])}
def export_dxf(svg):
    from dxf_export import svg_bytes_to_dxf
    return svg_bytes_to_dxf(svg.encode() if isinstance(svg,str) else svg)

def convert_text_to_paths(obj):
    if obj.get('type')!='text':raise ValueError('text object required')
    geom=_element_geom(obj)
    return {'id':obj.get('id'),'type':'graphic','semantic_role':'text','operation':obj.get('operation','ENGRAVE'),'parent_part_id':obj.get('parent_part_id'),'d':_emit(geom,'#FFFF00',.15),'bounds':list(geom.bounds),'source':'text_to_paths','locked':obj.get('locked',False)}

def repair_composition(svg,safe_margin=3,mechanical_clearance=1):
    doc=inspect_design(svg);root=doc['_root'];parents=_parents(root);elements=[]
    semantic=[o for o in doc['_objects'] if o['id'].startswith(('TXT_','GFX_'))]
    for obj in semantic:
        if obj['type']=='text' and obj.get('content'):
            elements.append(create_text(obj['content'],id=obj['id'],parent_part_id=obj['parent_part_id'],font_size=max(1,obj['size']['height']),position=obj['position']))
        else:
            fragment=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'+_emit(obj['_geom'],'#FFFF00',.15)+'</svg>')
            d=' '.join(p.get('d','') for p in fragment)
            elements.append(create_vector_graphic(d,id=obj['id'],parent_part_id=obj['parent_part_id'],position=obj['position'],semantic_role=obj['semantic_role']))
    for el in list(root.iter()):
        if el.get('data-object-id','').startswith(('TXT_','GFX_')):
            parent=parents.get(el)
            if parent is not None:parent.remove(el)
    return compose_design(ET.tostring(root,encoding='unicode'),elements,safe_margin,mechanical_clearance)
def remove_object(svg,object_id):
    root=ET.fromstring(svg.encode() if isinstance(svg,str) else svg);parents=_parents(root);found=0
    for el in list(root.iter()):
        if el.get('data-object-id')==object_id and parents.get(el) is not None:parents[el].remove(el);found+=1
    if not found:raise ValueError('semantic object not found')
    return ET.tostring(root,encoding='unicode')
def replace_object(svg,object_id,replacement,safe_margin=3,mechanical_clearance=1):
    replacement=copy.deepcopy(replacement);replacement['id']=object_id
    return compose_design(remove_object(svg,object_id),[replacement],safe_margin,mechanical_clearance)

def align_objects(objects, mode, bounds=None):
    rows=copy.deepcopy(objects);mode=str(mode).lower()
    if not rows:return rows
    if bounds:
        left,bottom,right,top=map(float,bounds)
    else:
        left=min(o['position']['x']-o.get('size',{}).get('width',0)/2 for o in rows);right=max(o['position']['x']+o.get('size',{}).get('width',0)/2 for o in rows);bottom=min(o['position']['y']-o.get('size',{}).get('height',0)/2 for o in rows);top=max(o['position']['y']+o.get('size',{}).get('height',0)/2 for o in rows)
    for o in rows:
        w=o.get('size',{}).get('width',0);h=o.get('size',{}).get('height',0)
        if mode=='left':o['position']['x']=left+w/2
        elif mode=='right':o['position']['x']=right-w/2
        elif mode=='top':o['position']['y']=top-h/2
        elif mode=='bottom':o['position']['y']=bottom+h/2
        elif mode=='center_x':o['position']['x']=(left+right)/2
        elif mode=='center_y':o['position']['y']=(bottom+top)/2
        else:raise ValueError('mode must be left/right/top/bottom/center_x/center_y')
    return rows
def distribute_objects(objects,axis='horizontal'):
    rows=copy.deepcopy(objects);key='x' if axis=='horizontal' else 'y'
    if axis not in {'horizontal','vertical'}:raise ValueError('axis must be horizontal or vertical')
    rows.sort(key=lambda o:o['position'][key])
    if len(rows)>2:
        start,end=rows[0]['position'][key],rows[-1]['position'][key]
        for i,o in enumerate(rows):o['position'][key]=start+(end-start)*i/(len(rows)-1)
    return rows
