import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from svgpathtools import parse_path

from standard_models import get_standard_model, model_recipe, model_parameters, ROOT
from toolbox import render_toolbox
from review import review_built
from semantic_cad import inspect_design


class StandardModelTests(unittest.TestCase):
    def test_standard_house_has_real_closed_parts_and_verified_mates(self):
        built = render_toolbox(model_recipe(), model_parameters())
        report = review_built(built)
        self.assertEqual(report['final_status'],'PROTOTYPE READY',report['look_again'])
        self.assertEqual(built['assembly']['tab_slot_pairs'],11)
        self.assertEqual(len(inspect_design(built['svg_bytes'])['parts']),7)
        self.assertEqual(built['topology']['nicked_closed'],0)
        for el in ET.fromstring(built['svg_bytes']).iter():
            if el.tag.endswith('path') and el.get('data-operation')=='CUT':
                self.assertTrue(all(abs(p.start-p.end)<1e-7 for p in parse_path(el.get('d')).continuous_subpaths()))
        self.assertTrue(built['assembly']['assembled_preview_svg'])

    def test_permanent_assets_do_not_use_job_expiry_storage(self):
        model = get_standard_model(base_url='https://example.test')
        self.assertTrue(model['success'])
        self.assertIsNone(model['expires_at'])
        self.assertEqual(model['thickness_mm'],2.7)
        self.assertEqual(model['production_export'],'BLOCKED')
        for key in ('svg_url','dxf_url','source_svg_url','recipe_url'):
            self.assertTrue(model[key].startswith('https://example.test/demo/'))
            self.assertTrue((ROOT/'web'/'demo'/model[key].rsplit('/',1)[1]).is_file())
        self.assertFalse(get_standard_model('../secret')['success'])

    def test_thickness_derived_placements_remain_valid(self):
        from house_holder import recipe
        from assembly import check_assembly
        for thickness in (2.7,3):
            result = check_assembly(recipe(thickness=thickness),thickness=thickness)
            self.assertTrue(result['ok'],result['look_again'])


class SourceModelTests(unittest.TestCase):
    def test_source_geometry_is_preserved_and_only_gaps_are_added(self):
        from tools.build_standard_models import SOURCE, remove_source_nicks
        from collections import Counter
        from svgpathtools import Line
        original = SOURCE.read_bytes()
        result, repairs = remove_source_nicks(original, straighten=False)
        def segments(data):
            rows=[]
            for e in ET.fromstring(data).iter():
                if not e.tag.endswith('path'): continue
                for seg in parse_path(e.get('d')):
                    self.assertIsInstance(seg,Line)
                    rows.append(tuple(sorted(((round(seg.start.real,6),round(seg.start.imag,6)),(round(seg.end.real,6),round(seg.end.imag,6))))))
            return Counter(rows)
        before,after=segments(original),segments(result)
        self.assertFalse(before-after, 'original segment removed or moved')
        self.assertEqual(sum((after-before).values()),len(repairs))
        self.assertEqual(len(repairs),79)
        self.assertEqual(ET.fromstring(original).attrib,ET.fromstring(result).attrib)
        for e in ET.fromstring(result).iter():
            if e.tag.endswith('path'): self.assertTrue(parse_path(e.get('d')).isclosed())


    def test_no_unrelated_assembly_pass_or_preview_is_claimed(self):
        result=get_standard_model()
        self.assertEqual(result['source_type'],'user_supplied_svg')
        self.assertIsNone(result['assembled_preview_url'])
        self.assertEqual(result['assembly'],'NOT VERIFIED')
        self.assertEqual(result['production_export'],'BLOCKED')
        self.assertEqual(result['topology']['open_cuts'],[])
        self.assertEqual(result['topology']['nicked_closed'],0)
        self.assertEqual(result['topology']['self_intersections'],[])


    def test_square_gap_repairs_keep_real_slopes(self):
        from tools.build_standard_models import gap_segments
        from svgpathtools import Line
        spans=gap_segments(complex(169.3,105.55),complex(169,106.2),Line(180+105.55j,169.3+105.55j),Line(169+106.2j,153+106.2j))
        self.assertEqual(len(spans),3)
        self.assertTrue(all(abs((q.end-q.start).real)<1e-8 or abs((q.end-q.start).imag)<1e-8 for q in spans))
        self.assertEqual(len(gap_segments(1+1j,2+2j,Line(0j,1+1j),Line(2+2j,3+3j))),1)

    def test_clean_svg_and_dxf_have_identical_vertices_in_mm(self):
        from tools.build_standard_models import SOURCE,remove_source_nicks
        from collections import Counter
        svg=(ROOT/'web/demo/house-pencil-holder.svg').read_bytes()
        self.assertEqual(remove_source_nicks(SOURCE.read_bytes())[0],svg)
        expected=[]
        for e in ET.fromstring(svg).iter():
            if e.tag.endswith('path'):
                for q in parse_path(e.get('d')):
                    expected.append((round(q.start.real+5,4),round(309.6-(q.start.imag+5),4)))
        lines=(ROOT/'web/demo/house-pencil-holder.dxf').read_text().splitlines()
        pairs=list(zip(lines[::2],lines[1::2]));actual=[];point=None
        for code,value in pairs:
            if code=='0':
                if point is not None:actual.append((point['10'],point['20']))
                point={} if value=='VERTEX' else None
            elif point is not None and code in ('10','20'):point[code]=round(float(value),4)
        self.assertEqual(Counter(expected),Counter(actual))
