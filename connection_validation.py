"""Canonical physical-part inventory and connection coverage gate."""
from __future__ import annotations

ROLES={"structural","removable","moving","hardware_mount","decorative"}

def _role(p):
    role=str(p.get("role") or p.get("assembly_role") or "").lower()
    if role in ROLES:return role,"explicit"
    if p.get("moving"):return "moving","derived:moving"
    semantic=str(p.get("semantic_role") or "").lower()
    if any(x in semantic for x in ("decor","logo","engrave","label")):return "decorative","derived:semantic"
    if any(x in semantic for x in ("mount","holder","bracket")):return "hardware_mount","derived:semantic"
    return "structural","derived:default"

def validate(primitives,parameters,assembly,linear,mechanism=None):
    rows=assembly.get("physical_parts") or [{"id":str(p.get("label") or p.get("id") or f"part-{i+1}"),**p} for i,p in enumerate(primitives or []) if isinstance(p,dict)]
    source={str(p.get("physical_part_id") or p.get("label") or p.get("id") or ""):p for p in primitives or [] if isinstance(p,dict)}
    inventory=[];inventory_ids=[]
    for row in rows:
        pid=str(row.get("id") or row.get("physical_part_id") or row.get("label") or "");role,role_source=_role(source.get(pid,row))
        inventory.append({"id":pid,"role":role,"role_source":role_source,"mates":[]});inventory_ids.append(pid)
    edges=[]
    def add(a,b,kind,status="PASS",evidence=""):
        if a and b and str(a)!=str(b):edges.append({"part_a":str(a),"part_b":str(b),"type":str(kind),"status":str(status),"evidence":evidence})
    for c in assembly.get("derived_constraints") or []:add(c.get("part_a"),c.get("part_b"),c.get("joint_type") or "joint",c.get("result") or "PASS","compiled geometry")
    for c in assembly.get("joints") or []:add(c.get("male"),c.get("female"),c.get("kind") or "finger_joint","PASS" if c.get("result") in {"MATCH","PASS","PLANNED"} else "FAIL",c.get("via") or "")
    slide_rows={str(s.get("id")):s for s in linear.get("slides") or []}
    mechanism_edges=list((mechanism or {}).get("connection_graph") or [])
    verified_pairs={(str(e["part_a"]),str(e["part_b"]),str(e["type"])) for e in edges if e["status"] in {"PASS","MATCH"}}
    verified_pairs|={(b,a,t) for a,b,t in tuple(verified_pairs)}
    for c in parameters.get("connections") or []:
        if not isinstance(c,dict):continue
        typ=str(c.get("type") or "")
        if typ in {"linear_slide","removable_slide"}:
            moving=c.get("moving_part") or c.get("driven_part")
            slide=slide_rows.get(str(c.get("id"))) or {};status=slide.get("status") or "NOT_VERIFIED"
            if typ=="removable_slide" and not (slide.get("removal_verified") and slide.get("reinstall_verified")):status="NOT_VERIFIED"
            for rail in c.get("rails") or []:add(moving,rail,typ,status,"continuous world-space sweep")
        elif typ in {"tab_slot","finger_joint","fixed_lid"}:
            a=str(c.get("part_a") or c.get("male") or "");b=str(c.get("part_b") or c.get("female") or "")
            status="PASS" if (a,b,typ) in verified_pairs or (a,b,"joint") in verified_pairs else "NOT_VERIFIED"
            add(a,b,typ,status,"compiled mate geometry" if status=="PASS" else "metadata is not geometric proof")
        elif typ in {"shaft_hole","shaft_rotation","direct_motor_shaft"}:
            # Hardware edges are accepted only from the canonical geometric validator.
            driven=str(c.get("part") or c.get("driven_part") or "");shaft=str(c.get("shaft") or c.get("motor_part") or "")
            canonical=next((e for e in mechanism_edges if isinstance(e,dict) and str(e.get("part") or "")==driven and str(e.get("shaft") or "")==shaft and e.get("status")=="PASS"),None)
            add(c.get("part") or c.get("driven_part"),"hardware:"+str(c.get("shaft") or c.get("motor_part") or ""),typ,"PASS" if canonical else "NOT_VERIFIED","canonical hardware geometry" if canonical else "connection metadata is not geometric proof")
    lookup={r["id"]:r for r in inventory}
    for edge in edges:
        for key in ("part_a","part_b"):
            if edge[key] in lookup:lookup[edge[key]]["mates"].append(edge)
    expected=len([r for r in inventory if r["role"]!="decorative"])>1;checks=[]
    duplicates=sorted({pid for pid in inventory_ids if not pid or inventory_ids.count(pid)>1})
    if duplicates:checks.append({"status":"FAIL","note":"physical part IDs must be unique and non-empty: "+", ".join(duplicates or ["<empty>"])})
    for item in inventory:
        role,mates=item["role"],item["mates"]
        if not expected or role=="decorative":continue
        if not mates:checks.append({"status":"FAIL","note":f'{item["id"]} role={role} has mates=[]; placement is not connection evidence'})
        elif any(e["status"] not in {"PASS","MATCH"} for e in mates):checks.append({"status":"FAIL","note":f'{item["id"]} has an unverified geometric mate'})
        else:checks.append({"status":"PASS","note":f'{item["id"]} role={role} connection coverage PASS'})
        if role=="moving" and not any(e["type"] in {"linear_slide","removable_slide","shaft_hole","shaft_rotation","direct_motor_shaft"} for e in mates):checks.append({"status":"FAIL","note":f'{item["id"]} moving part has no motion connection'})
        if role=="removable" and not any(e["type"] in {"removable_slide","removable_lid"} and e["status"] in {"PASS","MATCH"} for e in mates):checks.append({"status":"FAIL","note":f'{item["id"]} removable part has no verified remove/reinstall path'})
    covered=sum(1 for r in inventory if r["role"]=="decorative" or not expected or (r["mates"] and all(e["status"] in {"PASS","MATCH"} for e in r["mates"])))
    mate_checks=[{"status":e["status"],"note":f'{e["part_a"]} → {e["part_b"]} {e["type"]}: {e["evidence"]}'} for e in edges]
    if expected and not edges:mate_checks=[{"status":"FAIL","note":"connection graph is empty; placement is not connection evidence"}]
    return {"physical_part_inventory":inventory,"connection_graph":edges,"checks":checks or [{"status":"PASS","note":"single physical part; assembly connection not required"}],"mate_geometry_checks":mate_checks or [{"status":"PASS","note":"single physical part; mate geometry not required"}],"coverage_percent":round(100*covered/max(1,len(inventory)),1),"assembly_expected":expected}
