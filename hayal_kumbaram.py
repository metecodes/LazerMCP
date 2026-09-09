"""Hayal Kumbaram: all manufacturing geometry rendered by Boxes.py.

Uses UniversalBox's proven finger and slide-lid edge pairs unchanged.
Artwork is drawn in Boxes.py's drawing context, never patched into SVG.
"""
import math
from boxes import Color
from boxes.generators.universalbox import UniversalBox


class HayalKumbaram(UniversalBox):
    ui_group = 'Box'
    description = 'Finger-jointed LED money box with sliding service lid and three interchangeable engraved faces.'

    def __init__(self):
        super().__init__()
        self.argparser.set_defaults(x=120, y=100, h=180, outside=True,
            thickness=3, burn=.15, tabs=.8, top_edge='L', bottom_edge='h',
            labels=False, reference=0, SlideOnLid_spring='none')
        self.argparser.add_argument('--output_selection', choices=['all','body','faces','coupon'], default='all')

    def line(self, *pts):
        self.ctx.move_to(*pts[0])
        for p in pts[1:]: self.ctx.line_to(*p)
        self.ctx.stroke()

    def bezier(self, start, *segments):
        self.ctx.move_to(*start)
        for s in segments:self.ctx.curve_to(*s)
        self.ctx.stroke()

    def ring(self, x,y,r):
        self.ctx.move_to(x+r,y)
        for i in range(4):self.ctx.arc(x,y,r,i*math.pi/2,(i+1)*math.pi/2)
        self.ctx.stroke()

    def star(self,x,y,r):
        pts=[(x+math.cos(math.pi/2+i*math.pi/5)*(r if i%2==0 else r*.43),
              y+math.sin(math.pi/2+i*math.pi/5)*(r if i%2==0 else r*.43)) for i in range(10)]
        self.line(*pts,pts[0])

    def heart(self,x,y,s=1):
        with self.saved_context():
            self.ctx.translate(x,y);self.ctx.scale(s,s)
            self.bezier((0,-7),(-20,4,-8,17,0,8),(8,17,20,4,0,-7))

    def mounts(self,w,h):
        for x in (9,w-9):
            for y in (12,h-12):self.hole(x,y,d=3.2)

    def led_holes(self,w,h):
        for x,y in ((w*.32,h*.69),(w*.68,h*.69),(w*.5,h*.32)):
            self.hole(x,y,d=5.2)

    def front(self):
        self.mounts(self.x,self.h);self.led_holes(self.x,self.h)

    def lid_art(self):
        self.rectangularHole(self.x/2,self.y*.52,40,4,r=1)
        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            for i in range(9):self.ring(self.x/2-32+i*8, self.y*.28,2.4)
            self.star(self.x/2+43,self.y*.28,3.4)

    def side_art(self):
        w,h=self.y,self.h
        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            # Bicycle, drawn with clean continuous strokes.
            for x in (w*.27,w*.73):self.ring(x,h*.24,13)
            self.line((w*.27,h*.24),(w*.4,h*.40),(w*.59,h*.24),(w*.27,h*.24))
            self.line((w*.4,h*.40),(w*.64,h*.40),(w*.59,h*.24),(w*.73,h*.24),(w*.64,h*.46),(w*.7,h*.48))
            self.line((w*.35,h*.42),(w*.46,h*.42))
            self.line((w*.2,h*.6),(w*.8,h*.6));self.line((w*.25,h*.55),(w*.75,h*.55))
            self.star(w*.3,h*.79,6);self.star(w*.7,h*.85,4)
            self.bezier((w*.42,h*.74),(w*.67,h*.78,w*.54,h*.95,w*.4,h*.87))

    def rectangularWall(self,x,y,edges='eeee',**kw):
        # UniversalBox calls this method for its established mating geometry.
        label=kw.get('label','')
        if label=='front':kw['callback']=[self.front]
        elif label in ('left','right'):kw['callback']=[self.side_art]
        elif label=='lid top':kw['callback']=[self.lid_art]
        return super().rectangularWall(x,y,edges,**kw)

    def artwork(self,theme,w,h):
        self.mounts(w,h);self.led_holes(w,h)
        with self.saved_context():
            self.set_source_color(Color.ETCHING)
            # Artwork coordinates 100 x 150, y points upward.
            self.ctx.scale(w/100,h/150)
            if theme=='Robot':
                self.line((12,118),(12,137),(22,143),(78,143),(88,137),(88,118))
                self.line((10,93),(10,82),(28,69),(72,69),(90,82),(90,93))
                for x in (32,68):
                    self.ring(x,103.5,15);self.ring(x,103.5,12)
                    for a in (35,145,215,325):
                        xx=x+13.5*math.cos(math.radians(a));yy=103.5+13.5*math.sin(math.radians(a));self.ring(xx,yy,.7)
                self.bezier((34,84),(42,73,58,73,66,84))
                self.line((19,65),(31,64),(69,64),(81,65),(88,58),(88,18),(76,10),(24,10),(12,18),(12,58),(19,65))
                self.heart(50,48,1)
                for x in (20,72):
                    for yy in (34,39,44):self.line((x,yy),(x+8,yy))
                for x in (22,78):
                    self.ring(x,132,3);self.line((x-1.6,132),(x+1.6,132))
                self.line((37,132),(63,132));self.line((42,128),(58,128))
                self.line((37,23),(63,23));self.line((43,19),(57,19))
            elif theme=='Uzay':
                # A diagonal rocket, porthole, curved fins and separate exhaust.
                self.bezier((30,48),(24,71,44,108,78,127),(80,89,67,61,47,48))
                self.line((30,48),(47,48))
                self.bezier((61,114),(68,111,74,107,77,101))
                self.ring(57,89,10);self.ring(57,89,7)
                self.bezier((31,74),(15,70,15,51,17,41),(23,48,28,50,31,52))
                self.bezier((59,61),(68,49,62,33,51,25),(52,39,48,44,46,48))
                self.bezier((31,42),(19,35,20,22,17,15),(34,20,40,28,41,40))
                self.bezier((33,36),(27,31,30,27,26,24))
                for x,y,r in ((32,103.5,7),(68,103.5,7),(50,48,6),(15,125,4),(85,60,4),(77,22,3)):
                    self.ring(x,y,4) if (x,y) in ((32,103.5),(68,103.5),(50,48)) else self.star(x,y,r)
                self.ring(21,82,8)
                self.bezier((10,80),(0,71,39,76,34,88));self.bezier((10,80),(13,88,36,93,34,88))
                for x,y in ((88,136),(12,58),(80,40),(44,131)):self.ring(x,y,1)
            else:
                # Friendly side-profile dinosaur, with deliberate curved silhouette.
                self.bezier((37,21),(18,17,9,28,10,43),(20,31,29,37,31,52),(25,69,27,86,41,94),(33,110,39,128,55,131),(77,139,89,123,85,111),(97,102,94,90,79,89),(68,88,61,92,58,96),(59,82,72,70,73,53),(84,47,86,32,75,23))
                self.line((75,23),(76,15),(59,15),(56,24),(47,24),(45,15),(29,15),(31,23))
                self.bezier((39,35),(34,58,44,79,57,75),(69,69,68,47,65,35))
                self.ring(66,118,5);self.ring(67,118,2)
                self.ring(84,105,1.4)
                self.bezier((72,100),(77,96,83,96,87,99))
                self.bezier((59,72),(50,67,51,59,60,61))
                self.line((31,81),(20,83),(27,70));self.line((27,64),(17,64),(26,53))
                self.line((34,91),(25,94),(28,84))
                for x,y,r in ((32,103.5,7),(68,103.5,7),(50,48,6),(18,136,4),(86,72,4)):
                    self.ring(x,y,4) if (x,y) in ((32,103.5),(68,103.5),(50,48)) else self.star(x,y,r)
                for x,y in ((40,85),(36,72),(34,59)):self.ring(x,y,2.5)
                for x in (34,39,64,69):self.line((x,15),(x,18))

    def render(self):
        if self.output_selection=='coupon':
            for gap in (.5,.6,.8,1.0):
                self.tabs=gap
                super().rectangularWall(25,25,'eeee',move='right')
            return
        if self.top_edge!='L' or self.bottom_edge!='h':
            raise ValueError('HayalKumbaram requires top_edge=L and bottom_edge=h')
        if self.output_selection in ('all','body'):
            super().render()
        else:
            if self.outside:
                self.x=self.adjustSize(self.x,'F','F')
                self.y=self.adjustSize(self.y)
                self.h=self.adjustSize(self.h,self.edges['h'],'L')
        if self.output_selection in ('all','faces'):
            self.moveTo(self.y+30,0)
            for name in ('Robot','Uzay','Dinozor'):
                super().rectangularWall(self.x,self.h,'eeee',
                    callback=[lambda n=name:self.artwork(n,self.x,self.h)],move='up',label=name)


