import unittest
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
