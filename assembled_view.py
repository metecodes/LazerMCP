"""Explicit panel placements, tab partners and a nominal assembled SVG preview."""
from __future__ import annotations
import math
from xml.sax.saxutils import quoteattr, escape
from shapely.geometry import Polygon, box


def outline(p):
    cut=p.get('_cut_geometry') if isinstance(p.get('_cut_geometry'),dict) else {}
    outer=cut.get('outer_cut') if isinstance(cut.get('outer_cut'),dict) else {}
    pts = outer.get('points') or p.get('points') or p.get('vertices') or p.get('coords') or p.get('contour')
    if pts:
        return [(float(x), float(y)) for x,y in pts]
    kind=str(p.get('type') or p.get('kind') or '').lower()
    if kind in {'propeller','pervane','blades','fan'}:
        from toolbox import propeller_points
        return propeller_points(int(p.get('blades') or 4),float(p.get('d') or p.get('diameter') or 80),float(p.get('blade_w') or p.get('blade_width') or 12))
    if kind in {'disc','disk','circle'}:
        r=float(p.get('d') or p.get('diameter') or 0)/2
        if r:return [(r*math.cos(i*math.pi/24),r*math.sin(i*math.pi/24)) for i in range(48)]
    w,h = float(p.get('w') or 0),float(p.get('h') or 0)
    return [(0,0),(w,0),(w,h),(0,h)] if w and h else []


def world(p,x,y,z=0):
    pose=p['placement']; o=pose['origin']; u=pose['u']; v=pose['v']
    n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
    return [o[i]+x*u[i]+y*v[i]+z*n[i] for i in range(3)]


def _tab_on_outer_cut(poly, tab_box, w, h, tolerance=.02):
    """A tab is evidence only when its rectangle is part of the outer CUT boundary."""
    if not poly.buffer(tolerance).covers(tab_box):
        return False
    shared = poly.boundary.buffer(tolerance).intersection(tab_box.boundary).length
    return shared >= max(min(abs(w), abs(h)) * .8, tolerance * 2)


