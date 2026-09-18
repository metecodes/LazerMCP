import unittest,math
from unittest.mock import patch
from plt_import import import_plt_document
from seen import check_what_you_see
from house_holder import recipe

class CompletenessRegressionTests(unittest.TestCase):
 def test_quoted_product_name_is_not_lettering(self):
  self.assertEqual(check_what_you_see(recipe(),'"Ev Kalemliği" modeli'),[])
 def test_absent_features_are_not_required(self):
  self.assertEqual(check_what_you_see(recipe(),'Pervane yok, yazı yok, gravür yok; no rotor; without lettering'),[])
 def test_positive_request_still_blocks_missing_rotor(self):
  self.assertTrue(any(a['status']=='FAIL' for a in check_what_you_see(recipe(),'4 kanatlı pervane var')))
 def test_missing_text_still_blocks(self):
  self.assertTrue(any(a['status']=='FAIL' for a in check_what_you_see(recipe(),'Ön yüzde "PAYAS" yazı var')))
 def test_default_text_marking_is_recognized(self):
  p={'type':'panel','markings':[{'value':'PAYAS','x':10,'y':10,'width':5}]}
  self.assertTrue(all(a['status']=='PASS' for a in check_what_you_see([p],'PAYAS yazısı var')))
 def test_engraved_icon_is_not_missing_text(self):
  p={'type':'panel','markings':[{'kind':'icon','icon':'star','x':10,'y':10,'width':5}]}
  self.assertTrue(all(a['status']=='PASS' for a in check_what_you_see([p],'Yıldız gravür var')))
  self.assertTrue(any(a['status']=='FAIL' for a in check_what_you_see([p],'PAYAS yazı var')))
 def test_house_contour_roof_name_is_not_a_separate_roof(self):
  from toolbox import render_toolbox
  from review import review_built
  p=recipe();p[0]['label']='house-roof-front'
  for a in p:
   if (a.get('attachment') or {}).get('to')=='front-house-face':a['attachment']['to']='house-roof-front'
  b=render_toolbox(p,{'what_you_see':'"Ev Kalemliği"; pervane yok; yazı yok; pencereler var'})
  r=review_built(b)
  self.assertEqual(r['categories']['PART_COMPLETENESS']['status'],'PASS',r['look_again'])
  self.assertEqual(r['final_status'],'PROTOTYPE READY')
  b['parameters']['what_you_see']='PAYAS yazı var'
  r=review_built(b)
  self.assertEqual(r['final_status'],'BLOCKED')
  self.assertIn('BLOCKING REASONS',r['speak'])
  self.assertTrue(any(a['category']=='PART_COMPLETENESS' for a in r['blocking_checks']))

class PLTTests(unittest.TestCase):
 def test_absolute_rectangle_preserves_mm(self):
  b=import_plt_document('IN;SP1;PU0,0;PD400,0,400,800,0,800,0,0;PU;SP0;')
  self.assertEqual(b['plt_import']['source_bounds_mm'],[0,0,10,20]);self.assertEqual(b['plt_import']['closed_paths'],1)
  from xml.etree import ElementTree as ET
  p=ET.fromstring(b['svg_bytes']).find('.//{http://www.w3.org/2000/svg}path')
  self.assertTrue(p.get('d').startswith('M2.000000,22.000000 L12.000000,22.000000 L12.000000,2.000000'))
 def test_relative_and_penup_do_not_join_unrelated_paths(self):
  b=import_plt_document('PU0,0;PR;PD400,0,0,400;PU400,0;PD0,400;')
  self.assertEqual(b['count'],2);self.assertEqual(b['plt_import']['source_bounds_mm'],[0,0,20,20])
 def test_consecutive_commands_without_semicolons(self):
  b=import_plt_document('INSP1PU0,0PD400,0,400,400PU')
  self.assertEqual(b['plt_import']['source_bounds_mm'],[0,0,10,10])
 def test_circle_even_with_pen_up(self):
  b=import_plt_document('PU400,400;CI400;')
  a=b['plt_import']['source_bounds_mm']
  for x,y in zip(a,[0,0,20,20]):self.assertAlmostEqual(x,y,delta=.02)
  self.assertEqual(b['plt_import']['closed_paths'],1)
 def test_absolute_and_relative_arcs(self):
  b=import_plt_document('PU400,0;PD;AA0,0,90;AR0,-400,90;PU;')
  bounds=b['plt_import']['source_bounds_mm'];self.assertAlmostEqual(bounds[0],-10,delta=.02);self.assertAlmostEqual(bounds[3],10,delta=.02)
 def test_scaling_with_explicit_ip(self):
  b=import_plt_document('IP0,0,4000,8000;SC0,100,0,100;PU0,0;PD100,100;')
  self.assertEqual(b['plt_import']['source_bounds_mm'],[0,0,100,200])
 def test_rotation_and_negative_coordinates(self):
  b=import_plt_document('RO90;PU-400,-400;PD0,0;')
  a=b['plt_import']['source_bounds_mm']
  for x,y in zip(a,[0,-10,10,0]):self.assertAlmostEqual(x,y)
 def test_pen_operations(self):
  b=import_plt_document('SP1;PU0,0;PD400,0;SP2;PU0,400;PD400,400;',{'plt_pen_operations':{'2':'ENGRAVE'}})
  self.assertIn(b'data-operation="ENGRAVE"',b['svg_bytes']);self.assertIn(b'data-operation="CUT"',b['svg_bytes'])
 def test_unknown_or_unsupported_geometry_never_silently_skipped(self):
  for command in ('PEabc;','LBPAYAS\x03;','PM0;','ZZ0;','SC0,100,0,100;','PD1;','CI-1;','RO45;'):
   with self.subTest(command=command),self.assertRaises(ValueError):import_plt_document('PU0,0;PD400,0;'+command)
 def test_empty_binary_and_multi_page_rejected(self):
  for text in ('','PU0,0;','\x00\x80','PU0,0;PD400,0;PG;PD0,400;'):
   with self.subTest(text=text),self.assertRaises(ValueError):import_plt_document(text)
 def test_pcl_wrappers(self):
  self.assertEqual(import_plt_document('\x1b%0BIN;PU0,0;PD400,0;\x1b%0A')['count'],1)
 def test_mcp_source_and_base64_error_status(self):
  from payas_cad import create_design
  import base64
  with patch('plans.gate_job',return_value={'ok':True}),patch('payas_cad._save_build',side_effect=lambda raw,*a,**kw: {'success':True,'svg':raw.decode(),**a[3]}):
   r=create_design(plt_base64=base64.b64encode(b'PU0,0;PD400,0,400,400,0,400,0,0;PU;').decode())
   self.assertTrue(r['success']);self.assertEqual(r['plt_import']['format'],'HP-GL')
   self.assertNotEqual(r['final_status'],'BLOCKED',r.get('look_again'))
   bad=create_design(plt='PU0,0;PD1;')
   self.assertFalse(bad['success'])

if __name__=='__main__':unittest.main()
