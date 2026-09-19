import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from laser_settings import resolve_operation_settings,stamp_operation_settings

class LaserSettingsTests(unittest.TestCase):
 def test_engrave_is_single_low_power_surface_pass(self):
  profile=resolve_operation_settings();cut=profile['operations']['CUT'];engrave=profile['operations']['ENGRAVE']
  self.assertLess(engrave['speed_scale'],cut['speed_scale']);self.assertLess(engrave['power_scale'],cut['power_scale']);self.assertEqual(engrave['passes'],1);self.assertFalse(engrave['through_cut'])
  svg=stamp_operation_settings(b'<svg xmlns="http://www.w3.org/2000/svg"><g id="CUT" data-operation="CUT"/><g id="ENGRAVE" data-operation="ENGRAVE"/></svg>',profile).decode()
  self.assertIn('data-laser-mode="surface_engrave"',svg);self.assertIn('data-through-cut="false"',svg)
 def test_unsafe_engrave_profile_is_rejected(self):
  with self.assertRaises(ValueError):resolve_operation_settings({'operation_settings':{'ENGRAVE':{'power_scale':1}}})
  with self.assertRaises(ValueError):resolve_operation_settings({'operation_settings':{'ENGRAVE':{'passes':2}}})
  with self.assertRaisesRegex(ValueError,'power_percent'):resolve_operation_settings({'operation_settings':{'CUT':{'power_percent':55},'ENGRAVE':{'power_percent':55}}})

 def test_saved_report_keeps_profile_and_dxf_uses_final_svg(self):
  import boxes_adapter
  raw=b'<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="20mm" viewBox="0 0 20 20"><g data-operation="CUT"><path data-operation="CUT" data-semantic-role="outer_contour" data-operation-origin="EXPLICIT" d="M1 1L19 1L19 19L1 19Z"/></g><g data-operation="ENGRAVE"><path data-operation="ENGRAVE" data-semantic-role="text" data-operation-origin="EXPLICIT" d="M5 5L15 5"/></g></svg>'
  with tempfile.TemporaryDirectory() as tmp,patch.object(boxes_adapter,'OUTPUT_DIR',Path(tmp)),patch('plans.entitled',return_value=True),patch('studio.attach',side_effect=lambda extra,*a:extra),patch('studio.finish_result',side_effect=lambda result,*a:result),patch('persist.job.attach_durable_artifacts',side_effect=lambda result,*a:result):
   result=boxes_adapter.save_generated_svg(raw,extra={'generator':'profile-test','parameters':{'operation_settings':{'ENGRAVE':{'speed_scale':.5,'power_scale':.2}}}},dxf_bytes=b'stale')
   report=json.loads((Path(tmp)/result['report_id']).read_text(encoding='utf-8'))
   self.assertEqual(report['operation_settings']['operations']['ENGRAVE']['speed_scale'],.5)
   self.assertNotEqual((Path(tmp)/result['dxf_id']).read_bytes(),b'stale')
   self.assertIn(b'ENGRAVE',(Path(tmp)/result['dxf_id']).read_bytes())
   self.assertEqual(result['assembly_steps']['status'],'NOT_AVAILABLE')
