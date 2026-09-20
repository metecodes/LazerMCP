"""Deterministic road-roller regression assembly used by validator tests."""
from __future__ import annotations

from toolbox import _materialize_cut_geometry


def build_fixture():
    tabs=lambda:[{'id':'L','x':0,'y':11,'w':3,'h':14},{'id':'R','x':50,'y':11,'w':3,'h':14}]
    front=_materialize_cut_geometry({'type':'panel','label':'front chassis bridge','w':50,'h':22,'placement':{'origin':[0,0,10],'u':[1,0,0],'v':[0,1,0]},'tabs':tabs()})
    rear=_materialize_cut_geometry({'type':'panel','label':'rear chassis bridge','w':50,'h':22,'placement':{'origin':[0,0,40],'u':[1,0,0],'v':[0,1,0]},'tabs':tabs()})
    def side(label,origin):
        return _materialize_cut_geometry({'type':'contour','label':label,'points':[[0,0],[22,0],[22,60],[0,60]],'placement':{'origin':origin,'u':[0,1,0],'v':[0,0,1]},'slots':[
            {'x':11,'y':11.5,'w':14,'h':3.15,'mate':{'part':'front chassis bridge','tab':'L' if label=='left chassis' else 'R'}},
            {'x':11,'y':41.5,'w':14,'h':3.15,'mate':{'part':'rear chassis bridge','tab':'L' if label=='left chassis' else 'R'}}]})
    static=[side('left chassis',[-3,0,0]),side('right chassis',[50,0,0]),front,rear,
            {'type':'panel','label':'cabin','w':30,'h':45,'placement':{'origin':[20,100,80],'u':[1,0,0],'v':[0,0,1]}},
            {'type':'disc','label':'left drum bearing','d':10,'hole':4.15,'placement':{'origin':[-5,80,25],'u':[0,1,0],'v':[0,0,1]}},
            {'type':'disc','label':'right drum bearing','d':10,'hole':4.15,'placement':{'origin':[55,80,25],'u':[0,1,0],'v':[0,0,1]}},
            {'type':'panel','label':'drum slats','w':60,'h':8,'placement':{'origin':[0,75,45],'u':[1,0,0],'v':[0,1,0]}}]
    rotating=[]
    for label,kind,center,shaft,dia in [
        ('left front wheel','wheel',[-8,20,22],'front axle',40),('right front wheel','wheel',[58,20,22],'front axle',40),
        ('left drum end cap','road_roller_drum',[-8,80,25],'rear drum axle',46),('right drum end cap','road_roller_drum',[58,80,25],'rear drum axle',46)]:
        rotating.append({'type':'disc','label':label,'d':dia,'hole':4.15,'mechanism':{'type':kind,'rotating':True,'shaft':shaft},'placement':{'origin':center,'u':[0,1,0],'v':[0,0,1]}})
    primitives=static+rotating
    allowed=[str(p.get('label')) for p in primitives if p.get('label')!='cabin']
    parameters={'project':'yol-silindiri-sasi-gecme-v3-reconstructed','hardware_clearance':.15,'hardware':[
        {'id':'front axle','type':'shaft','diameter':4,'axis':[1,0,0],'origin':[0,20,22],'length':75},
        {'id':'rear drum axle','type':'shaft','diameter':4,'axis':[1,0,0],'origin':[0,80,25],'length':75}], 'connections':[]}
    for part in rotating:
        parameters['connections'].append({'type':'shaft_rotation','shaft':part['mechanism']['shaft'],'driven_part':part['label'],'hardware_clearance':.15,'required_length':70,'allowed_contact_parts':allowed})
    return primitives,parameters
