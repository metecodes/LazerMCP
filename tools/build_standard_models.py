"""Publish the supplied SVG, closing only bounded endpoint gaps.

No scaling, kerf compensation, contour regeneration or assembly invention.
Offset orthogonal gaps are squared; zero-area micro returns are bounded to 0.03 mm.
"""
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from svgpathtools import Path as SVGPath, Line, parse_path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standard_models import ROOT, MODEL_ID
from dxf_export import svg_bytes_to_dxf
from topology import inspect_topology

SOURCE = ROOT/'assets/standard-models/house-pencil-holder.source.svg'


def _axis(segment):
    delta = segment.end-segment.start
    if abs(delta.imag)<1e-8 and abs(delta.real)>1e-8: return 'x'
    if abs(delta.real)<1e-8 and abs(delta.imag)>1e-8: return 'y'
    return None


def gap_segments(a, b, before, after):
    """Preserve real slopes; bridge offset orthogonal runs with square corners."""
    axis = _axis(before)
    if axis and axis == _axis(after) and abs(a.real-b.real)>1e-8 and abs(a.imag-b.imag)>1e-8:
        if axis == 'x':
            middle = (a.real+b.real)/2
            points = [a,complex(middle,a.imag),complex(middle,b.imag),b]
        else:
            middle = (a.imag+b.imag)/2
            points = [a,complex(a.real,middle),complex(b.real,middle),b]
        return [Line(x,y) for x,y in zip(points,points[1:]) if abs(x-y)>1e-8]
    return [Line(a,b)] if abs(a-b)>1e-8 else []


def clean_micro_returns(path):
    """Remove only zero-area backtracks; never silently reshape a contour."""
    from shapely.geometry import Polygon
    poly=Polygon([(s.start.real,s.start.imag) for s in path])
    if poly.is_valid:return path
    cleaned=poly.buffer(0)
    if (cleaned.geom_type!='Polygon' or cleaned.interiors or not cleaned.is_valid
            or abs(cleaned.area-poly.area)>1e-5
            or poly.boundary.hausdorff_distance(cleaned.boundary)>.03):
        raise ValueError('Contour repair exceeds micro-return limit; manual review required')
    points=[complex(x,y) for x,y in cleaned.exterior.coords]
    return SVGPath(*(Line(a,b) for a,b in zip(points,points[1:])))


def remove_source_nicks(data, straighten=True):
    root = ET.fromstring(data)
    elements = [e for e in root.iter() if e.tag.endswith('path')]
    paths = [parse_path(e.get('d')) for e in elements]
    if any(not p.iscontinuous() or any(not isinstance(s, Line) for s in p) for p in paths):
        raise ValueError('This versioned source must contain continuous line paths')
    ends = [(i,k,p.start if k == 0 else p.end) for i,p in enumerate(paths)
            if abs(p.start-p.end)>1e-8 for k in (0,1)]
    candidates = [(i,j,abs(a[2]-b[2])) for i,a in enumerate(ends)
                  for j,b in enumerate(ends) if j>i and abs(a[2]-b[2])<=1.5]
    matrix = np.zeros((len(ends),len(candidates)))
    for k,(i,j,_) in enumerate(candidates): matrix[i,k]=matrix[j,k]=1
    result = milp([d for _,_,d in candidates], integrality=np.ones(len(candidates)),
                  bounds=Bounds(0,1), constraints=LinearConstraint(matrix,1,1))
    if not result.success:
        raise ValueError('Source gaps cannot be paired within 1.5 mm; manual review required')
    links, repairs = {}, []
    for k,(i,j,d) in enumerate(candidates):
        if result.x[k]<.5: continue
        a,b=ends[i],ends[j]
        links[a[:2]]=b[:2];links[b[:2]]=a[:2]
        if d>1e-8: repairs.append({'from':[a[2].real,a[2].imag], 'to':[b[2].real,b[2].imag], 'length_mm':d})
    # Traverse connected source paths. Reversing traversal changes no geometry.
    loops, used = [], set()
    for start,p in enumerate(paths):
        if start in used: continue
        if abs(p.start-p.end)<1e-8:
            loops.append(p);used.add(start);continue
        segments=[];current=(start,0)
        while True:
            idx,side=current
            if idx in used: raise ValueError('Non-cycle source topology')
            used.add(idx);q=paths[idx] if side==0 else paths[idx].reversed()
            segments.extend(q)
            nxt=links[idx,1-side]
            end=paths[nxt[0]].start if nxt[1]==0 else paths[nxt[0]].end
            other=paths[nxt[0]] if nxt[1]==0 else paths[nxt[0]].reversed()
            if abs(q.end-end)>1e-8:
                segments.extend(gap_segments(q.end,end,q[-1],other[0]) if straighten else [Line(q.end,end)])
            if nxt==(start,0): break
            current=nxt
        joined=SVGPath(*segments)
        loops.append(clean_micro_returns(joined) if straighten else joined)
    ns='{http://www.w3.org/2000/svg}'
    output=ET.Element(ns+'svg',dict(root.attrib))
    group=ET.SubElement(output,ns+'g',{'fill':'none','stroke':'#FF0000','stroke-width':'0.15'})
    for i,p in enumerate(loops):
        ET.SubElement(group,ns+'path',{'id':f'source-contour-{i+1}','d':p.d()+' Z','data-operation':'CUT'})
    return ET.tostring(output,encoding='utf-8',xml_declaration=True),repairs


def build():
    original=SOURCE.read_bytes();svg,repairs=remove_source_nicks(original)
    dest=ROOT/'web/demo'
    (dest/f'{MODEL_ID}.svg').write_bytes(svg)
    (dest/f'{MODEL_ID}.source.svg').write_bytes(original)
    (dest/f'{MODEL_ID}.dxf').write_bytes(svg_bytes_to_dxf(svg))
    params={'project':'Ev kalemlik — kullanıcı kaynak SVG', 'thickness':2.7,
            'holding_nicks':False,'surface_texts':[], 'format':'both'}
    (dest/f'{MODEL_ID}.recipe.json').write_text(json.dumps({'svg':svg.decode(),'parameters':params},ensure_ascii=False,indent=2),encoding='utf-8')
    topology=inspect_topology(svg)
    manifest={'id':MODEL_ID,'version':3,'title':'Ev Kalemlik','source_type':'user_supplied_svg',
              'dimensions_mm':{'width':130,'depth':90,'height':180},'dimensions_source':'user filename; not rederived',
              'sheet_mm':[375.02,309.60],'thickness_mm':2.7,'holding_nicks':False,'surface_texts':[],
              'source_sha256':hashlib.sha256(original).hexdigest(),'svg_sha256':hashlib.sha256(svg).hexdigest(),
              'closed_gap_count':len(repairs),'gap_repairs':repairs,'topology':topology,
              'final_status':'NOT VERIFIED','production_export':'BLOCKED','physical_assembly':'NOT VERIFIED',
              'physical_kerf_test':'NOT VERIFIED','assembly':'NOT VERIFIED','assembled_preview_available':False,
              'palette':{'CUT':'#FF0000','ENGRAVE':'#000000'},
              'note':'Kaynak SVG ölçüsü ve geçmeleri korunmuştur. Noç boşlukları kapatıldı; yatay/dikey kenarlardaki bağlantılar dik açılı yapıldı. Sıfır alanlı geri dönüşler en fazla 0,03 mm sınırla temizlendi. Montaj doğrulaması yapılmadı.'}
    (dest/f'{MODEL_ID}.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'gaps_closed':len(repairs),'topology':topology},ensure_ascii=False))

if __name__=='__main__':build()

