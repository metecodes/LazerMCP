import unittest
from copy import deepcopy

from assembly import check_assembly
from bom import build_bom
from house_holder import recipe
from review import connection_graph
from toolbox import compile_toolbox
from toolbox import render_toolbox


def helicopter_recipe():
    parts=recipe()
    front,back,left,right,floor,divider,star=parts
    left['slots']=[];right['slots']=[]
    floor['tabs']=[t for t in floor['tabs'] if t['id'] in {'front','back'}];floor['slots']=[];floor['label']='motor-mount'
    divider['tabs']=[t for t in divider['tabs'] if t['id'] in {'front','back'}];divider['label']='battery-mount'
    for body in (front,back):
        for slot in body['slots']:
            mate=slot.get('mate') or {}
            if mate.get('part')=='floor':mate['part']='motor-mount'
            if mate.get('part')=='divider':mate['part']='battery-mount'
    left['label']='cross-brace-left';right['label']='cross-brace-right'
    for body in (front,back):
        for slot in body['slots']:
            mate=slot.get('mate') or {}
            if mate.get('part')=='left-side':mate['part']='cross-brace-left'
            if mate.get('part')=='right-side':mate['part']='cross-brace-right'
    star['label']='skid-left';star.pop('attachment',None)
    skid2=deepcopy(star);skid2['label']='skid-right';skid2['placement']={'origin':[0,90,0],'u':[1,0,0],'v':[0,0,1]}
    prop={'type':'propeller','label':'ust-pervane','blades':2,'d':30,'hole':2,'drive_type':'direct_motor_shaft','placement':{'origin':[200,200,200],'u':[1,0,0],'v':[0,1,0]},'drive':{'type':'direct_motor_shaft','hardware':'motor-1'}}
    return [front,back,left,right,floor,divider,star,skid2,prop]


class MechanicalRegressionTests(unittest.TestCase):
    def test_left_and_right_edge_tabs_compile_and_align_in_world_space(self):
        bridge={'type':'panel','label':'on-kopru','w':50,'h':22,'placement':{'origin':[0,0,10],'u':[1,0,0],'v':[0,1,0]},'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14},{'id':'R','x':50,'y':11,'w':3,'h':14}]}
        left={'type':'contour','label':'govde-sol','points':[[0,0],[22,0],[22,30],[0,30]],'placement':{'origin':[-3,0,0],'u':[0,1,0],'v':[0,0,1]},'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'on-kopru','tab':'L'}}]}
        right={'type':'contour','label':'govde-sag','points':[[0,0],[22,0],[22,30],[0,30]],'placement':{'origin':[50,0,0],'u':[0,1,0],'v':[0,0,1]},'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'on-kopru','tab':'R'}}]}
        report=check_assembly([bridge,left,right])
        self.assertTrue(report['ok'],report['look_again'])
        self.assertEqual(report['tab_slot_pairs'],2)
        self.assertEqual([row['result'] for row in report['tab_slot_debug']],['PASS','PASS'])
        from toolbox import _materialize_cut_geometry
        compiled=_materialize_cut_geometry(bridge)
        self.assertEqual([round(t['x'],3) for t in compiled['tabs']],[-1.5,51.5])
        self.assertTrue(all(t['materialized'] for t in compiled['_cut_geometry']['tabs']))

    def test_compiler_emits_tab_outer_cut_and_slot_inner_cut(self):
        panel={'type':'panel','label':'panel-a','w':50,'h':22,'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14}],'slots':[{'x':25,'y':11,'w':14,'h':3.15}]}
        built=render_toolbox([panel],{})
        compiled=built['primitives'][0]
        self.assertLess(min(x for x,y in compiled['points']),0)
        self.assertTrue(compiled['_cut_geometry']['tabs'][0]['materialized'])
        self.assertEqual(compiled['_cut_geometry']['inner_cuts'][0]['role'],'SLOT')
        self.assertEqual(compiled['_cut_geometry']['inner_cuts'][0]['operation'],'CUT')
        from manufacturing import iter_drawables
        rows=iter_drawables(built['svg_bytes'])
        self.assertTrue(any(row.get('semantic_role') in {'slot','inner_cutout'} and row.get('operation')=='CUT' for row in rows))

    def test_wrong_world_orientation_fails(self):
        parts=recipe();parts[2]['placement']={'origin':[3,3,0],'u':[1,0,0],'v':[0,0,1]}
        report=check_assembly(parts)
        self.assertFalse(report['ok'])
        self.assertTrue(any('does not align' in e for e in report['look_again']))

    def test_joint_debug_reports_geometric_metrics(self):
        report=check_assembly(recipe())
        self.assertEqual(len(report['tab_slot_debug']),11)
        row=report['tab_slot_debug'][0]
        for key in ('tab_local_bbox','tab_world_bbox','slot_local_bbox','slot_world_bbox','center_distance_mm','angular_error_deg','thickness_clearance_mm','insertion_depth_mm','result','reason'):
            self.assertIn(key,row)

    def test_direct_motor_has_no_self_connection_and_no_dowel(self):
        parts=helicopter_recipe();params={'hardware':[{'id':'motor-1','type':'dc_motor','shaft_diameter':2,'shaft_axis':[0,0,1],'shaft_origin':[200,200,190]}]}
        assembly=check_assembly(parts)
        graph=connection_graph(assembly,[],params)
        self.assertFalse(any(c['a_name']==c['b_name'] for c in graph))
        bom=build_bom(primitives=parts,parameters=params)
        self.assertFalse(any('dowel' in row['item'].lower() or 'mil /' in row['item'].lower() for row in bom['lines']))

    def test_valid_helicopter_has_eight_geometric_mates_and_preview(self):
        parts=helicopter_recipe()
        report=check_assembly(parts)
        self.assertTrue(report['ok'],report['look_again'])
        self.assertEqual(report['tab_slot_pairs'],8)
        self.assertEqual(sum(d['result']=='PASS' for d in report['tab_slot_debug']),8)
        self.assertTrue(report['assembled_preview_svg'])

    def test_direct_motor_end_to_end_gate(self):
        parts=helicopter_recipe()
        params={
            'hardware':[{'id':'motor-1','type':'dc_motor','shaft_diameter':2,'shaft_axis':[0,0,1],'shaft_origin':[200,200,190]}],
            'connections':[{'type':'direct_motor_shaft','motor_part':'motor-1','driven_part':'ust-pervane','shaft_axis':{'origin':[200,200,190],'direction':[0,0,1]},'driven_center':[200,200,200],'radius_mm':15,'clearance_mm':1}],
            'assembly_order':[p['label'] for p in parts],
        }
        built=compile_toolbox(parts,params)
        review=built['review']
        self.assertEqual(built['assembly']['tab_slot_pairs'],8)
        self.assertEqual(review['categories']['TAB_SLOT_GEOMETRY']['status'],'PASS')
        self.assertEqual(review['categories']['3D_ASSEMBLY']['status'],'PASS')
        self.assertEqual(review['categories']['HARDWARE_FIT']['status'],'PASS')
        self.assertEqual(review['categories']['MOTION_CLEARANCE']['status'],'PASS')
        self.assertFalse(any(c['a_name']==c['b_name'] for c in review['connections']))
        self.assertIsNotNone(built['assembly']['assembled_preview_svg'])
        self.assertEqual(review['physical']['kerf'],'NOT_VERIFIED')
        self.assertEqual(review['physical']['assembly'],'NOT_VERIFIED')
        self.assertEqual(review['physical']['movement'],'NOT_VERIFIED')
        self.assertEqual(review['production_export'],'BLOCKED')


if __name__=='__main__':unittest.main()
