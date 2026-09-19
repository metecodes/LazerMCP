import unittest
from motion_clearance import check_motion_clearance

def panel(label,z):
 return {'type':'contour','label':label,'points':[[-20,-20],[20,-20],[20,20],[-20,20]],'placement':{'origin':[0,0,z],'u':[1,0,0],'v':[0,1,0]}}

class MotionClearanceTests(unittest.TestCase):
 def test_direct_motor_axis_and_clear_sweep(self):
  motion={'drive_type':'direct_motor_shaft','motor_axis':{'origin':[0,0,-5],'direction':[0,0,1]},'propeller_center':[0,0,0],'radius_mm':10,'moving_part':'propeller'}
  report=check_motion_clearance([panel('body',10)],motion,3)
  self.assertEqual(report['status'],'PASS')
 def test_swept_disk_collision_fails(self):
  motion={'motor_axis':{'origin':[0,0,-5],'direction':[0,0,1]},'propeller_center':[0,0,0],'radius_mm':10,'moving_part':'propeller'}
  report=check_motion_clearance([panel('body',0)],motion,3)
  self.assertEqual(report['status'],'FAIL');self.assertIn('body',report['note'])
 def test_missing_motion_geometry_is_not_verified(self):
  self.assertEqual(check_motion_clearance([],{},3)['status'],'NOT_VERIFIED')

if __name__=='__main__':unittest.main()
