import unittest

from assembly import check_assembly
from mechanism_validation import validate
from mechanisms import mechanism_type
from placement_solver import derive_placements
from seen import check_what_you_see
from toolbox import _materialize_cut_geometry
from road_roller_fixture import build_fixture


def rotating_part(label,kind='road_roller_drum',origin=None):
    return {'type':'disc','label':label,'d':40,'hole':4.15,'mechanism':{'type':kind,'rotating':True,'shaft':'axle-1'},'placement':{'origin':origin or [0,0,0],'u':[0,1,0],'v':[0,0,1]}}

def chassis():
    return {'type':'contour','label':'chassis','points':[[-50,-50],[50,-50],[50,50],[-50,50]],'placement':{'origin':[20,0,0],'u':[0,1,0],'v':[0,0,1]}}

def params(axis_origin=None):
    return {'hardware':[{'id':'axle-1','type':'shaft','diameter':4,'axis':[1,0,0],'origin':axis_origin or [0,0,0],'length':60}], 'connections':[{'type':'shaft_rotation','shaft':'axle-1','driven_part':'drum','hardware_clearance':.15,'required_length':50}]}


class RoadRollerTests(unittest.TestCase):
    def test_explicit_road_roller_classification_wins(self):
        p={'type':'disc','label':'rear rotor looking drum','mechanism':{'type':'road_roller_drum','rotating':True}}
        self.assertEqual(mechanism_type(p),'road_roller_drum')
        self.assertFalse(check_what_you_see([p],'road roller tambur ve teker'))

    def test_road_roller_without_shaft_fails(self):
        report=validate([rotating_part('drum'),chassis()],{},3)
        self.assertEqual(report['checks'][0]['reason'],'SHAFT_CONNECTION_MISSING')

    def test_road_roller_misaligned_shaft_fails_coaxiality(self):
        report=validate([rotating_part('drum'),chassis()],params([0,10,0]),3)
        self.assertEqual(report['checks'][0]['reason'],'COAXIALITY_FAIL')

    def test_wheel_with_correct_axle_passes(self):
        wheel=rotating_part('drum','wheel');report=validate([wheel,chassis()],params(),3)
        self.assertEqual(report['classifications'][0]['type'],'wheel')
        self.assertEqual(report['checks'][0]['status'],'PASS')

    def test_propeller_dispatch_remains_propeller(self):
        self.assertEqual(mechanism_type({'type':'propeller','label':'prop'}),'propeller')

    def test_static_disc_is_not_propeller_or_rotor(self):
        p={'type':'disc','label':'round decorative plate'}
        self.assertEqual(mechanism_type(p),'disc')

    def test_missing_placement_is_derived_from_one_anchored_mate(self):
        bridge=_materialize_cut_geometry({'type':'panel','label':'sasi-on-kopru','w':50,'h':22,'placement':{'origin':[0,0,10],'u':[1,0,0],'v':[0,1,0]},'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14}]})
        side=_materialize_cut_geometry({'type':'contour','label':'sasi-sol','points':[[0,0],[22,0],[22,30],[0,30]],'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'sasi-on-kopru','tab':'L'}}]})
        notes=derive_placements([bridge,side],3)
        self.assertTrue(side.get('placement'));self.assertEqual(side['placement']['source'],'constraint')
        self.assertTrue(any(n['status']=='DERIVED' for n in notes))
        report=check_assembly([bridge,side]);self.assertTrue(report['ok'],report['look_again'])

    def test_unanchored_constraints_are_ambiguous(self):
        bridge=_materialize_cut_geometry({'type':'panel','label':'bridge','w':50,'h':22,'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14}]})
        side=_materialize_cut_geometry({'type':'contour','label':'side','points':[[0,0],[22,0],[22,30],[0,30]],'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'bridge','tab':'L'}}]})
        notes=derive_placements([bridge,side],3)
        self.assertTrue(any(n['status']=='PLACEMENT_AMBIGUOUS' for n in notes))
        report=check_assembly([bridge,side]);self.assertFalse(report['ok']);self.assertTrue(any('PLACEMENT_AMBIGUOUS' in e for e in report['look_again']))

    def test_matching_names_with_different_world_positions_fail(self):
        bridge=_materialize_cut_geometry({'type':'panel','label':'bridge','w':50,'h':22,'placement':{'origin':[0,0,10],'u':[1,0,0],'v':[0,1,0]},'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14}]})
        side=_materialize_cut_geometry({'type':'contour','label':'side','points':[[0,0],[22,0],[22,30],[0,30]],'placement':{'origin':[100,0,0],'u':[0,1,0],'v':[0,0,1]},'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'bridge','tab':'L'}}]})
        report=check_assembly([bridge,side])
        self.assertFalse(report['ok']);self.assertEqual(report['tab_slot_pairs'],0)
        self.assertGreater(report['tab_slot_debug'][0]['center_delta_mm'],90)

    def test_matching_world_geometry_passes(self):
        bridge=_materialize_cut_geometry({'type':'panel','label':'bridge','w':50,'h':22,'placement':{'origin':[0,0,10],'u':[1,0,0],'v':[0,1,0]},'tabs':[{'id':'L','x':0,'y':11,'w':3,'h':14}]})
        side=_materialize_cut_geometry({'type':'contour','label':'side','points':[[0,0],[22,0],[22,30],[0,30]],'placement':{'origin':[-3,0,0],'u':[0,1,0],'v':[0,0,1]},'slots':[{'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'bridge','tab':'L'}}]})
        report=check_assembly([bridge,side])
        self.assertTrue(report['ok'],report['look_again']);self.assertEqual(report['tab_slot_pairs'],1)
        self.assertEqual(report['tab_slot_debug'][0]['result'],'PASS')

    def test_complete_road_roller_fixture(self):
        primitives,parameters=build_fixture();assembly=check_assembly(primitives);mechanics=validate(primitives,parameters,3)
        self.assertTrue(assembly['ok'],assembly['look_again']);self.assertEqual(assembly['tab_slot_pairs'],4)
        self.assertEqual({r['type'] for r in mechanics['classifications']},{'wheel','road_roller_drum','disc'})
        moving=[r for r in mechanics['checks'] if r['type'] in {'wheel','road_roller_drum'}]
        self.assertEqual(len(moving),4);self.assertTrue(all(r['status']=='PASS' for r in moving),moving)


if __name__=='__main__':unittest.main()
