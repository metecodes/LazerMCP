"""Read-only counterexamples; reports observed behavior, never modifies designs on disk.

Run from repository root: .venv/Scripts/python.exe tools/audit_validation_gaps.py
These are diagnostic probes, not assertions that unsafe behavior is acceptable.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explicit_panel_assembly import compile_connections
from composite_assembly import classify_contacts
from engraving_validation import validate as engraving
from linear_motion import validate as motion
from standalone_validation import classify_assembly_mode
from topology import inspect_topology
from toolbox import render_toolbox
from review import review_built


def run():
    a = dict(type="panel", label="a", w=100, h=100, edges="eeee",
             placement=dict(origin=[0, 0, 0], u=[1, 0, 0], v=[0, 1, 0]))
    b = deepcopy(a)
    b["label"] = "b"
    params = {"connections": [dict(id="C1", type="finger_joint", part_a="a", part_b="b")]}
    review = review_built(render_toolbox([a, b], params))
    outer = '<path d="M0 0H100V100H0Z" stroke="#FF0000" fill="none" data-operation="CUT"/>'
    hole = '<path d="M40 40H60V60H40Z" stroke="#FF0000" fill="none" data-operation="CUT"/>'
    mark = '<path d="M45 50L55 50" stroke="#FFFF00" fill="none" data-operation="ENGRAVE"/>'

    def svg(content):
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
                'viewBox="0 0 100 100">' + content + '</svg>').encode()

    return {
        "coplanar_compiler": compile_connections([a, b], params, 3, .15)[1],
        "coplanar_collision": classify_contacts([a, b], [], 3),
        "coplanar_final_gate": {"final_status": review["final_status"], "categories": {
            k: v for k, v in review["categories"].items()
            if k in {"CONNECTIONS", "ASSEMBLY", "3D_ASSEMBLY", "TAB_SLOT_GEOMETRY"}}},
        "engraving_in_cut_hole": engraving(svg(outer + hole + mark)),
        "duplicate_unnamed_engraving": engraving(svg(outer + mark + mark)),
        "malformed_cut": inspect_topology(svg(
            '<path d="M broken" stroke="#FF0000" data-operation="CUT"/>')),
        "fake_standalone": classify_assembly_mode(
            {"preset": "engraving_layout", "parameters": {"assembly_mode": "standalone"}},
            [{"kind": "panel"}, {"kind": "panel"}], [], False),
        "moving_through_rail": motion([a, b], {"connections": [dict(
            id="S1", type="linear_slide", moving_part="a", rails=["b"],
            axis=[1, 0, 0], travel_mm=10)]}, 3),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=True))
