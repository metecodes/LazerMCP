"""Partitioned coin bank: catalog apertures, sourced battery envelope, unresolved sensor explicit."""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from products.robot_bank.generate import RobotBank,RailTabs,validate_assembly,engravings,local_shapes,validate_outside_faces
from products.ressam_robot.generate import validate_closed,validate_final,add_bridges,require,NS,polygon,parse_path
from boxes import edges
from boxes.stem_layout import pack_sheet
from xml.etree import ElementTree as ET
from shapely.geometry import LineString,box

class PartitionTabs(edges.BaseEdge):
 char='Q'
 def margin(self):return 3
 def __call__(self,length,**kw):
  last=0
  for center in (25,117):
   self.edge(center-3-last);self.polyline(0,-90,3,90,6,90,3,-90);last=center+3
  self.edge(length-last)

class ShelfTabs(PartitionTabs):
 char='U'
 def __call__(self,length,**kw):
  last=0
  for center in (12,54):
   self.edge(center-3-last);self.polyline(0,-90,3,90,6,90,3,-90);last=center+3
  self.edge(length-last)

class ElectronicBank(RobotBank):
 expected_parts=17
 electronic_revision=True
 def define(self):
  super().define();self.electronics=json.loads((Path(__file__).parent/'electronics_components.json').read_text())
  for x,y in [(33,101),(81,101),(57,43)]:self.hole_spec('Bank Front','led',x,y,self.electronics['led']['cutout_diameter_mm'])
  self.hole_spec('Bank Front','switch',57,126,*self.electronics['switch']['cutout_mm'])
  for x in (7,107):self.hole_spec('Bank Front','front-service-tie',x,136,3.2,5)
  for name in ('Bank Left','Bank Right'):
   left=name=='Bank Left'
   for z in (40,132):self.hole_spec(name,'partition-slot',51.5 if left else 27.5,z-15,3,6)
   self.hole_spec(name,'front-service-tie',73 if left else 6,136,3.2,5)
  self.panel('Divider',120,142)
  for x in (44,110):
   for z in (28,60):self.hole_spec('Divider','battery-strap',x,z-15,3.2,6)
  for x in (56,98):self.hole_spec('Divider','shelf-slot',x,3.5,6,3)
  self.panel('Battery Shelf',66,23)
 def render(self):
  self.addPart(RailTabs(self,None));self.addPart(PartitionTabs(self,None));self.addPart(ShelfTabs(self,None))
  for p in self.specs:
   self.current_name=p['name']
   if p['name']=='Divider':
    def cb():
     with self.saved_context():self.moveTo(-3,0);self.draw_features()
    self.rectangularWall(114,142,'eQeQ',callback=[cb],move='up')
   elif p['name']=='Battery Shelf':self.rectangularWall(66,20,'eeUe',move='up')
   elif p['name'].startswith('Arm') or p['name']=='Rear Cover':
    radius=6 if p['name'].startswith('Arm') else 3
    def cb(r=radius):
     with self.saved_context():self.moveTo(-r,0);self.draw_features()
    self.roundedPlate(p['w'],p['h'],radius,edge='e',extend_corners=False,callback=[cb],move='up')
   else:self.rectangularWall(p['w'],p['h'],p['edges'],callback=[self.draw_features],move='up')

