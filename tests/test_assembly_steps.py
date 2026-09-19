import unittest
from xml.etree import ElementTree as ET
from assembly_steps import build_assembly_steps
from assembly import check_assembly
from house_holder import recipe

class AssemblyStepTests(unittest.TestCase):
 def test_progressive_steps_follow_verified_house_placements(self):
  parts=recipe();assembly=check_assembly(parts)
  plan=build_assembly_steps(parts,assembly,{'assembly_request':'Kalemliği tabandan başlayarak ayakta kur.'})
  self.assertEqual(plan['status'],'READY');self.assertEqual(len(plan['steps']),len(parts));self.assertEqual(plan['request'],'Kalemliği tabandan başlayarak ayakta kur.')
  first=ET.fromstring(plan['steps'][0]['svg_bytes']);last=ET.fromstring(plan['steps'][-1]['svg_bytes'])
  self.assertEqual(len([e for e in first.iter() if e.get('data-panel')]),1)
  self.assertEqual(len([e for e in last.iter() if e.get('data-panel')]),len(parts))
  self.assertIn('#f2a65a',plan['steps'][0]['svg_bytes'].decode())
  self.assertEqual(plan['physical_fit'],'NOT VERIFIED')

 def test_explicit_final_request_order_and_notes(self):
  parts=recipe();labels=[p['label'] for p in parts];order=list(reversed(labels))
  plan=build_assembly_steps(parts,check_assembly(parts),{'assembly_order':order,'assembly_notes':['Önce arka parçayı tak.']})
  self.assertEqual(plan['order'],order);self.assertEqual(plan['steps'][0]['instruction'],'Önce arka parçayı tak.')

 def test_incomplete_order_or_missing_placements_never_guesses(self):
  parts=recipe()
  blocked=build_assembly_steps(parts,check_assembly(parts),{'assembly_order':[parts[0]['label']]})
  self.assertEqual(blocked['status'],'BLOCKED')
  unavailable=build_assembly_steps([{'type':'panel','label':'flat','w':10,'h':10}],{}, {})
  self.assertEqual(unavailable['status'],'NOT_AVAILABLE')

if __name__=='__main__':unittest.main()
