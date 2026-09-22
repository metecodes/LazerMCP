"""Recover legacy rectangular interlocks from CUT geometry, never from labels.

Only orthogonal, uniquely matching rectangular interfaces are supported. All
coordinates are nominal pre-kerf millimetres. Unsupported/ambiguous geometry
is left unverified; existing explicit joint validators remain authoritative.
"""
from copy import deepcopy
from itertools import combinations
import math

from shapely.geometry import Polygon, box
from shapely.ops import transform
from assembled_view import world


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def sub(a, b):
    return [x-y for x, y in zip(a, b)]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def _frame(p):
    pose = p['placement']
    o, u, v = [list(map(float, pose[k])) for k in ('origin', 'u', 'v')]
    if any(len(a) != 3 or not all(math.isfinite(x) for x in a) for a in (o, u, v)):
        raise ValueError('invalid placement')
    if abs(norm(u)-1) > 1e-5 or abs(norm(v)-1) > 1e-5 or abs(dot(u, v)) > 1e-5:
        raise ValueError('non-orthonormal placement')
    return o, u, v, cross(u, v)


def _rectangle(points):
    poly = Polygon(points)
    if not poly.is_valid or poly.area <= 1e-8:
        return None
    rect = poly.minimum_rotated_rectangle
    return rect if poly.symmetric_difference(rect).area < 1e-7 else None


def contour_candidates(p):
    """Detect three-edge rectangular excursions and real rectangular holes."""
    cut = p.get('_cut_geometry') or {}
    outer = cut.get('outer_cut') or {}
    if outer.get('operation') != 'CUT' or str(p.get('operation', 'CUT')).upper() != 'CUT':
        return [], None
    pts = outer.get('points') or []
    if len(pts) < 3:
        return [], None
    poly = Polygon(pts)
    if not poly.is_valid or poly.area <= 0:
        return [], None
    # Simplify redundant collinear vertices, preserving real steps.
    pts = list(poly.simplify(1e-8, preserve_topology=True).exterior.coords)[:-1]
    candidates = []
    for i in range(len(pts)):
        prev, a, b, c, d, nxt = [pts[(i+j) % len(pts)] for j in (-1, 0, 1, 2, 3, 4)]
        rise, along, fall = sub(b, a), sub(c, b), sub(d, c)
        width, depth = norm(along), norm(rise)
        if min(width, depth) < 1e-6 or norm([x+y for x, y in zip(rise, fall)]) > 1e-6:
            continue
        if abs(dot(rise, along)) > 1e-6:
            continue
        before, after = sub(a, prev), sub(nxt, d)
        parallel = lambda vec: abs(vec[0]*along[1]-vec[1]*along[0]) < 1e-6 and dot(vec, along) > 0
        if not parallel(before) or not parallel(after):
            continue
        rect = Polygon([a, b, c, d])
        occupied = poly.intersection(rect).area
        kind = 'tab' if abs(occupied-rect.area) < 1e-7 else 'recess' if occupied < 1e-7 else None
        if kind:
            candidates.append({'feature': f'contour:{i}', 'kind': kind, 'points': list(rect.exterior.coords)[:-1],
                               'width': width, 'depth': depth, 'direction': [x/depth for x in rise]})
    for i, row in enumerate(cut.get('inner_cuts') or []):
        if row.get('operation') != 'CUT' or not row.get('points'):
            continue
        hole = Polygon(row['points'])
        if not hole.is_valid or not poly.covers(hole):
            continue
        poly = poly.difference(hole)
        rect = _rectangle(row['points'])
        if rect is None:
            continue
        coords = list(rect.exterior.coords)[:-1]
        lengths = [norm(sub(coords[j], coords[(j+1) % 4])) for j in range(4)]
        candidates.append({'feature': f'inner:{i}', 'kind': 'slot', 'points': coords,
                           'width': max(lengths), 'depth': min(lengths), 'direction': None})
    return candidates, poly


def _corners(p, feature, thickness):
    return [world(p, x, y, z) for x, y in feature['points'] for z in (0, thickness)]


def _intervals(poly, p, along, normal, lo, hi):
    """Project material inside the other part's thickness slab onto joint axis."""
    def project(x, y, z=None):
        q = world(p, x, y)
        return dot(q, along), dot(q, normal)
    projected = transform(project, poly)
    bounds = projected.bounds
    clipped = projected.intersection(box(bounds[0]-1, lo+1e-6, bounds[2]+1, hi-1e-6))
    pieces = [clipped] if clipped.geom_type == 'Polygon' else list(getattr(clipped, 'geoms', []))
    return [(s.bounds[0], s.bounds[2]) for s in pieces if s.area > 1e-8]


def orthogonal_collision(a, b, pa, pb, ta, tb):
    """Exact positive-volume test for perpendicular polygon extrusions.

    Inside the intersection of two thickness slabs, material sections are
    independent in the two normal directions. Their joint-axis projections
    overlap iff the solids penetrate. Holes/recesses are subtracted first.
    """
    oa, _, _, na = _frame(a)
    ob, _, _, nb = _frame(b)
    if abs(dot(na, nb)) > 1e-5:
        return None
    along = cross(na, nb)
    ia = _intervals(pa, a, along, nb, dot(ob, nb), dot(ob, nb)+tb)
    ib = _intervals(pb, b, along, na, dot(oa, na), dot(oa, na)+ta)
    return any(min(y, v)-max(x, u) > 1e-6 for x, y in ia for u, v in ib)


