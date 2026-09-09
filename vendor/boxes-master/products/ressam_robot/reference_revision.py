"""Reference-led cosmetic revision; preserve the audited drivetrain and original SVG."""
from generate import *

class ReferenceRobot(RessamRobot):
    expected_parts=24

    def define(self):
        super().define()
        for p in self.specs:
            if p['name'] in ('Head Front','Head Back','Head Left','Head Right'):p['h']=101
            if p['name'].startswith('Eye '):p['w']=p['h']=34
        self.features=[f for f in self.features if not(f['part']=='Head Front' and f['kind']=='smile')]
        for f in self.features:
            if f['part']=='Head Front' and f['kind']=='eye-bolt':f['y']=76
            if f['part']=='Head Back':
                if f['kind']=='battery-service-window':f['y']=63
                if f['kind']=='battery-strap':f['y']-=8
            if f['part'].startswith('Head ') and f['kind']=='service-tie' and f['y']==105:f['y']=91
            if f['part'].startswith('Eye ') and f['kind']=='pupil':f['w']=18
            if f['part'].startswith('Eye ') and f['kind']=='highlight':f.update(x=-4,y=4,w=3)
        self.panel('Rounded Face',120,109)
        for x in (36,84):self.hole_spec('Rounded Face','eye-bolt',x,76,3.2)
        self.hole_spec('Rounded Face','smile',60,51,24,12,True)

    def render(self):
        self.addPart(MountEdge(self,None));self.addPart(PenNotchEdge(self,None))
        for p in self.specs:
            self.current_name=p['name']
            if p['name']=='Rounded Face':
                # roundedPlate callback origin is at the beginning of its bottom straight, x=r.
                def callback():
                    with self.saved_context():
                        self.moveTo(-6,0)
                        self.draw_features()
                self.roundedPlate(120,109,6,edge='e',extend_corners=False,callback=[callback],move='up')
            elif p['disc']:self.parts.disc(p['w'],callback=self.draw_features,move='up')
            else:self.rectangularWall(p['w'],p['h'],p['edges'],callback=[self.draw_features],move='up')

def validate_reference_assembly(robot):
    features=robot.features
    front=sorted((13+f['x'],40+f['y'],f['w']) for f in features if f['part']=='Head Front' and f['kind']=='eye-bolt')
    face=sorted((5+f['x'],40+f['y'],f['w']) for f in features if f['part']=='Rounded Face' and f['kind']=='eye-bolt')
    require(front==face==[(41,116,3.2),(89,116,3.2)],'Face/eye attachment mismatch')
    minimum=999
    for i in range(1441):
        angle=i*math.tau/1440
        A=18+15j+12*complex(math.cos(angle),math.sin(angle));delta=112+15j-A;dd=abs(delta)
        aa=(84**2-30**2+dd**2)/(2*dd);B=A+delta/dd*complex(aa,-math.sqrt(84**2-aa**2));u=(B-A)/84
        beam=[A+u*complex(x-6,y-18) for x,y in [(0,0),(96,0),(96,24),(0,24)]]
        saddle=[A+u*complex(x,y) for x,y in [(22,-14.5),(62,-14.5),(62,-11.5),(22,-11.5)]]
        minimum=min(minimum,57-max(p.imag for p in beam+saddle))
    require(minimum>20,'Reference face intersects moving assembly')
    return dict(face_eye_registration_mm=face,face_foot_z_clearance_mm=0,
        face_minimum_moving_wood_gap_mm=minimum,sampled_positions=1441,
        limitations='Rigid nominal geometry; hardware and physical loading unresolved')

def main():
    robot=ReferenceRobot();motion=motion_check()
    robot.open();robot.render();joints=validate_joints(robot)
    raw=robot.close().getvalue();validate_closed(raw,robot)
    packed,layout=pack_sheet(raw,[(p['name'],) for p in robot.specs],1500,3000,cluster_width=360)
    validate_closed(packed,robot,True)
    final,bridges=add_bridges(packed,24);validation=validate_final(final,bridges,robot)
    # Face Y57..60, Z40..149; bottom rests at foot top, without entering its volume.
    assembly=validate_reference_assembly(robot)
    face_mounts=[]
    for x in (36,84):
        world=(5+x,116)
        require(world in [(41,116),(89,116)],'Face-to-eye registration')
        face_mounts.append(dict(world_xz_mm=world,hole_diameter_mm=3.2,stack_mm=9,fastener_length='UNRESOLVED'))
    report=dict(status='GEOMETRY_VALIDATED_PHYSICAL_PROTOTYPE_REQUIRED',geometry=validation,joints=joints,
        layout=layout,motion=motion,parts=robot.specs,features=robot.features,bridges=bridges,components=robot.catalog,
        revision=dict(assembly=assembly,head_external_mm=[110,35,104],face_mm=[120,109,3],face_radius_mm=6,
            overall_wood_height_mm=149,eye_diameter_mm=34,face_mounts=face_mounts,
            physical_limitations=['Actual marker unspecified','Pivot hardware dimensions and fastening unresolved',
            'Face/eye bolt length unresolved: 9 mm wood stack plus actual washers/nut allowance',
            'Motor load and pen contact require physical test','Kerf and thickness require coupon']))
    output=ROOT/'output/Payas_STEM_Ressam_Robot_REFERENCE_REV1.svg'
    output.with_suffix('.validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    output.write_bytes(final)
    print(json.dumps(dict(file=str(output),geometry=validation,layout=layout),indent=2))

if __name__=='__main__':main()
