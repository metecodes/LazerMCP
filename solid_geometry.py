"""Convex-prism SAT and continuous translational insertion checks (nominal mm)."""
import numpy as np
from scipy.spatial import ConvexHull
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon, Point
from assembled_view import outline,world


def part_solid(part,thickness):
    if not np.isfinite(thickness) or thickness<=0:raise ValueError('INVALID_SOLID_THICKNESS')
    poly=Polygon(outline(part))
    if not poly.is_valid or poly.area<=0:raise ValueError('INVALID_SOLID_OUTLINE')
    for h in (part.get('_cut_geometry') or {}).get('inner_cuts') or []:
        if h.get('operation')=='CUT':poly=poly.difference(Polygon(h['points']))
    for h in part.get('holes') or []:
        poly=poly.difference(Point(float(h['x']),float(h['y'])).buffer(float(h.get('d',0))/2,quad_segs=24))
    if poly.is_empty or not poly.is_valid or poly.area<=0:raise ValueError('INVALID_SOLID_OUTLINE')
    tris=constrained_delaunay_triangles(poly)
    result=[]
    for tri in tris.geoms:
        pts=list(tri.exterior.coords)[:3]
        result.append(np.array([world(part,x,y,z) for x,y in pts for z in (0,thickness)],dtype=float))
    return result


def _hull(vertices):
    h=ConvexHull(vertices)
    edges={tuple(sorted((int(a),int(b)))) for face in h.simplices for a,b in zip(face,np.roll(face,1))}
    vec=np.array([vertices[b]-vertices[a] for a,b in edges])
    return h.equations[:,:3],vec


def penetrates(a,b,tolerance=1e-6):
    if np.any(np.minimum(a.max(0),b.max(0))-np.maximum(a.min(0),b.min(0))<=tolerance):return False
    an,ae=_hull(a);bn,be=_hull(b)
    axes=np.concatenate((an,bn,np.cross(ae[:,None,:],be[None,:,:]).reshape(-1,3)))
    sizes=np.linalg.norm(axes,axis=1);axes=axes[sizes>1e-9]/sizes[sizes>1e-9,None]
    aa=a@axes.T;bb=b@axes.T
    return bool(np.all(np.minimum(aa.max(0),bb.max(0))-np.maximum(aa.min(0),bb.min(0))>tolerance))


def collision(moving,obstacle,translation=None):
    for a in moving:
        swept=np.concatenate((a,a+translation)) if translation is not None else a
        for b in obstacle:
            if penetrates(swept,b):return True
    return False


def insertion_check(part,obstacles,direction,thickness,distance=None):
    axis=np.array(direction,dtype=float);size=np.linalg.norm(axis)
    if not np.isfinite(size) or size<1e-9:raise ValueError('MATE_AXIS_MISMATCH')
    axis/=size
    moving=part_solid(part,float(part.get('thickness',thickness)))
    vertices=np.concatenate(moving)
    # Enough travel to begin wholly outside every installed object's projection.
    needed=max([float((vertices@axis).max()-(np.concatenate(solid)@axis).min()+thickness)
                for _,solid in obstacles]+[thickness])
    distance=needed if distance is None else float(distance)
    if not np.isfinite(distance) or distance<needed-1e-6:raise ValueError('INSERTION_TRAVEL_TOO_SHORT')
    delta=-axis*distance
    hits=[pid for pid,solid in obstacles if collision(moving,solid,delta)]
    return {'status':'FAIL' if hits else 'PASS','code':'INSERTION_PATH_COLLISION' if hits else None,
            'obstacles':hits,'direction':axis.tolist(),'travel_mm':distance,'method':'continuous convex-prism swept-volume SAT'}
