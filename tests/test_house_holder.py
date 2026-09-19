import unittest
from copy import deepcopy
from house_holder import recipe
from assembly import check_assembly
from job_planner import plan_laser_job

class HouseHolderTests(unittest.TestCase):
 def test_reference_recipe_has_no_duplicate_box(self):
  p=plan_laser_job('ev şeklinde kalemlik pencil holder')
  parts=p['next_arguments']['primitives']
  self.assertEqual(len(parts),7)
  self.assertNotIn('box',[p['type'] for p in parts])
  report=check_assembly(parts)
  self.assertTrue(report['ok'],report['look_again'])
  self.assertEqual(report['tab_slot_pairs'],11)
  self.assertEqual(report['graph']['node_count'],7)
  self.assertIn('front-house-face',report['assembled_preview_svg'])
 def test_unmatched_decorative_slot_does_not_pass(self):
  parts=[{'type':'contour','label':'face','points':[[0,0],[130,0],[130,130],[65,180],[0,130]],'slots':[{'x':5,'y':30,'w':3,'h':48}]}]
  report=check_assembly(parts)
  self.assertFalse(report['ok'])
  self.assertIsNone(report['assembled_preview_svg'])
 def test_off_outline_slot_detected(self):
  parts=recipe();parts[0]['slots'].append({'x':5,'y':175,'w':10,'h':10})
  self.assertFalse(check_assembly(parts)['ok'])
 def test_wrong_mating_position_detected(self):
  parts=recipe();parts[2]['placement']['origin'][0]+=1
  self.assertFalse(check_assembly(parts)['ok'])
 def test_compiler_materializes_touching_tab_into_cut_outline(self):
  parts=recipe();parts[2]['points']=[[0,0],[84,0],[84,130],[0,130]]
  self.assertTrue(check_assembly(parts)['ok'])
 def test_tab_metadata_inside_plain_rectangle_is_not_outer_cut_geometry(self):
  parts=recipe()
  parts[2]['points']=[[0,0],[84,0],[84,130],[0,130]]
  parts[2]['tabs'][0]={'id':'front','x':1.5,'y':65,'w':3,'h':90}
  report=check_assembly(parts)
  self.assertFalse(report['ok'])
  self.assertTrue(any('metadata only' in issue for issue in report['look_again']),report['look_again'])
 def test_pose_basis_is_not_scaled(self):
  from scale import scale_obj
  p=scale_obj(recipe()[0],2)
  self.assertEqual(p['placement']['u'],[1,0,0]);self.assertEqual(p['placement']['origin'],[0,6,0])
 def test_invalid_create_does_not_claim_success(self):
  from payas_cad import create_design
  from unittest.mock import patch
  with patch('plans.gate_job',return_value={'ok':True}),patch('design_engine.compile_design',side_effect=ValueError('bad recipe')):
   r=create_design(primitives=[{'type':'invalid'}])
  self.assertFalse(r['success']);self.assertFalse(r['ready_to_cut'])

if __name__=='__main__':unittest.main()
