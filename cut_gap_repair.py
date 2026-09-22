"""Conservative CUT gap repair in millimetres; ambiguous joins fail closed."""
import json
import math
from xml.etree import ElementTree as ET
from svgpathtools import Path as SVGPath, Line, parse_path

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

def repair_cut_gaps(svg_bytes, explicit=False, max_gap_mm=1.5):
    """Repair tagged holding bridges or explicitly requested imported CUT gaps.

    Distinct parents/styles/part metadata never share endpoint pools. Every
    endpoint must have exactly one candidate; no nearest-neighbour guess.
    Curved open cuts and non-mm/transformed inputs require caller normalization.
    """
    from manufacturing import classify_element
    root=ET.fromstring(svg_bytes)
    parents={c:p for p in root.iter() for c in p}
    groups={}
    for el in root.iter():
        if not el.tag.endswith('path') or classify_element(el,parents)[0]!='CUT':continue
        tagged=bool(el.get('data-holding-nicks') or el.get('data-holding-bridges'))
        if not explicit and not tagged:continue
        path=parse_path(el.get('d') or '')
        subs=path.continuous_subpaths() if path else []
        if all(p.isclosed() for p in subs):continue
        # Repair distances must not be interpreted in px or transformed units.
        vb=[float(x) for x in root.get('viewBox','').replace(',',' ').split()]
        if len(vb)!=4 or not root.get('width','').endswith('mm') or not root.get('height','').endswith('mm'):
            raise ValueError('CUT_REPAIR_UNITS: normalize to millimetre viewBox first')
        if any(abs(float(root.get(k)[:-2])-vb[i])>1e-6 for k,i in [('width',2),('height',3)]):
            raise ValueError('CUT_REPAIR_UNITS: scaled viewBox is unsupported')
        node=el
        while node is not None:
            if node.get('transform'):
                from svgpathtools.parser import parse_transform
                matrix=parse_transform(node.get('transform'))
                # Translation, rotation and reflection preserve mm distances.
                if any(abs(sum(matrix[k,i]*matrix[k,j] for k in range(2))-(1 if i==j else 0))>1e-8 for i in range(2) for j in range(2)):
                    raise ValueError('CUT_REPAIR_TRANSFORM: flatten scaled/skewed transforms first')
            node=parents.get(node)
        if any(not isinstance(seg,Line) for p in subs if not p.isclosed() for seg in p):
            raise ValueError('CUT_REPAIR_CURVE: open curved cuts need explicit reconstruction')
        attrs=tuple(sorted((k,v) for k,v in el.attrib.items() if k not in {'d','data-holding-nicks','data-holding-bridges'}))
        key=(parents.get(el),attrs, id(el) if tagged else None)
        groups.setdefault(key,[]).append((el,subs))
    if not groups:return svg_bytes
    if not math.isfinite(max_gap_mm) or not 0<max_gap_mm<=1.5:
        raise ValueError('CUT_REPAIR_TOLERANCE: must be >0 and <=1.5 mm')
    repairs=[]
    for (parent,_,_),entries in groups.items():
        paths=[p for _,subs in entries for p in subs]
        ends={(i,k):p.start if k==0 else p.end for i,p in enumerate(paths) if not p.isclosed() for k in (0,1)}
        links={}
        for key,pt in ends.items():
            hits=[q for q,v in ends.items() if q!=key and abs(pt-v)<=max_gap_mm]
            if len(hits)!=1:
                raise ValueError('CUT_REPAIR_AMBIGUOUS' if hits else 'CUT_REPAIR_UNMATCHED_ENDPOINT')
            links[key]=hits[0]
        used=set();loops=[]
        for i,p in enumerate(paths):
            if i in used:continue
            if p.isclosed():loops.append(p);used.add(i);continue
            current=(i,0);segments=[]
            while True:
                idx,side=current
                if idx in used:raise ValueError('CUT_REPAIR_NON_CYCLE')
                used.add(idx);q=paths[idx] if side==0 else paths[idx].reversed()
                segments.extend(q)
                nxt=links[idx,1-side];other=paths[nxt[0]] if nxt[1]==0 else paths[nxt[0]].reversed()
                bridge=gap_segments(q.end,other.start,q[-1],other[0]);segments.extend(bridge)
                repairs.append({'gap_mm':abs(q.end-other.start),'square_join':len(bridge)>1})
                if nxt==(i,0):break
                current=nxt
            loops.append(clean_micro_returns(SVGPath(*segments)))
        el=entries[0][0]
        el.set('d',' '.join(p.d()+' Z' for p in loops))
        for attr in ('data-holding-nicks','data-holding-bridges'):el.attrib.pop(attr,None)
        for old,_ in entries[1:]:parent.remove(old)
    from topology import inspect_topology
    result=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    report=inspect_topology(result)
    if not report['ok']:raise ValueError('CUT_REPAIR_TOPOLOGY_FAILED: '+json.dumps(report))
    root.set('data-cut-gap-repair',json.dumps({'closed_gaps':len(repairs),'square_joins':sum(r['square_join'] for r in repairs)}))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