def validate(parts,t):
    errors=[]; joints=[];debug=[]
    lookup={p.get('label'):p for p in parts if isinstance(p,dict)}
    if len(lookup)!=len(parts):
        errors.append('assembly panel labels must be unique')
    for p in lookup.values():
        pose=p.get('placement')
        if pose:
            try:
                o,u,v=[pose[k] for k in ('origin','u','v')]
                if any(len(a)!=3 or any(not math.isfinite(float(b)) for b in a) for a in (o,u,v)) or any(abs(sum(float(b)**2 for b in a)-1)>.0001 for a in (u,v)) or abs(sum(float(a)*float(b) for a,b in zip(u,v)))>.0001:
                    raise ValueError()
            except (KeyError,TypeError,ValueError):
                errors.append(f"invalid orthonormal placement on {p.get('label')}")
    if errors: return errors,joints,debug
    for p in lookup.values():
        pts=outline(p)
        if not pts: continue
        poly=Polygon(pts)
        if not poly.is_valid or poly.area<=0:
            errors.append(f"invalid outline on {p.get('label')}"); continue
        from shapely.geometry import Point
        for hole in p.get('holes') or []:
            if not poly.contains(Point(float(hole['x']),float(hole['y'])).buffer(float(hole.get('d',0))/2)):
                errors.append(f"hole on {p.get('label')} leaves its actual outline")
        for s in p.get('slots') or []:
            rec={'connection':f'C{len(debug)+1:02d}','tab_part':None,'tab_id':None,'slot_part':p.get('label'),'result':'FAIL'}
            x,y,w,h=[float(s.get(k) or 0) for k in ('x','y','w','h')]
            rec['slot_local_bbox']=[x-w/2,y-h/2,x+w/2,y+h/2]
            if w<=0 or h<=0 or not poly.contains(box(x-w/2,y-h/2,x+w/2,y+h/2)):
                rec['reason']='slot leaves its actual outline';debug.append(rec);errors.append(f"slot on {p.get('label')} leaves its actual outline");continue
            edge_clearance=float(s.get('edge_clearance_mm') or 1.0)
            if box(x-w/2,y-h/2,x+w/2,y+h/2).distance(poly.boundary)<edge_clearance:
                rec['reason']=f'slot edge clearance is below {edge_clearance:g} mm';debug.append(rec);errors.append(f"slot on {p.get('label')} violates minimum edge clearance {edge_clearance:g} mm");continue
            actual=(p.get('_cut_geometry') or {}).get('inner_cuts') or []
            if not any(row.get('role')=='SLOT' and row.get('operation')=='CUT' and row.get('points')==[[x-w/2,y-h/2],[x+w/2,y-h/2],[x+w/2,y+h/2],[x-w/2,y+h/2]] for row in actual if isinstance(row,dict)):
                rec['reason']='slot is metadata only; no closed INNER_CUT geometry';debug.append(rec);errors.append(f"slot on {p.get('label')} is missing from actual INNER_CUT geometry");continue
            if min(w,h)>t+.6: continue
            mate=s.get('mate') or {}; other=lookup.get(mate.get('part'))
            tab=next((a for a in (other or {}).get('tabs',[]) if a.get('id')==mate.get('tab')),None)
            rec.update({'tab_part':mate.get('part'),'tab_id':mate.get('tab')})
            if not tab:
                rec['reason']='no explicit matching tab';debug.append(rec);errors.append(f"slot on {p.get('label')} has no explicit matching tab"); continue
            tx,ty,tw,th=[float(tab.get(k) or 0) for k in ('x','y','w','h')]
            rec['tab_local_bbox']=[tx-tw/2,ty-th/2,tx+tw/2,ty+th/2]
            op=Polygon(outline(other)); tab_box=box(tx-tw/2,ty-th/2,tx+tw/2,ty+th/2)
            compiled_tab=next((row for row in (other.get('_cut_geometry') or {}).get('tabs') or [] if str(row.get('id') or '')==str(mate.get('tab') or '')),None)
            if str(other.get('operation') or 'CUT').upper() != 'CUT' or not compiled_tab or not compiled_tab.get('materialized') or not op.is_valid or not _tab_on_outer_cut(op,tab_box,tw,th):
                rec['reason']='tab is metadata only; missing from actual outer CUT geometry';debug.append(rec);errors.append(f"tab {mate.get('tab')} is metadata only; it is missing from {mate.get('part')} actual outer CUT geometry"); continue
            if not p.get('placement') or not other.get('placement'):
                rec['reason']='explicit assembled placements required';debug.append(rec);errors.append(f"tab-slot {p.get('label')} needs explicit assembled placements"); continue
            try:
                corners=[world(other,a,b,c) for a in (tx-tw/2,tx+tw/2) for b in (ty-th/2,ty+th/2) for c in (0,t)]
                pose=p['placement']; local=[[sum((a[i]-pose['origin'][i])*pose[k][i] for i in range(3)) for k in ('u','v')] for a in corners]
                bounds=[min(a[0] for a in local),min(a[1] for a in local),max(a[0] for a in local),max(a[1] for a in local)]
                expected=[x-w/2,y-h/2,x+w/2,y+h/2]
                origin=world(p,0,0); u=pose['u']; v=pose['v']; n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                other_pose=other['placement']; other_n=[other_pose['u'][1]*other_pose['v'][2]-other_pose['u'][2]*other_pose['v'][1],other_pose['u'][2]*other_pose['v'][0]-other_pose['u'][0]*other_pose['v'][2],other_pose['u'][0]*other_pose['v'][1]-other_pose['u'][1]*other_pose['v'][0]]
                depths=[sum((a[i]-origin[i])*n[i] for i in range(3)) for a in corners]
                fit=float(s.get('fit_tolerance_mm') or .15)
                centers=[(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2]; expected_centers=[x,y]
                sizes=[bounds[2]-bounds[0],bounds[3]-bounds[1]]; expected_sizes=[w,h]
                perpendicular=abs(sum(float(a)*float(b) for a,b in zip(n,other_n))) <= .001
                fitted=all(abs(a-b)<=fit for a,b in zip(centers,expected_centers)) and all(-.05 <= slot-tab <= fit for slot,tab in zip(expected_sizes,sizes))
                world_tab=[world(other,a,b,0) for a in (tx-tw/2,tx+tw/2) for b in (ty-th/2,ty+th/2)]
                world_slot=[world(p,a,b,0) for a in (x-w/2,x+w/2) for b in (y-h/2,y+h/2)]
                bbox=lambda pts:[min(q[i] for q in pts) for i in range(3)]+[max(q[i] for q in pts) for i in range(3)]
                angular=math.degrees(math.asin(min(1,abs(sum(float(a)*float(b) for a,b in zip(n,other_n))))))
                rec.update({'tab_world_bbox':bbox(world_tab),'slot_world_bbox':bbox(world_slot),'center_distance_mm':math.hypot(centers[0]-x,centers[1]-y),'angular_error_deg':angular,'thickness_clearance_mm':min(expected_sizes[i]-sizes[i] for i in range(2)),'insertion_depth_mm':max(depths)-min(depths)})
                if not perpendicular or not fitted or min(depths)>.05 or max(depths)<t-.05:
                    rec['reason']='orientation, position, thickness clearance or insertion depth mismatch';debug.append(rec);errors.append(f"tab {mate.get('part')}.{mate.get('tab')} does not align with {p.get('label')} slot"); continue
                rec.update({'result':'PASS','reason':'actual CUT polygons align after shared 3D transform'});debug.append(rec)
                joints.append({'male':mate['part'],'female':p['label'],'kind':'tab-slot','result':'MATCH','via':'actual outer CUT tab geometry transformed into the receiving panel 3D frame'})
            except (KeyError,TypeError,ValueError):
                rec['reason']='invalid placement transform';debug.append(rec);errors.append(f"invalid placement on {p.get('label')}")
    for p in lookup.values():
        attachment=p.get('attachment') or {}
        if not attachment: continue
        other=lookup.get(attachment.get('to'))
        if attachment.get('kind')!='glue' or not other or not p.get('placement') or not other.get('placement'):
            errors.append(f"unsupported attachment on {p.get('label')}"); continue
        pose=other['placement']; u,v=pose['u'],pose['v']; n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        local=[]; depths=[]
        for x,y in outline(p):
            a=world(p,x,y); diff=[a[i]-pose['origin'][i] for i in range(3)]
            local.append([sum(diff[i]*pose[k][i] for i in range(3)) for k in ('u','v')]); depths.append(sum(diff[i]*n[i] for i in range(3)))
        target=Polygon(outline(other))
        for s in other.get('slots') or []:
            x,y,w,h=[float(s[k]) for k in ('x','y','w','h')];target=target.difference(box(x-w/2,y-h/2,x+w/2,y+h/2))
        if not target.covers(Polygon(local)) or any(abs(a-t)>.05 for a in depths):
            errors.append(f"glued ornament {p.get('label')} does not contact {other['label']}")
        else:
            joints.append({'male':p['label'],'female':other['label'],'kind':'glue','result':'PLANNED','via':'nominal adhesive contact; physical glue test not verified'})
    return errors,joints,debug


def preview(parts,t=3,visible_labels=None,highlight_labels=None,caption=None):
    panels=[p for p in parts if isinstance(p,dict) and outline(p) and p.get('placement')]
    if not panels or len(panels)!=len(parts): return None
    visible=set(visible_labels or [p.get('label') for p in panels])
    highlight=set(highlight_labels or [])
    def project(a): return (a[0]+.45*a[1],-a[2]-.24*a[1])
    allpts=[project(world(p,x,y,z)) for p in panels for x,y in outline(p) for z in (0,t)]
    xs,ys=zip(*allpts); lo,hi=min(xs)-20,min(ys)-20; w,h=max(xs)-lo+20,max(ys)-hi+20
    def path(p,pts,z=0):
        return 'M'+' L'.join(f'{a:.3f},{b:.3f}' for a,b in [project(world(p,x,y,z)) for x,y in pts])+' Z'
    chunks=[]
    for p in sorted((p for p in panels if p.get('label') in visible),key=lambda p:sum(world(p,x,y)[1] for x,y in outline(p))/len(outline(p)),reverse=True):
        pts=outline(p)
        active=p.get('label') in highlight
        face_fill='#f2a65a' if active else '#c6a274'; edge_fill='#c8792c' if active else '#9c754b'; stroke='#9a4f0b' if active else '#775b3e'
        for a,b in zip(pts,pts[1:]+pts[:1]):
            ring=[project(world(p,*a)),project(world(p,*b)),project(world(p,*b,t)),project(world(p,*a,t))]
            chunks.append('<polygon points="'+' '.join(f'{x:.3f},{y:.3f}' for x,y in ring)+f'" fill="{edge_fill}" stroke="{stroke}" stroke-width=".25"/>')
        d=path(p,pts)
        for s in p.get('slots') or []:
            x,y,sw,sh=[float(s[k]) for k in ('x','y','w','h')]
            d+=' '+path(p,[(x-sw/2,y-sh/2),(x+sw/2,y-sh/2),(x+sw/2,y+sh/2),(x-sw/2,y+sh/2)])
        for hole in p.get('holes') or []:
            x,y,r=float(hole['x']),float(hole['y']),float(hole.get('d',0))/2
            d+=' '+path(p,[(x+r*math.cos(i*math.pi/24),y+r*math.sin(i*math.pi/24)) for i in range(48)])
        chunks.append(f'<path data-panel={quoteattr(p["label"])} d="{d}" fill="{face_fill}" fill-rule="evenodd" stroke="{stroke}" stroke-width=".4"/>')
        for mark in p.get('markings') or []:
            if mark.get('icon')=='star':
                x,y,r=float(mark['x']),float(mark['y']),float(mark.get('width',24))/2
                star=[(x+r*(1 if i%2==0 else .45)*math.cos(math.pi/2+i*math.pi/5),y+r*(1 if i%2==0 else .45)*math.sin(math.pi/2+i*math.pi/5)) for i in range(10)]
                chunks.append(f'<path d="{path(p,star)}" fill="none" stroke="#775b3e" stroke-width=".7"/>')
    title=str(caption or 'Nominal assembled panel preview')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{lo} {hi} {w} {h}" role="img" aria-label={quoteattr(title)}><title>{escape(title)}</title><rect x="{lo}" y="{hi}" width="{w}" height="{h}" fill="#f6f3ed"/>'+''.join(chunks)+'</svg>'
