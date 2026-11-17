"""Cut parts that fit either way up: the workshop should never have to find a wall's "top".

A closed box's walls once had their corner fingers t/2 low (only the floor corners were
extended) and the shelf and divider holes sat off the middle, so every wall went in one way
only. These tests turn each part upside down and compare it with itself.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "vision_eval"))


def cut_parts(primitives):
    """Each part of the DXF as one polygon with its holes (holding tabs bridged)."""
    import make_synthetic as ms
    import payas_cad
    from shapely.geometry import Polygon

    built = payas_cad.create_design(primitives=primitives, parameters={"thickness": 3})
    assert built.get("final_status") == "PROTOTYPE READY", built.get("final_status")
    segs = [list(p) for p in ms.dxf_polylines(ms.find_output(built["dxf_id"]))]

    def near(a, b):
        return abs(a[0] - b[0]) < 1.6 and abs(a[1] - b[1]) < 1.6

    loops = []
    while segs:
        cur = segs.pop(0)
        grown = True
        while grown and not (len(cur) > 3 and near(cur[0], cur[-1])):
            grown = False
            for k, s in enumerate(segs):
                if near(cur[-1], s[0]):
                    cur += s[1:]
                elif near(cur[-1], s[-1]):
                    cur += s[::-1][1:]
                elif near(cur[0], s[-1]):
                    cur = s + cur[1:]
                elif near(cur[0], s[0]):
                    cur = s[::-1] + cur[1:]
                else:
                    continue
                segs.pop(k)
                grown = True
                break
        loops.append(cur)
    polys = sorted((Polygon(p).buffer(0) for p in loops if len(p) >= 4), key=lambda p: -p.area)
    parts = []
    for p in polys:
        if p.geom_type != "Polygon" or p.area <= 1:
            continue
        host = next((i for i, o in enumerate(parts) if o.contains(p.representative_point())), None)
        if host is None:
            parts.append(Polygon(p.exterior))
        else:
            parts[host] = parts[host].difference(p)
    return parts


def turned_over_mismatch(part):
    from shapely import affinity

    turned = affinity.rotate(part, 180, origin=part.envelope.centroid)
    return part.symmetric_difference(turned).area / part.area


class ReversiblePartsTests(unittest.TestCase):
    def assert_reversible(self, primitives, expect_parts):
        parts = cut_parts(primitives)
        self.assertEqual(len(parts), expect_parts)
        for i, part in enumerate(parts):
            with self.subTest(part=i, size=[round(v) for v in part.bounds]):
                self.assertLess(turned_over_mismatch(part), 0.002)

    def test_closed_box_walls_fit_either_way_up(self):
        self.assert_reversible([{"type": "box", "x": 120, "y": 80, "h": 60, "lid": True}], 6)
        self.assert_reversible([{"type": "box", "x": 237, "y": 151, "h": 93, "lid": True}], 6)

    def test_shelf_holes_in_a_closed_box_are_centred(self):
        self.assert_reversible([{"type": "box", "x": 150, "y": 100, "h": 200, "lid": True, "shelves": 2}], 8)

    def test_bookshelf_side_slots_are_symmetric(self):
        import panel_kits

        for middle in (1, 2, 3, 5):
            with self.subTest(middle=middle):
                parts, _ = panel_kits.carcass(300, 150, 400, 3, middle)
                hi = 400 - 2 * 3
                ys = sorted(s["y"] for s in panel_kits.find(parts, "left")["slots"])
                for a, b in zip(ys, reversed(ys)):
                    self.assertAlmostEqual(a + b, hi, delta=0.15)


if __name__ == "__main__":
    unittest.main()