def verify_electronics(b,packed):
 s=local_shapes(packed,b);pairs=[]
 def segments(shape,line,axis):
  cut=shape.intersection(line);geoms=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
  return sorted((q.centroid.coords[0][axis],q.length) for q in geoms if q.length>1e-6)
 for x,name in [(1.5,'Bank Left'),(118.5,'Bank Right')]:
  teeth=segments(s['Divider']['local'],LineString([(x,0),(x,142)]),1)
  require(len(teeth)==2 and all(abs(c-z)<.005 and abs(w-6.15)<.005 for (c,w),z in zip(teeth,(25,117))),'Divider tab profile mismatch')
  for z in (40,132):
   matches=[f for f in b.features if f['part']==name and f['kind']=='partition-slot' and f['y']+15==z and f['x']==(51.5 if name=='Bank Left' else 27.5)]
   require(len(matches)==1 and (matches[0]['w'],matches[0]['h'])==(3,6),'Divider slot mismatch')
   pairs.append(dict(male='Divider',female=name,center_xyz_mm=[x,30.5,z],tab_mm=[6,3],slot_mm=[6,3],nominal_clearance_mm=0))
 teeth=segments(s['Battery Shelf']['local'],LineString([(0,21.5),(66,21.5)]),0)
 require(len(teeth)==2 and all(abs(c-z)<.005 and abs(w-6.15)<.005 for (c,w),z in zip(teeth,(12,54))),'Shelf tab profile mismatch')
 for x in (56,98):
  f=next(f for f in b.features if f['part']=='Divider' and f['kind']=='shelf-slot' and f['x']==x)
  require((f['y'],f['w'],f['h'])==(3.5,6,3),'Shelf registration mismatch')
  pairs.append(dict(male='Battery Shelf',female='Divider',center_xyz_mm=[x,30.5,18.5],tab_mm=[6,3],slot_mm=[6,3],nominal_clearance_mm=0))
 slot=next(f for f in b.features if f['kind']=='coin-slot')
 require(slot['y']+3-slot['h']/2>32,'Coin slot feeds electronics cavity')
 # Real battery envelope from catalog, orientation width X / thickness Y / height Z.
 bw,bh,bd=b.electronics['battery_holder']['envelope_mm']
 battery=[48,29-bd,20,48+bw,29,20+bh]
 require(battery[0]>=44 and battery[3]<=110 and battery[1]>=9 and battery[4]<=29,'Battery overhangs shelf')
 require(battery[1]-3>=10 and battery[5]<157,'Battery intersects front or roof')
 require(3<29<32<82,'Partition clearances invalid')
 # Strap slots are outside the holder's X envelope; the selected holder is not drilled.
 require(44+1.6<48 and 110-1.6>48+bw,'Strap slots under battery edges')
 return dict(additional_tab_slot_pairs=pairs,partition_xyz_mm=[3,29,15,117,32,157],
  electronics_cavity_mm=[114,26,142],coin_cavity_mm=[114,50,142],battery_envelope_xyz_mm=battery,
  battery_front_clearance_mm=battery[1]-3,battery_holder=b.electronics['battery_holder'],
  service='Release two front corner ties and pull front outward; electronics accessible from front. Rear cover accesses coins only.',
  led_apertures_mm=[5,5,5],switch_aperture_mm=[13,19],
  status='MECHANICAL_GEOMETRY_PASS_ELECTRICAL_OPERATION_UNVERIFIED',
  unresolved=['LED flange, retention and insulated lead envelope','Switch body depth, flange and 3mm clip suitability','Coin sensor, circuit and trigger behaviour','Actual strap and wire clearances','Physical loaded fit and strength'])

def build():
 b=ElectronicBank();b.open();b.render();raw=b.close().getvalue();validate_closed(raw,b)
 packed,layout=pack_sheet(raw,[(p['name'],) for p in b.specs],1500,3000,cluster_width=390)
 validate_closed(packed,b,True);assembly=validate_assembly(b,packed);electronic=verify_electronics(b,packed);art=engravings(b,packed)
 final,bridges=add_bridges(packed,17);root=ET.fromstring(final)
 for rec in art:ET.SubElement(root.find(NS+"g[@id='ENGRAVE']"),NS+'path',{'d':rec['d'],'data-panel':rec['part'],'fill':'none','stroke':'#000000','stroke-width':'0.15'})
 for p in root.iter(NS+'path'):p.set('stroke','#000000')
 final=ET.tostring(root,encoding='utf-8',xml_declaration=True);geometry=validate_final(final,bridges,b)
 assembly['limits']=[s for s in assembly['limits'] if not s.startswith('Passive coin bank')]+['Electronic operation and actual LED/switch retention not verified']
 report=dict(status='ELECTRONICS_ENCLOSURE_PROTOTYPE',geometry=geometry,assembly=assembly,electronic_assembly=electronic,layout=layout,parts=b.specs,features=b.features,mount_records=b.mount_records,bridges=bridges,engravings=art,components=b.electronics,orientation_checks=validate_outside_faces())
 return final,report,b

if __name__=='__main__':
 data,report,b=build();out=ROOT/'output/Payas_STEM_Robot_Kumbara_ELEKTRONIK_REV2.svg'
 out.write_bytes(data);out.with_suffix('.validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({'file':str(out),'geometry':report['geometry'],'layout':report['layout'],'electronics':report['electronic_assembly']},indent=2))
