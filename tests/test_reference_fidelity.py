import unittest
from reference_fidelity import check_reference_fidelity

class ReferenceFidelityTests(unittest.TestCase):
 def test_helicopter_reference_rejects_rectangle_outer_cut(self):
  params={'reference_job':True,'reference_parts':[{'reference_part':'helicopter silhouette','generated_part':'govde-sol','expected_outer_shape':'helicopter'}]}
  report=check_reference_fidelity(params,[{'type':'panel','label':'govde-sol','w':100,'h':40,'operation':'CUT'}])
  self.assertEqual(report['outer_cut'][0]['status'],'FAIL')
  self.assertIn('reference silhouette is not the outer cut contour',report['outer_cut'][0]['note'])

 def test_custom_outer_cut_and_one_to_one_mapping_pass(self):
  points=[[0,10],[20,10],[30,20],[55,20],[65,10],[90,10],[70,30],[35,35]]
  params={'reference_job':True,'reference_parts':[{'reference_part':'helicopter silhouette','generated_part':'govde-sol','expected_outer_shape':'helicopter','silhouette_points':points}]}
  report=check_reference_fidelity(params,[{'type':'contour','label':'govde-sol','points':points,'operation':'CUT'}])
  self.assertTrue(all(c['status']=='PASS' for c in report['fidelity']))

 def test_missing_reference_evidence_is_not_verified(self):
  report=check_reference_fidelity({'reference_job':True},[])
  self.assertEqual(report['fidelity'][0]['status'],'NOT_VERIFIED')

 def test_reference_physical_ids_must_be_unique(self):
  refs=[
   {'id':'side','reference_part':'left','generated_part':'left','role':'decoration'},
   {'id':'side','reference_part':'right','generated_part':'right','role':'decoration'},
  ]
  report=check_reference_fidelity({'reference_job':True,'reference_parts':refs},[{'type':'panel','label':'left'},{'type':'panel','label':'right'}])
  self.assertTrue(any(c['status']=='FAIL' and 'unique' in c['note'] for c in report['part_mapping']))

 def test_photo_derived_house_can_only_pass_with_complete_mapping_and_preview(self):
  from house_holder import recipe
  from design_engine import compile_design
  parts=recipe();refs=[{'reference_part':p['label'],'generated_part':p['label'],'expected_outer_shape':'contour','role':'decoration' if p.get('attachment') else 'structural'} for p in parts]
  built=compile_design(primitives=parts,parameters={'reference_job':True,'reference_parts':refs})
  self.assertEqual(built['final_status'],'PROTOTYPE READY')
  self.assertEqual(built['review']['categories']['REFERENCE_FIDELITY']['status'],'PASS')
  self.assertEqual(built['review']['categories']['3D_ASSEMBLY']['status'],'PASS')

if __name__=='__main__':unittest.main()
