import unittest
from pathlib import Path
from semantic_cad import *

SVG='''<svg xmlns="http://www.w3.org/2000/svg" width="120mm" height="120mm" viewBox="0 0 120 120">
<g id="CUT"><path id="PART_A" data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="outer_contour" d="M10 10 L110 10 L110 110 L10 110 Z"/>
<path id="HOLE_1" data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="hole" d="M28 55 L32 55 L32 59 L28 59 Z"/>
<path id="HOLE_2" data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="hole" d="M58 55 L62 55 L62 59 L58 59 Z"/>
<path id="HOLE_3" data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="hole" d="M88 55 L92 55 L92 59 L88 59 Z"/></g></svg>'''

class SemanticCadTests(unittest.TestCase):
    def test_detects_part_features_and_safe_area(self):
        doc=inspect_design(SVG);self.assertEqual(len(doc['parts']),1);self.assertEqual(len(doc['parts'][0]['feature_ids']),3)
        safe=compute_safe_design_area(SVG,'PART_A',5,2);self.assertEqual(safe['bounds'],[15.0,15.0,105.0,105.0]);self.assertLess(safe['area'],8100)
    def test_turkish_multiline_text_becomes_paths_and_preserves_cad(self):
        item=create_text('ÖNCE GÜVENLİK\nİŞARET',parent_part_id='PART_A',font_size=7,placement='top_center')
        out=compose_design(SVG,[item]);self.assertTrue(out['success'],out['issues']);self.assertNotIn('<text',out['svg']);self.assertIn('PART_A',out['svg']);self.assertIn('#FFFF00',out['svg']);self.assertEqual(out['validation']['status'],'PASS')
    def test_three_labels_snap_to_actual_holes(self):
        elements=[create_text(label,parent_part_id='PART_A',font_size=4,anchor_feature_id=f'HOLE_{i}',offset_y=-10) for i,label in enumerate(['KIRMIZI','SARI','YEŞİL'],1)]
        out=compose_design(SVG,elements);self.assertTrue(out['success'],out['issues']);centers=[round((o['bounds'][0]+o['bounds'][2])/2) for o in out['objects']];self.assertEqual(centers,[30,60,90])
    def test_unknown_blocks_validation(self):
        raw=SVG.replace('<g id="CUT">','<g>').replace('data-operation="CUT" data-operation-origin="EXPLICIT" data-semantic-role="outer_contour"','',1)
        self.assertEqual(validate_composition(raw)['status'],'FAIL')
    def test_graphic_avoids_holes_and_stays_inside(self):
        graphic=create_vector_graphic('M0 0 L20 0 L20 20 L0 20 Z',parent_part_id='PART_A',placement='center')
        out=compose_design(SVG,[graphic]);self.assertTrue(out['success'],out['issues']);self.assertFalse(any(i['status']=='FAIL' for i in out['issues']))
    def test_alignment_and_distribution(self):
        rows=[create_text(str(i),position={'x':i*5,'y':i},size={'width':2,'height':2}) for i in range(3)]
        self.assertTrue(all(o['position']['x']==5 for o in align_objects(rows,'center_x',bounds=[0,0,10,10])))
        spread=distribute_objects([rows[0],{**rows[1],'position':{'x':9,'y':1}}, {**rows[2],'position':{'x':10,'y':2}}]);self.assertEqual([o['position']['x'] for o in spread],[0,5,10])
    def test_svg_and_dxf_operations(self):
        out=compose_design(SVG,[create_text('A B D O P R',parent_part_id='PART_A')]);dxf=export_dxf(out['svg']).decode();self.assertIn('CUT',dxf);self.assertIn('ENGRAVE',dxf)
    def test_edit_convert_and_repair_existing(self):
        text=create_text('LOGO',parent_part_id='PART_A',position={'x':60,'y':57},font_size=10)
        moved=edit_object(text,{'position':{'x':60,'y':95}});self.assertEqual(moved['id'],text['id'])
        self.assertIn('<path',convert_text_to_paths(moved)['d'])
        out=compose_design(SVG,[text]);fixed=repair_composition(out['svg']);self.assertTrue(fixed['success'],fixed['issues'])
    def test_rect_circle_existing_svg_and_duplicate_ask(self):
        raw='<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"><rect id="P" x="5" y="5" width="90" height="90" data-operation="CUT" data-operation-origin="EXPLICIT"/><circle id="H" cx="50" cy="50" r="5" data-operation="CUT" data-operation-origin="EXPLICIT"/></svg>'
        self.assertEqual(len(inspect_design(raw)['parts']),1)
        item=create_text('TITLE',id='TXT_FIXED',parent_part_id='P');first=compose_design(raw,[item]);second=compose_design(first['svg'],[item],duplicate_policy='ask')
        self.assertTrue(any('duplicate skipped' in i['note'] for i in second['issues']))
    def test_negative_scaled_viewbox_is_physical_mm(self):
        raw='<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="-5 -5 40 20"><path id="P" d="M-5 -5 L35 -5 L35 15 L-5 15 Z" data-operation="CUT" data-operation-origin="EXPLICIT"/></svg>'
        self.assertEqual(inspect_design(raw)['parts'][0]['bounds'],[0.0,0.0,20.0,10.0])
    def test_acceptance_visual_svg_snapshot(self):
        elements=[create_text('GÜVENLİ TASARIM',id='TXT_TITLE',parent_part_id='PART_A',font_size=7,placement='top_center')]
        elements += [create_text(s,id='TXT_'+str(i),parent_part_id='PART_A',font_size=4,anchor_feature_id='HOLE_'+str(i),offset_y=-10) for i,s in enumerate(['BİR','İKİ','ÜÇ'],1)]
        elements += [create_vector_graphic('M0 0 L5 10 L10 0 Z',id='GFX_LOGO',parent_part_id='PART_A',graphic_type='logo',placement='bottom_left',size={'width':12,'height':12})]
        actual=compose_design(SVG,elements);self.assertTrue(actual['success'],actual['issues'])
        expected=(Path(__file__).parent/'snapshots'/'semantic_acceptance.svg').read_text(encoding='utf-8')
        self.assertEqual(actual['svg'],expected)
    def test_remove_and_replace_object_preserve_cut(self):
        first=compose_design(SVG,[create_text('OLD',id='TXT_EDIT',parent_part_id='PART_A')])
        removed=remove_object(first['svg'],'TXT_EDIT');self.assertNotIn('TXT_EDIT',removed);self.assertIn('PART_A',removed)
        replaced=replace_object(first['svg'],'TXT_EDIT',create_text('NEW',parent_part_id='PART_A'));self.assertTrue(replaced['success']);self.assertIn('NEW',replaced['svg']);self.assertNotIn('OLD',replaced['svg'])
