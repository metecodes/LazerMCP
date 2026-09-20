"""Opt-in user text and brand engraving placement on real product faces."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from shapely.geometry import Polygon, box


ELIGIBLE = {"panel", "wall", "rect", "roof", "roof_panel", "contour", "outline", "polygon"}


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or "").strip().lower()


def _bounds(part: dict[str, Any]):
    pts = part.get("points") or part.get("vertices") or part.get("contour")
    if isinstance(pts, list) and len(pts) >= 3:
        try:
            poly = Polygon([(float(p[0]), float(p[1])) for p in pts])
            if poly.is_valid and poly.area > 0:
                return poly.bounds, poly
        except (TypeError, ValueError, IndexError):
            pass
    w = float(part.get("w") or part.get("width") or part.get("x") or 0)
    h = float(part.get("h") or part.get("height") or part.get("y") or 0)
    return ((0.0, 0.0, w, h), box(0, 0, w, h)) if w > 0 and h > 0 else (None, None)


def _keepouts(part: dict[str, Any]):
    out = []
    for row in [*(part.get("holes") or []), *(part.get("slots") or part.get("rect_holes") or [])]:
        if not isinstance(row, dict):
            continue
        x, y = float(row.get("x") or row.get("cx") or 0), float(row.get("y") or row.get("cy") or 0)
        if row.get("d") or row.get("diameter"):
            r = float(row.get("d") or row.get("diameter")) / 2 + 2
            out.append(box(x-r, y-r, x+r, y+r))
        else:
            w, h = float(row.get("w") or row.get("width") or 0)+4, float(row.get("h") or row.get("height") or 0)+4
            out.append(box(x-w/2, y-h/2, x+w/2, y+h/2))
    for row in part.get("markings") or []:
        if isinstance(row,dict) and isinstance(row.get("_branding_box"),list):
            out.append(box(*row["_branding_box"]))
    return out


def _spot(part: dict[str, Any], height: float, width: float):
    bounds, poly = _bounds(part)
    if not bounds:
        return None
    minx, miny, maxx, maxy = bounds
    margin = max(3.0, min(maxx-minx, maxy-miny)*.06)
    usable = poly.buffer(-margin)
    if usable.is_empty:
        return None
    width = min(width, max(0.0, maxx-minx-2*margin))
    if width < 8 or height < 2 or height > maxy-miny-2*margin:
        return None
    candidates = [(0.72,"upper"),(0.50,"center"),(0.28,"lower")]
    for ratio, name in candidates:
        x, y = (minx+maxx)/2, miny+(maxy-miny)*ratio
        area = box(x-width/2, y-height/2, x+width/2, y+height/2)
        if usable.covers(area) and not any(area.intersects(k) for k in _keepouts(part)):
            return {"x":x,"y":y,"width":width,"height":height,"zone":name}
    return None


def _mark(kind: str, value: Any, spot: dict[str, Any], source: str):
    row={"kind":kind,"x":spot["x"],"y":spot["y"],"width":spot["width"],"height":spot["height"],"align":"center","operation":"ENGRAVE","semantic_role":"logo" if kind=="path" else "text","_branding_generated":True,"source":source}
    if kind == "text": row["value"] = str(value)
    else: row["d"] = str(value)
    row["_branding_box"]=[spot["x"]-spot["width"]/2,spot["y"]-spot["height"]/2,spot["x"]+spot["width"]/2,spot["y"]+spot["height"]/2]
    return row


def apply_surface_content(parts: list[dict[str, Any]], parameters: dict[str, Any]):
    """Apply only explicit user content; branding is repeated only when opted in."""
    result=deepcopy(parts);report={"enabled":False,"requested":[],"placements":[],"skipped":[]}
    for part in result:
        part["markings"]=[m for m in part.get("markings") or [] if not (isinstance(m,dict) and m.get("_branding_generated"))]
    texts=parameters.get("surface_texts") or parameters.get("product_texts") or []
    if isinstance(texts,str): texts=[line.strip() for line in texts.splitlines() if line.strip()]
    normalized=[]
    for raw in texts:
        item={"text":raw} if isinstance(raw,str) else dict(raw) if isinstance(raw,dict) else {}
        if str(item.get("text") or item.get("value") or "").strip(): normalized.append(item)
    brand=parameters.get("branding") if isinstance(parameters.get("branding"),dict) else {}
    enabled=bool(parameters.get("apply_branding") or parameters.get("brand_on_product") or brand.get("enabled"))
    name=str(brand.get("name") or parameters.get("brand_name") or "").strip()
    logo=brand.get("logo_path") or brand.get("logo") or parameters.get("brand_logo_path")
    report["enabled"]=enabled;report["requested"]=[str(x.get("text") or x.get("value")) for x in normalized]
    eligible=[p for p in result if _kind(p) in ELIGIBLE]
    for part in result:
        if _kind(part)!="box": continue
        walls=part.setdefault("walls",{})
        x,y,h=float(part.get("x") or part.get("w") or 0),float(part.get("y") or part.get("d") or 0),float(part.get("h") or 0)
        for face,w,fh in (("front",x,h),("back",x,h),("left",y,h),("right",y,h),("top",x,y)):
            if w<=0 or fh<=0 or (face=="top" and not part.get("lid")): continue
            host=walls.setdefault(face,{})
            host.update({"type":"wall","label":f"{part.get('label') or 'box'}.{face}","w":w,"h":fh})
            eligible.append(host)

    def place(part, kind, value, source, preferred_h):
        bounds,_=_bounds(part); span=(bounds[2]-bounds[0]) if bounds else 0
        if kind == "text":
            natural=max(8.0,len(str(value))*preferred_h*.62)
            target_width=min(natural,max(8.0,span*.64),120.0)
            effective_h=preferred_h*min(1.0,target_width/natural)
        else:
            target_width=min(max(18.0,span*.38),60.0);effective_h=preferred_h
        spot=_spot(part,effective_h,target_width)
        label=str(part.get("label") or part.get("type") or "part")
        if not spot:
            report["skipped"].append({"part":label,"content":str(value)[:80],"reason":"NO_SAFE_AREA"});return False
        part.setdefault("markings",[]).append(_mark(kind,value,spot,source))
        report["placements"].append({"part":label,"content":str(value)[:80],"kind":"logo" if kind=="path" else "text","operation":"ENGRAVE","color":"#FFFF00","x_mm":round(spot["x"],2),"y_mm":round(spot["y"],2),"width_mm":round(spot["width"],2),"height_mm":round(spot["height"],2),"zone":spot["zone"]});return True

    for item in normalized:
        target=str(item.get("target_part") or item.get("part") or "").strip().lower()
        hosts=[p for p in eligible if target and target in {str(p.get("label") or "").lower(),_kind(p)}] if target else eligible[:1]
        if not hosts: report["skipped"].append({"part":target or None,"content":str(item.get("text") or item.get("value")),"reason":"TARGET_NOT_FOUND"})
        for host in hosts: place(host,"text",item.get("text") or item.get("value"),"user_surface_text",float(item.get("height_mm") or item.get("height") or 6))
    if enabled and (name or logo):
        for host in eligible:
            if logo: place(host,"path",logo,"user_brand_logo",8)
            if name: place(host,"text",name,"user_brand_name",5)
    elif enabled:
        report["skipped"].append({"part":None,"content":"branding","reason":"BRAND_CONTENT_MISSING"})
    return result,report