def infer_structural_mates(parts, thickness=3, existing_joints=(), tolerance=.05):
    """Return verified evidence plus reciprocal mates, without changing inputs."""
    from connection_validation import _role
    tolerance = min(.05, max(0., float(tolerance)))
    rows, errors, rejected = [], [], []
    for p in parts:
        if _role(p)[0] != 'structural' or p.get('composite_parent'):
            continue
        pid = str(p.get('physical_part_id') or p.get('label') or p.get('id') or '')
        try:
            _frame(p)
            t = float(p.get('thickness', thickness))
            if not math.isfinite(t) or t <= 0:
                raise ValueError('invalid thickness')
            candidates, poly = contour_candidates(p)
            if poly is not None:
                rows.append((pid, p, t, candidates, poly))
        except (KeyError, TypeError, ValueError):
            continue  # Missing/invalid placements are reported by assembly.
    possible = []
    for a, b in combinations(rows, 2):
        aid, ap, at, ac, ag = a
        bid, bp, bt, bc, bg = b
        if aid == bid or abs(dot(_frame(ap)[3], _frame(bp)[3])) > 1e-5:
            continue
        collision = None
        for af in ac:
            for bf in bc:
                if (af['kind'] == 'tab') == (bf['kind'] == 'tab'):
                    continue
                # The entire tab and receiving void must represent the same
                # world-space rectangular prism (not merely equal centres).
                av, bv = _corners(ap, af, at), _corners(bp, bf, bt)
                error = max(max(min(norm(sub(x, y)) for y in bv) for x in av),
                            max(min(norm(sub(y, x)) for x in av) for y in bv))
                if error > tolerance:
                    continue
                terr = max(abs(at-bt), abs(af['depth']-bt), abs(bf['depth']-at))
                if terr > tolerance:
                    rejected.append({'part_a': aid, 'part_b': bid, 'code': 'THICKNESS_MISMATCH', 'thickness_error_mm': terr})
                    continue
                if collision is None:
                    collision = orthogonal_collision(ap, bp, ag, bg, at, bt)
                if collision is not False:
                    rejected.append({'part_a': aid, 'part_b': bid, 'code': 'INTERLOCK_COLLISION'})
                    continue
                possible.append({'part_a': aid, 'part_b': bid, 'feature_a': af['feature'], 'feature_b': bf['feature'],
                                 'type': 'finger_joint', 'source': 'inferred_geometry', 'geometry_source': 'contour_geometry',
                                 'joint_width': max(af['width'], bf['width']), 'joint_depth': af['depth'],
                                 'alignment_error_mm': error, 'thickness_error_mm': terr, 'verified': True,
                                 'world_position': [sum(v[i] for v in av)/len(av) for i in range(3)],
                                 'world_normals': [_frame(ap)[3],_frame(bp)[3]],
                                 'status': 'PASS', 'confidence': 1.0})
    counts = {}
    for c in possible:
        for side in ('a', 'b'):
            key = c['part_'+side], c['feature_'+side]
            counts[key] = counts.get(key, 0)+1
    verified = []
    for c in possible:
        if any(counts[c['part_'+side], c['feature_'+side]] > 1 for side in ('a', 'b')):
            errors.append(f"AMBIGUOUS_STRUCTURAL_MATE: {c['part_a']} ↔ {c['part_b']}")
        else:
            verified.append(c)
    known = {frozenset((c.get('male'), c.get('female'))) for c in existing_joints}
    explicit_by_id={pid:p for pid,p,*_ in rows}
    for pid,p,*_ in rows:
        for mate in p.get('mates') or []:
            if not isinstance(mate,dict):continue
            target=str(mate.get('part') or '')
            if not any(m.get('part')==pid for m in explicit_by_id.get(target,{}).get('mates',[]) if isinstance(m,dict)):
                errors.append(f'NON_RECIPROCAL_EXPLICIT_MATE: {pid} -> {target}')
            if not any({c['part_a'],c['part_b']}=={pid,target} for c in verified) and frozenset((pid,target)) not in known:
                errors.append(f'UNVERIFIED_EXPLICIT_MATE: {pid} -> {target}')
    joints, pairs = [], set()
    reciprocal = {pid: deepcopy(p.get('mates') or []) for pid, p, *_ in rows}
    for c in verified:
        pair = frozenset((c['part_a'], c['part_b']))
        for a, b in ((c['part_a'], c['part_b']), (c['part_b'], c['part_a'])):
            if not any(m.get('part') == b for m in reciprocal[a] if isinstance(m, dict)):
                reciprocal[a].append({'part': b, 'type': c['type'], 'source': 'inferred_geometry', 'verified': True, 'confidence': 1.0})
        if pair in pairs or pair in known:
            continue
        pairs.add(pair)
        joints.append({'male': c['part_a'], 'female': c['part_b'], 'joint_type': 'finger_joint',
                       'result': 'MATCH', 'via': 'verified contour_geometry in assembly space', **c})
    return {'joints': joints, 'inferred_mates': verified, 'reciprocal_mates': reciprocal,
            'errors': sorted(set(errors)), 'rejected_candidates': rejected}
