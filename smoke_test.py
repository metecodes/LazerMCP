"""Prove: Boxes.py import → generator → SVG → output/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import boxes_adapter as boxespy


def main() -> int:
    print("== Boxes.py import ==")
    print(f"boxes module: {boxespy.boxes.__file__}")
    print(f"BOXES_PATH: {boxespy.BOXES_PATH}")

    print("\n== list_generators ==")
    listing = boxespy.list_generators()
    print(f"count: {listing['count']}")
    names = {item["name"] for item in listing["generators"]}
    print(f"has ABox: {'ABox' in names}")
    print(f"aliases: {listing['aliases']}")

    print("\n== get_generator_schema(SimpleBox) ==")
    schema = boxespy.get_generator_schema("SimpleBox")
    print(f"resolved: {schema['resolved_name']}")
    print(f"param count: {len(schema['parameters'])}")

    print("\n== generate_svg ==")
    result = boxespy.generate_svg(
        "SimpleBox",
        {"x": 220, "y": 160, "h": 50},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    path = Path(result["output_path"])
    exists = path.is_file() and path.stat().st_size > 0
    print(f"\nwritten: {exists} ({path})")
    head = path.read_text(encoding="utf-8")[:120]
    print(f"svg head: {head!r}")

    print("\n== validate_svg ==")
    report = boxespy.validate_svg(result["file_id"])
    print(json.dumps(report, ensure_ascii=False, indent=2))

    print("\n== render_preview ==")
    preview = boxespy.render_preview(result["file_id"])
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    ok = exists and report["success"] and result["success"]
    print("\n== RESULT ==")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
