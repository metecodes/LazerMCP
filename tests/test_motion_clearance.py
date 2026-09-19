import unittest
from motion_clearance import check_motion_clearance,resolve_motion

def panel(label,z):
 return {'type':'contour','label':label,'points':[[-20,-20],[20,-20],[20,20],[-20,20]],'placement':{'origin':[0,0,z],'u':[1,0,0],'v':[0,1,0]}}

def propeller():
 return {'type':'contour','label':'propeller','points':[[-10,-1],[10,-1],[10,1],[-10,1]],'placement':{'origin':[0,0,0],'u':[1,0,0],'v':[0,1,0]}}

class MotionClearanceTests(unittest.TestCase):
 def test_direct_motor_axis_and_clear_sweep(self):
  motion={'drive_type':'direct_motor_shaft','motor_axis':{'origin':[0,0,-5],'direction':[0,0,1]},'propeller_center':[0,0,0],'radius_mm':10,'moving_part':'propeller'}
  motion['motor_part']='motor'
  report=check_motion_clearance([panel('body',10),propeller()],motion,3)
  self.assertEqual(report['status'],'PASS')
 def test_swept_disk_collision_fails(self):
  motion={'motor_axis':{'origin':[0,0,-5],'direction':[0,0,1]},'propeller_center':[0,0,0],'radius_mm':10,'moving_part':'propeller'}
  report=check_motion_clearance([panel('body',0)],motion,3)
  self.assertEqual(report['status'],'FAIL');self.assertIn('body',report['note'])
 def test_missing_motion_geometry_is_not_verified(self):
  self.assertEqual(check_motion_clearance([],{},3)['status'],'NOT_VERIFIED')
 def test_direct_motor_connection_is_resolved_as_a_typed_connection(self):
  params={'connections':[{'type':'direct_motor_shaft','motor_part':'motor','driven_part':'propeller','shaft_axis':{'origin':[0,0,-5],'direction':[0,0,1]},'driven_center':[0,0,0],'radius_mm':10}]}
  motion=resolve_motion(params)
  self.assertEqual(motion['drive_type'],'direct_motor_shaft')
  self.assertEqual(motion['moving_part'],'propeller')
  self.assertEqual(motion['connection_source'],'parameters.connections')
  self.assertEqual(check_motion_clearance([panel('body',10),propeller()],motion,3)['status'],'PASS')
 def test_direct_motor_connection_rejects_missing_driven_geometry(self):
  motion={'drive_type':'direct_motor_shaft','motor_part':'motor','moving_part':'missing','motor_axis':{'origin':[0,0,0],'direction':[0,0,1]},'propeller_center':[0,0,0],'radius_mm':10}
  report=check_motion_clearance([panel('body',10)],motion,3)
  self.assertEqual(report['status'],'FAIL')

if __name__=='__main__':unittest.main()
