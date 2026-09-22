import unittest,json,math
from pathlib import Path
from copy import deepcopy
from tests.test_structural_mates import pair
from explicit_mates import prepare_parts,validate_connectors,COMPATIBLE
from assembly import check_assembly
from toolbox import render_toolbox
from review import review_built
from assembly_steps import build_assembly_steps


def connectors():
    p=pair()
    p[0]['connectors']=[{'id':'a','type':'tab','part_id':'alpha','mate_id':'b','position':[11.5,22,1.5],'axis':[1,0,0],'width_mm':24,'depth_mm':3,'thickness_mm':3}]
    p[1]['connectors']=[{'id':'b','type':'slot','part_id':'beta','mate_id':'a','position':[22,1.5,1.5],'axis':[0,0,1],'width_mm':24,'depth_mm':3,'thickness_mm':3}]
    return p

class ExplicitMateTests(unittest.TestCase):
    def test_reciprocal_geometry_insertion_and_steps(self):
        p=connectors();before=deepcopy(p);params={'assembly_order':['beta','alpha'],'holding_nicks':False,'surface_texts':[],'thickness':3}
        built=render_toolbox(p,params);r=review_built(built)
        self.assertEqual(p,before)
        self.assertEqual(r['final_status'],'PROTOTYPE READY',r['look_again'])
        for part in r['design_map']['parts']:
            self.assertTrue(part['connectors']);self.assertTrue(part['mates'][0]['geometry_verified'])
        steps=build_assembly_steps(built['primitives'],built['assembly'],params)
        self.assertEqual(steps['status'],'AVAILABLE')
        self.assertEqual(steps['steps'][1]['mate_ids'],['mate:a:b'])
        self.assertEqual(steps['steps'][1]['insertion_direction'],[1,0,0])

    def test_specific_error_codes(self):
        cases=[('MATE_TARGET_NOT_FOUND',lambda p:p[0]['connectors'][0].update(mate_id='gone')),
               ('NON_RECIPROCAL_MATE',lambda p:p[1]['connectors'][0].update(mate_id='gone')),
               ('MATE_DIMENSION_MISMATCH',lambda p:p[0]['connectors'][0].update(width_mm=30)),
               ('MATE_POSITION_MISMATCH',lambda p:p[0]['connectors'][0].update(position=[15,22,1.5])),
               ('MATE_AXIS_MISMATCH',lambda p:p[0]['connectors'][0].update(axis=[0,1,0])),
               ('NON_COMPLEMENTARY_JOINT',lambda p:p[1]['connectors'][0].update(type='tab'))]
        for code,mutate in cases:
            p=connectors();mutate(p);r=check_assembly(p)
            self.assertFalse(r['ok'],code);self.assertIn(code,str(r['canonical_mates']['errors']))
            self.assertEqual(build_assembly_steps(p,r)['steps'],[])

    def test_duplicate_feature_and_unsupported_physics_fail(self):
        p=connectors();p[0]['connectors'].append(deepcopy(p[0]['connectors'][0]))
        self.assertIn('DUPLICATE_MATE',str(check_assembly(p)['look_again']))
        p=connectors();p[0]['connectors'][0]['type']='hinge';p[1]['connectors'][0]['type']='hinge'
        self.assertIn('MATE_GEOMETRY_UNSUPPORTED',str(check_assembly(p)['look_again']))

    def test_insertion_obstacle_fails_continuously(self):
        p=connectors()
        obstacle={'type':'panel','label':'blocker','role':'decorative','w':44,'h':20,'placement':{'origin':[-5,0,0],'u':[0,1,0],'v':[0,0,1]}}
        p.append(obstacle)
        r=check_assembly(p,parameters={'assembly_order':['blocker','beta','alpha']})
        self.assertFalse(r['ok']);self.assertIn('INSERTION_PATH_COLLISION',str(r['look_again']))
        self.assertFalse(build_assembly_steps(p,r)['steps'])

    def test_approximate_roof_frame_normalizes_invalid_frame_fails(self):
        p=connectors();angle=.6;c,s=round(math.cos(angle),5),round(math.sin(angle),5)
        def rot(v):return [c*v[0]+s*v[2],v[1],-s*v[0]+c*v[2]]
        for row in p:
            row['placement']={k:rot(v) for k,v in row['placement'].items()}
        r=check_assembly(p,parameters={'assembly_order':['beta','alpha']})
        self.assertTrue(r['ok'],r['look_again'])
        p[0]['placement']['v']=p[0]['placement']['u'][:]
        self.assertFalse(check_assembly(p)['ok'])

    def test_mates_connector_reference_alias_and_locked_repairs(self):
        from repair import repair_primitives
        p=connectors()
        for part in p:
            c=part['connectors'][0];mate=c.pop('mate_id');part['mates']=[{'connector_id':c['id'],'target_connector':mate}]
        prepared=prepare_parts(p)
        r=check_assembly(prepared,parameters={'assembly_order':['beta','alpha']})
        self.assertTrue(r['ok'],r['look_again'])
        new,actions=repair_primitives(p,{'canonical_mates':r['canonical_mates'],'look_again':['repair roof']})
        self.assertEqual(new,p);self.assertEqual(actions,[])

    def test_v18_geometry_unchanged_and_real_failures_remain_blocked(self):
        recipe=json.loads(Path('tests/fixtures/house_lamp_v18.json').read_text(encoding='utf-8'))
        before=deepcopy(recipe)
        built=render_toolbox(recipe['primitives'],recipe['parameters']);r=review_built(built)
        self.assertEqual(recipe,before)
        self.assertEqual(len(built['assembly']['physical_parts']),12)
        self.assertEqual(r['final_status'],'BLOCKED')
        self.assertFalse(any('PART_TRANSFORM' in x for x in r['look_again']))
        self.assertFalse(any('invalid orthonormal' in x for x in r['look_again']))
        self.assertEqual(r['scorecard']['digital']['Tab-Slot Geometry'],'FAIL')
        self.assertEqual(r['scorecard']['digital']['Collision'],'FAIL')
        self.assertIn('NON_COMPLEMENTARY_JOINT',str(r['look_again']))
        self.assertTrue(all(not p.get('connectors') for p in recipe['primitives']))

    def test_scale_keeps_insertion_axis_dimensionless(self):
        from scale import scale_primitives
        p=connectors();scaled,_=scale_primitives(p,{'scale':2})
        c=scaled[0]['connectors'][0]
        self.assertEqual(c['axis'],p[0]['connectors'][0]['axis'])
        self.assertEqual(c['position'],[23,44,3])
        self.assertEqual(c['width_mm'],48)
        self.assertTrue(check_assembly(scaled,thickness=6,parameters={'assembly_order':['beta','alpha']})['ok'])

    def test_invalid_solid_thickness_fails_closed(self):
        from solid_geometry import part_solid
        for t in (0,-1,float('nan')):
            with self.assertRaisesRegex(ValueError,'INVALID_SOLID_THICKNESS'):
                part_solid(connectors()[0],t)

    def test_malformed_connectors_block_instead_of_crashing(self):
        for bad in ([None],{'bad':'shape'}):
            p=connectors();p[0]['connectors']=bad
            result=check_assembly(p)
            self.assertFalse(result['ok'])
            self.assertIn('INVALID_CONNECTOR_SCHEMA',str(result['look_again']))
