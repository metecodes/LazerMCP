import base64
import io
import unittest
from PIL import Image, ImageDraw
from markings import marking_geom
from design_engine import compile_design
from xml.etree import ElementTree as ET

def sample(background, foreground):
    image=Image.new('RGB',(100,100),background)
    ImageDraw.Draw(image).ellipse((25,20,75,80),outline=foreground,width=3)
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

class ImageEngravingTests(unittest.TestCase):
    def test_yellow_selection_excludes_black_part_outlines(self):
        image=Image.new('RGBA',(100,100),(0,0,0,0))
        draw=ImageDraw.Draw(image)
        draw.line((5,5,5,95),fill=(0,0,0,255),width=3)
        draw.ellipse((25,20,75,80),outline=(255,255,0,255),width=3)
        buffer=io.BytesIO();image.save(buffer,format='PNG')
        from image_engraving import image_geometry
        geom=image_geometry({'image_base64':base64.b64encode(buffer.getvalue()).decode(),'ink_color':'yellow'})
        self.assertGreater(geom.bounds[0],20)

    def test_transparent_yellow_details_are_not_lost(self):
        image=Image.new('RGBA',(100,100),(0,0,0,0))
        ImageDraw.Draw(image).ellipse((25,20,75,80),outline=(255,255,0,255),width=2)
        buffer=io.BytesIO();image.save(buffer,format='PNG')
        geom=marking_geom({'kind':'image','image_base64':base64.b64encode(buffer.getvalue()).decode(),'x':50,'y':50,'width':30})
        self.assertGreater(len(geom.geoms),1)
        self.assertAlmostEqual(geom.bounds[2]-geom.bounds[0],30)

    def test_image_can_be_engraved_on_a_real_panel(self):
        built=compile_design(primitives=[{'type':'panel','w':100,'h':100,'edges':'eeee','label':'police-panel','markings':[{'kind':'image','image_base64':sample('white','black'),'x':50,'y':50,'width':30}]}],parameters={})
        paths=[el for el in ET.fromstring(built['svg_bytes']).iter() if el.tag.endswith('path') and el.get('data-operation')=='ENGRAVE']
        self.assertTrue(paths)
        self.assertTrue(all(p.get('stroke')=='#FFFF00' for p in paths))

    def test_both_backgrounds_and_position(self):
        for bg,fg in [('white','black'),('black','yellow')]:
            geom=marking_geom({'kind':'image','image_base64':sample(bg,fg),'x':50,'y':60,'width':30})
            self.assertAlmostEqual(geom.bounds[2]-geom.bounds[0],30)
            self.assertAlmostEqual((geom.bounds[0]+geom.bounds[2])/2,50)
            self.assertAlmostEqual((geom.bounds[1]+geom.bounds[3])/2,60)
            self.assertGreater(len(geom.geoms),1)

    def test_real_layout_is_yellow(self):
        built=compile_design(preset='engraving_layout',parameters={'width_mm':100,'height_mm':100,'items':[{'kind':'image','image_base64':sample('black','yellow'),'x':50,'y':50,'width':30}]})
        paths=[el for el in ET.fromstring(built['svg_bytes']).iter() if el.tag.endswith('path')]
        self.assertTrue(paths)
        self.assertTrue(all(p.get('data-operation')=='ENGRAVE' and p.get('stroke')=='#FFFF00' for p in paths))

    def test_bad_inputs_and_cut_rejected(self):
        for extra in [{'crop':[.8,0,.2,1]},{'operation':'cut'},{'foreground':'nonsense'}]:
            with self.assertRaises(ValueError):marking_geom({'kind':'image','image_base64':sample('white','black'),'width':30,**extra})
