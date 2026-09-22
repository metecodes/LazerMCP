import unittest
from copy import deepcopy
from shapely.geometry import box
from toolbox import _materialize_cut_geometry,render_toolbox
from structural_mates import infer_structural_mates
from assembly import check_assembly
from connection_validation import validate
from review import review_built
from tests.legacy_contour_fixture import legacy_house


def pair():
    a=box(0,0,10,44).union(box(10,10,13,34))
    b=box(0,0,44,20).difference(box(10,0,34,3))
    def part(name,shape,origin,u,v):
        return _materialize_cut_geometry({'type':'contour','label':name,'role':'structural','points':list(shape.exterior.coords)[:-1], 'placement':{'origin':origin,'u':u,'v':v}})
    return [part('alpha',a,[0,0,0],[1,0,0],[0,1,0]),part('beta',b,[10,0,0],[0,1,0],[0,0,1])]


class StructuralMateTests(unittest.TestCase):
    def test_legacy_house_eight_edges_no_input_mutation(self):
        for t in (2.7,3):
            parts=legacy_house(t);original=deepcopy(parts)
            result=check_assembly(parts,t)
            self.assertTrue(result['ok'],result['look_again'])
            inf=result['structural_inference']
            self.assertEqual(len(inf['joints']),8)
            self.assertEqual(parts,original)
            cov=validate(parts,{},result,{})
            self.assertEqual(len(cov['connection_graph']),8)
            self.assertEqual(result['connection_graph_summary']['connected_components'],1)
            self.assertEqual(cov['coverage_percent'],100)
            for pid,mates in inf['reciprocal_mates'].items():
                for m in mates:self.assertIn(pid,[r['part'] for r in inf['reciprocal_mates'][m['part']]])
            self.assertTrue(result['assembled_preview_svg'])

    def test_outer_contour_tab_recess_without_slot_metadata(self):
        self.assertEqual(len(infer_structural_mates(pair())['joints']),1)

    def test_names_are_not_evidence(self):
        parts=pair()
        for i,p in enumerate(parts):p['label']=str(i*173)
        self.assertEqual(len(infer_structural_mates(parts)['joints']),1)

    def test_plain_placed_parts_do_not_mate(self):
        parts=pair()
        for p in parts:p['_cut_geometry']['outer_cut']['points']=[[0,0],[10,0],[10,44],[0,44]]
        self.assertEqual(infer_structural_mates(parts)['joints'],[])

    def test_misalignment_and_material_mismatch(self):
        for mode in ('offset','thickness','depth'):
            parts=pair()
            if mode=='offset':parts[1]['placement']['origin'][1]+=.2
            elif mode=='thickness':parts[1]['thickness']=2.7
            else:
                for pt in parts[0]['_cut_geometry']['outer_cut']['points']:
                    if pt[0]==13:pt[0]=14
            self.assertEqual(infer_structural_mates(parts)['joints'],[],mode)

    def test_collision_rejects_apparent_joint(self):
        parts=pair()
        shape=box(0,0,10,44).union(box(10,10,13,34)).union(box(9,38,12,42))
        parts[0]['_cut_geometry']['outer_cut']['points']=list(shape.exterior.coords)[:-1]
        result=infer_structural_mates(parts)
        self.assertFalse(result['joints'])
        self.assertTrue(any(x['code']=='INTERLOCK_COLLISION' for x in result['rejected_candidates']))

    def test_explicit_preserved_and_nonreciprocal_fails(self):
        parts=pair();parts[0]['mates']=[{'part':'beta','custom':'keep'}]
        self.assertIn('NON_RECIPROCAL',str(infer_structural_mates(parts)['errors']))
        parts[1]['mates']=[{'part':'alpha'}]
        result=infer_structural_mates(parts,existing_joints=[{'male':'alpha','female':'beta','result':'MATCH'}])
        self.assertEqual(result['joints'],[])
        self.assertEqual(result['reciprocal_mates']['alpha'],parts[0]['mates'])
        self.assertFalse(result['errors'])

    def test_ambiguous_feature_never_passes(self):
        parts=pair();clone=deepcopy(parts[1]);clone['label']='third';parts.append(clone)
        result=infer_structural_mates(parts)
        self.assertFalse(result['joints']);self.assertTrue(result['errors'])

    def test_disconnected_coverage_blocks(self):
        parts=legacy_house();extra=deepcopy(parts[0]);extra['label']='isolated';extra['placement']['origin'][0]+=500;parts.append(extra)
        result=check_assembly(parts);cov=validate(parts,{},result,{})
        self.assertTrue(any(c['status']=='FAIL' for c in cov['checks']))
        self.assertEqual(result['connection_graph_summary']['connected_components'],2)

    def test_full_reviewer_and_existing_workflows(self):
        built=render_toolbox(legacy_house(),{'holding_nicks':False,'surface_texts':[],'thickness':3,'machine':'desktop_400'})
        result=review_built(built)
        self.assertEqual(result['final_status'],'PROTOTYPE READY',result['look_again'])
        for key in ('Connections','Assembly','3D Assembly'):
            self.assertEqual(result['scorecard']['digital'][key],'PASS')
        self.assertTrue(all(p['mates'] for p in result['design_map']['parts']))
        from house_holder import recipe
        explicit=check_assembly(recipe(),3)
        self.assertTrue(explicit['ok'],explicit['look_again']);self.assertEqual(explicit['tab_slot_pairs'],11)
        box_result=check_assembly([{'type':'box','label':'b','x':96,'y':115,'h':40,'bottom':True}],3)
        self.assertTrue(box_result['ok'],box_result['look_again'])

