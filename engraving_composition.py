"""Product-neutral engraving composition for cards, boards and learning wheels."""
from __future__ import annotations
import math
from copy import deepcopy
from shapely.geometry import Point, box
from shapely.ops import unary_union

def _n(value,default=0.0):return float(default if value is None or value=="" else value)
def _size(part):
    kind=str(part.get("type") or part.get("kind") or "").lower()
    if kind in {"disc","disk","circle","washer","spacer"}:
        d=_n(part.get("d") or part.get("diameter") or part.get("w"),40);return d,d
    return _n(part.get("w") or part.get("x") or part.get("width"),0),_n(part.get("h") or part.get("y") or part.get("height"),0)
def _safe_area(part,margin,clearance):
    w,h=_size(part);kind=str(part.get("type") or "").lower()
    safe=Point(w/2,h/2).buffer(max(0,min(w,h)/2-margin),resolution=96) if kind in {"disc","disk","circle","washer","spacer"} else box(margin,margin,w-margin,h-margin)
    obstacles=[]
    for hole in part.get("holes") or []:
        x=_n(hole.get("x") or hole.get("cx"));y=_n(hole.get("y") or hole.get("cy"));d=_n(hole.get("d") or hole.get("diameter"),2*_n(hole.get("r") or hole.get("radius")))
        if d>0:obstacles.append(Point(x,y).buffer(d/2+clearance,resolution=32))
    center_hole=_n(part.get("hole") or part.get("d_hole"))
    if center_hole>0:obstacles.append(Point(w/2,h/2).buffer(center_hole/2+clearance,resolution=32))
    for slot in part.get("slots") or part.get("rect_holes") or []:
        x=_n(slot.get("x") or slot.get("cx"));y=_n(slot.get("y") or slot.get("cy"));sw=_n(slot.get("w") or slot.get("width") or slot.get("dx"));sh=_n(slot.get("h") or slot.get("height") or slot.get("dy"))
        if sw>0 and sh>0:obstacles.append(box(x-sw/2-clearance,y-sh/2-clearance,x+sw/2+clearance,y+sh/2+clearance))
    return safe.difference(unary_union(obstacles)) if obstacles else safe
def _engrave(mark):
    row=deepcopy(mark);op=str(row.get("operation") or "engrave").lower()
    if op not in {"engrave","etch"}:raise ValueError("engraving_composition items must use ENGRAVE, never CUT")
    row["operation"]="engrave";row.setdefault("semantic_role","illustration" if str(row.get("kind")) in {"image","path"} else "text");return row
def _image_caption(block,x0,y0,x1,y1,padding):
    if not isinstance(block,dict):raise ValueError("image_caption block must be an object")
    illustration=block.get("illustration") or block.get("image") or block.get("graphic");caption=block.get("caption") or block.get("label") or block.get("text")
    if not isinstance(illustration,dict) or not str(caption or "").strip():raise ValueError("image_caption requires illustration and caption")
    w=x1-x0;h=y1-y0;caption_h=max(3,min(h*.22,_n(block.get("caption_height"),h*.16)))
    art=_engrave(illustration);art.update(x=(x0+x1)/2,y=y0+caption_h+(h-caption_h)/2,width=max(1,w-2*padding),height=max(1,h-caption_h-2*padding),align="center")
    text=_engrave({"kind":"text","value":str(caption),"x":(x0+x1)/2,"y":y0+caption_h/2,"width":max(1,w-2*padding),"height":caption_h*.72,"align":"center"})
    return [art,text]
def compose(part):
    cfg=part.get("engraving_composition")
    if not isinstance(cfg,dict):return part,None
    w,h=_size(part)
    if min(w,h)<=0:raise ValueError("engraving_composition requires physical part width and height")
    margin=max(1,_n(cfg.get("safe_margin_mm"),3));clearance=max(0,_n(cfg.get("mechanical_clearance_mm"),1));gap=max(0,_n(cfg.get("gap_mm"),2));layout=str(cfg.get("layout") or "grid").lower();items=cfg.get("items") or cfg.get("blocks") or []
    if not isinstance(items,list) or not items:raise ValueError("engraving_composition requires items")
    safe=_safe_area(part,margin,clearance)
    if safe.is_empty:raise ValueError("no engraving-safe area remains after margins and cut features")
    marks=[]
    if layout=="radial":
        if str(part.get("type") or "").lower() not in {"disc","disk","circle","washer","spacer"}:raise ValueError("radial engraving layout requires a disc part")
        radius=_n(cfg.get("radius_mm"),min(w,h)*.31);item_size=_n(cfg.get("item_size_mm"),min(w,h)*.16);start=_n(cfg.get("start_angle_deg"),90)
        for i,item in enumerate(items):
            angle=math.radians(start-360*i/len(items));x=w/2+radius*math.cos(angle);y=h/2+radius*math.sin(angle);row=_engrave(item if isinstance(item,dict) else {"kind":"text","value":str(item)});row.update(x=x,y=y,width=_n(row.get("width"),item_size),height=_n(row.get("height"),item_size),align="center");marks.append(row)
    else:
        columns=max(1,int(cfg.get("columns") or (1 if layout=="image_caption" else math.ceil(math.sqrt(len(items))))));rows=math.ceil(len(items)/columns);x0,y0,x1,y1=safe.bounds;cw=(x1-x0-gap*(columns-1))/columns;ch=(y1-y0-gap*(rows-1))/rows
        if min(cw,ch)<=2:raise ValueError("engraving items do not fit the requested grid")
        for i,item in enumerate(items):
            col=i%columns;row=i//columns;ax=x0+col*(cw+gap);ay=y1-(row+1)*ch-row*gap
            if layout=="image_caption":marks.extend(_image_caption(item,ax,ay,ax+cw,ay+ch,max(1,gap/2)))
            else:
                mark=_engrave(item if isinstance(item,dict) else {"kind":"text","value":str(item)});mark.update(x=ax+cw/2,y=ay+ch/2,width=_n(mark.get("width"),cw-2),height=_n(mark.get("height"),ch-2),align="center");marks.append(mark)
    from markings import marking_geom
    checks=[]
    for mark in marks:
        geom=marking_geom(mark);ok=geom is not None and not geom.is_empty and safe.buffer(1e-6).covers(geom);checks.append({"status":"PASS" if ok else "FAIL","kind":str(mark.get("kind") or "text"),"bounds":list(geom.bounds) if geom is not None and not geom.is_empty else []})
        if not ok:raise ValueError("engraving item leaves the safe area or overlaps a mechanical cutout")
    out=deepcopy(part);out.setdefault("markings",[]).extend(marks);out["_engraving_composition"]={"status":"PASS","layout":layout,"safe_margin_mm":margin,"mechanical_clearance_mm":clearance,"item_count":len(marks),"safe_bounds":list(safe.bounds),"checks":checks};return out,out["_engraving_composition"]
def prepare(parts):
    out=[];reports=[]
    for part in parts:
        row,report=compose(part);out.append(row)
        if report:reports.append({"part":str(row.get("label") or row.get("id") or row.get("type")),**report})
    return out,reports
