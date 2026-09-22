import unittest
from xml.etree import ElementTree as ET
from toolbox import render_toolbox

class EngravingCompositionTests(unittest.TestCase):
    def test_image_caption_learning_card_auto_fits_and_stays_engrave(self):
        part={"type":"panel","label":"dog-card","w":60,"h":80,"edges":"eeee","engraving_composition":{
            "layout":"image_caption","safe_margin_mm":4,"items":[{"illustration":{"kind":"icon","icon":"heart"},"caption":"DOG"}]}}
        built=render_toolbox([part],{});report=built["engraving_composition"][0]
        self.assertEqual(report["status"],"PASS");self.assertEqual(report["item_count"],2)
        self.assertTrue(all(c["status"]=="PASS" for c in report["checks"]))
        paths=[el for el in ET.fromstring(built["svg_bytes"]).iter() if el.tag.endswith("path") and el.get("data-operation")=="ENGRAVE"]
        self.assertTrue(paths);self.assertTrue(all(p.get("stroke")=="#000000" for p in paths))

    def test_grid_places_multiple_words(self):
        part={"type":"panel","label":"sentence-board","w":160,"h":80,"edges":"eeee","engraving_composition":{"layout":"grid","columns":3,"items":["I","like","apples","She","has","a cat"]}}
        built=render_toolbox([part],{});report=built["engraving_composition"][0]
        self.assertEqual(report["item_count"],6);self.assertTrue(all(c["status"]=="PASS" for c in report["checks"]))

    def test_radial_learning_wheel_avoids_center_hole(self):
        part={"type":"disc","label":"weather-wheel","d":140,"hole":8,"engraving_composition":{"layout":"radial","safe_margin_mm":5,"mechanical_clearance_mm":3,"items":["SUNNY","RAINY","WINDY","SNOWY","CLOUDY"]}}
        built=render_toolbox([part],{});report=built["engraving_composition"][0]
        self.assertEqual(report["item_count"],5);self.assertTrue(all(c["status"]=="PASS" for c in report["checks"]))

    def test_composition_rejects_cut_operation(self):
        part={"type":"panel","w":60,"h":60,"edges":"eeee","engraving_composition":{"items":[{"kind":"text","value":"DOG","operation":"cut"}]}}
        with self.assertRaisesRegex(ValueError,"ENGRAVE"):render_toolbox([part],{})

    def test_safe_area_rejects_artwork_over_mechanical_cutout(self):
        part={"type":"panel","w":40,"h":40,"edges":"eeee","holes":[{"x":20,"y":20,"d":30}],"engraving_composition":{"layout":"grid","items":["A"]}}
        with self.assertRaisesRegex(ValueError,"safe area|mechanical cutout"):render_toolbox([part],{})

if __name__=="__main__":unittest.main()
