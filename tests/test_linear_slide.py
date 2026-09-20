import unittest

from assembly_steps import build_assembly_steps
from pipeline import review_only
from toolbox import render_toolbox


def panel(label,w,h,origin,u=(1,0,0),v=(0,1,0),moving=False):
    return {'type':'panel','label':label,'w':w,'h':h,'edges':'eeee','moving':moving,'placement':{'origin':list(origin),'u':list(u),'v':list(v)}}


def trash_bin(clearance=.5):
    parts=[
        panel('front',400,700,(0,0,0),u=(1,0,0),v=(0,0,1)),
        panel('back',400,700,(0,400,0),u=(1,0,0),v=(0,0,1)),
        panel('left',400,700,(0,0,0),u=(0,1,0),v=(0,0,1)),
        panel('right',400,700,(400,0,0),u=(0,1,0),v=(0,0,1)),
        panel('bottom',400,400,(0,0,0)),
        panel('top-frame',400,40,(0,0,700)),
        panel('top-lid-fixed',400,200,(0,200,706)),
        panel('top-lid-sliding',400,180,(0,0,712),moving=True),
        panel('lid-rail-left',220,12,(-6,0,706)),
        panel('lid-rail-right',220,12,(406,0,706)),
        panel('servo-holder',60,50,(430,300,620)),
    ]
    params={'thickness':3,'connections':[{'id':'lid-slide','type':'linear_slide','moving_part':'top-lid-sliding','rails':['lid-rail-left','lid-rail-right'],'axis':[0,1,0],'travel_mm':180,'clearance_mm':clearance}]}
    return parts,params


class LinearSlideIntegrationTests(unittest.TestCase):
    def test_placed_sliding_bin_has_preview_motion_and_steps(self):
        parts,params=trash_bin();built=review_only(render_toolbox(parts,params));motion=built['linear_motion'];dmap=built['design_map']
        self.assertIn('top-lid-sliding',dmap['moving_parts'])
        self.assertTrue(all(p.get('placement') for p in dmap['parts']))
        self.assertIsNotNone(built['assembly']['assembled_preview_svg'])
        self.assertEqual([p['travel_mm'] for p in motion['slides'][0]['positions']],[0,45,90,135,180])
        self.assertEqual(motion['status'],'PASS');self.assertIn('collisions',motion['slides'][0])
        steps=build_assembly_steps(built['primitives'],built['assembly'],params)
        self.assertEqual(steps['status'],'AVAILABLE');self.assertTrue(steps['steps'])

    def test_negative_clearance_blocks_motion_and_final_gate(self):
        parts,params=trash_bin(-.1);built=review_only(render_toolbox(parts,params))
        self.assertEqual(built['linear_motion']['status'],'FAIL')
        self.assertEqual(built['review']['categories']['MOTION_CLEARANCE']['status'],'FAIL')
        self.assertEqual(built['final_status'],'BLOCKED');self.assertEqual(built['authorized_output'],'None')

    def test_servo_without_linkage_is_not_verified(self):
        parts,params=trash_bin();params['connections'].append({'type':'servo_linear_drive','motor_part':'servo-holder','driven_part':'top-lid-sliding','slide_connection':'lid-slide','servo_axis':[0,0,1],'servo_angle_min':0,'servo_angle_max':90,'required_travel_mm':180})
        built=review_only(render_toolbox(parts,params))
        self.assertEqual(built['linear_motion']['drives'][0]['status'],'NOT_VERIFIED')
        self.assertEqual(built['final_status'],'BLOCKED')


if __name__=='__main__':unittest.main()
