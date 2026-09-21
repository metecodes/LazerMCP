"""Normalize generic electronic-enclosure cutouts without product presets."""
from __future__ import annotations
from copy import deepcopy

def _n(row,key,default=0.0):
    value=row.get(key)
    return float(default if value is None or value=="" else value)

def normalize(raw):
    raw=raw if isinstance(raw,dict) else {}
    holes=deepcopy(raw.get("holes") or [])
    slots=deepcopy(raw.get("slots") or raw.get("rect_holes") or [])
    for index,source in enumerate(raw.get("ports") or [],1):
        if not isinstance(source,dict):continue
        port=deepcopy(source);clearance=_n(port,"clearance",_n(port,"clearance_mm",0))
        cw=_n(port,"connector_width",_n(port,"w",_n(port,"width",0)))
        ch=_n(port,"connector_height",_n(port,"h",_n(port,"height",0)))
        pw=_n(port,"plug_width",0);ph=_n(port,"plug_height",0)
        port.update(id=str(port.get("id") or f"port-{index}"),w=max(cw,pw)+2*clearance,h=max(ch,ph)+2*clearance,
                    semantic_role="port_cutout",operation="CUT",clearance_mm=clearance,
                    connector_envelope_mm=[cw,ch],plug_envelope_mm=[pw,ph])
        slots.append(port)
    return {"holes":holes,"slots":slots,"finger_holes":deepcopy(raw.get("finger_holes") or raw.get("fingerHoles") or []),
            "markings":deepcopy(raw.get("markings") or [])}
