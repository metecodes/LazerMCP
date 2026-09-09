"""Reference-style 15-part robot bank, rendered entirely through Boxes.py."""
from boxes import Boxes, Color, edges
from hayal_kumbaram import HayalKumbaram

class FootTabs(edges.BaseEdge):
    char='a'
    def __call__(self,length,**kw):
        # Symmetric 6 mm tenons at 25 and 69 mm on a 94 mm foot cheek.
        for v in (22,38):
            self.edge(v,tabs=1)
            self.corner(-90);self.edge(self.thickness);self.corner(90)
            self.edge(6);self.corner(90);self.edge(self.thickness);self.corner(-90)
        self.edge(22,tabs=1)
    def margin(self):return self.thickness

class PayasRobot(HayalKumbaram):
    description='Reference-style robot bank: six finger-jointed faces, rear service door, arms and feet.'
    def __init__(self):
        super().__init__()
        self.argparser.set_defaults(x=120,y=100,h=180,labels=False)
    def caption(self,s,x,y,size=5):
        with self.saved_context():
            self.text(s,x,y,fontsize=size,align='center',color=Color.ETCHING)
    def art(self,fn):
        with self.saved_context():
            self.set_source_color(Color.ETCHING);fn()
    def face(self):
        w,h=self.x,self.h
        for x in (w*.28,w*.72):self.hole(x,h*.70,d=5.2)
        self.hole(w/2,h*.30,d=5.2)
        def draw():
            for x in (w*.28,w*.72):self.ring(x,h*.70,14);self.ring(x,h*.70,10)
            self.bezier((w*.33,h*.53),(w*.43,h*.44,w*.57,h*.44,w*.67,h*.53),
                (w*.64,h*.38,w*.36,h*.38,w*.33,h*.53))
            self.heart(w/2,h*.30,1.2)
            for x,sg in ((17,1),(w-17,-1)):
                for y in (h*.88,h*.39):self.ring(x,y,2.5)
                self.line((x,h*.855),(x,h*.82),(x-10*sg,h*.79),(x-14*sg,h*.79))
                self.line((x,h*.365),(x+8*sg,h*.34),(x+8*sg,h*.30))
                for yy in (h*.30,h*.27,h*.24):self.line((x-3,yy),(x+5,yy))
        self.art(draw);self.caption('DENE YAP',w/2,h*.13,6)
    def rear(self):
        w,h=self.x,self.h
        self.rectangularHole(w/2,44,64,50,r=1)
        for x in (w/2-39,w/2+39):self.hole(x,44,d=3.2)
        self.caption('PAYAS STEM',w/2,h*.84,7)
        self.caption('Geleceği Kurgular',w/2,h*.65,3.5)
        def emblem():
            self.line((14,h*.82),(10,h*.82),(13,h*.89),(10,h*.94),(w-10,h*.94),(w-13,h*.89),(w-10,h*.82),(w-14,h*.82))
            self.line((w/2-17,h*.69),(w/2,h*.71),(w/2+17,h*.69))
            self.line((w/2-17,h*.69),(w/2-14,h*.75),(w/2,h*.73),(w/2+14,h*.75),(w/2+17,h*.69))
        self.art(emblem)
    def side(self,bicycle=False):
        w,h=self.y,self.h
        for yy in (72,104):self.hole(w/2,yy,d=3.2)
        if bicycle:
            self.caption('HAYALİM',w/2,h*.59,6)
            self.caption('BİSİKLET',w/2,h*.52,5)
            def draw():
                for x in (25,w-25):self.ring(x,28,14)
                self.line((25,28),(39,51),(w-25,28),(25,28),(39,51),(w-29,51),(w-25,28))
                self.line((w-25,28),(w-29,58),(w-35,58));self.line((34,53),(43,53))
                self.line((w/2-9,h*.76),(w/2-6,h*.88),(w/2+5,h*.93),(w/2+11,h*.87),(w/2+8,h*.76),(w/2,h*.79),(w/2-9,h*.76))
                self.ring(w/2+2,h*.86,3)
            self.art(draw)
        else:
            self.caption('BU KUMBARA',w/2,h*.74,5)
            self.caption('BENİM HAYALİM',w/2,h*.66,4)
            self.caption('BİRİKTİR',w/2,h*.33,6)
            self.art(lambda:self.line((20,h*.58),(w-12,h*.58)))
    def roof(self):
        self.rectangularHole(self.x/2,self.y*.48,36,4)
        self.caption('HAYALİNE YAKLAŞ',self.x/2,self.y*.74,5)
        self.art(lambda:[self.ring(20+i*(self.x-40)/8,20,2) for i in range(9)])
    def floor(self):
        for x in (16,40,self.x-40,self.x-16):
            for y in (25,69):self.rectangularHole(x,y,3,6)
    def door(self):
        for x in (3,81):self.hole(x,36,d=3.2)
        self.caption('PARA KAPAĞI',42,54,5)
        self.caption('DENE YAP',42,18,5)
    def arm(self):
        # RoundedPlate's callback origin is radius mm right of its lower-left.
        for yy in (18,50):self.hole(30-5,yy,d=3.2)
        self.art(lambda:self.ring(12-5,35,8))
        self.art(lambda:[self.line((x-5,55),(x-5,63)) for x in (9,14,19)])
    def render(self):
        if self.output_selection=='coupon':return super().render()
        if (self.x,self.y,self.h,self.thickness)!=(120,100,180,3):
            raise ValueError('This reference layout requires 120x100x180 and 3 mm; foot geometry is fixed.')
        self.x=self.adjustSize(self.x);self.y=self.adjustSize(self.y);self.h=self.adjustSize(self.h)
        self.addPart(FootTabs(self,None))
        # Deterministic compact nesting. Every part still uses Boxes.py walls.
        def panel(px,py,w,h,edge,cb=None,rounding=0):
            with self.saved_context():
                self.moveTo(px,py)
                if rounding:
                    Boxes.roundedPlate(self,w,h,rounding,edge='e',extend_corners=False,callback=[cb] if cb else None)
                else:
                    Boxes.rectangularWall(self,w,h,edge,callback=[cb] if cb else None)
        panel(0,218,self.x,self.h,'FFFF',self.rear)
        panel(128,218,self.x,self.h,'FFFF',self.face)
        panel(256,218,self.y,self.h,'FfFf',self.side)
        panel(0,108,self.x,self.y,'ffff',self.roof)
        panel(0,0,self.x,self.y,'ffff',self.floor)
        panel(128,24,self.y,self.h,'FfFf',lambda:self.side(True))
        panel(232,130,84,72,'eeee',self.door)
        panel(364,320,44,70,'eeee',self.arm,5)
        panel(364,240,44,70,'eeee',self.arm,5)
        for y in (106,82,58,34):panel(232,y,94,12,['e','e','a','e'])
        # Crosspieces brace the two cheeks of each foot, glued between them.
        for x in (336,374):panel(x,195,21,12,'eeee')


