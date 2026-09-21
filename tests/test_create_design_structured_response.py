import unittest
from unittest.mock import patch

import payas_cad


class CreateDesignStructuredResponseTests(unittest.TestCase):
    def test_unknown_icon_returns_typed_nonempty_error(self):
        result = payas_cad.create_design(primitives=[{
            "type":"panel","label":"board","w":90,"h":125,"edges":"eeee",
            "markings":[{"kind":"icon","value":"non_existing_random_icon","x":45,"y":60,"width":20,"operation":"engrave"}],
        }], parameters={"assembly_mode":"standalone"})
        self.assertTrue(result)
        self.assertFalse(result["success"])
        self.assertEqual(result["final_status"],"BLOCKED")
        self.assertEqual(result["error_code"],"UNKNOWN_ENGRAVING_ICON")
        self.assertEqual(result["error_stage"],"icon_resolver")
        self.assertTrue(result["error_message"])

    def test_alphabet_panel_success_response_has_required_fields(self):
        marks=[]
        for i,ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            marks.append({"kind":"text","value":ch,"x":9+(i%5)*18,"y":115-(i//5)*12,"height":5,"operation":"engrave"})
        marks.extend([
            {"kind":"text","value":"A Apple","x":20,"y":30,"height":4,"operation":"engrave"},
            {"kind":"icon","value":"apple","x":20,"y":18,"width":7,"operation":"engrave"},
            {"kind":"text","value":"B Ball","x":45,"y":30,"height":4,"operation":"engrave"},
            {"kind":"icon","value":"ball","x":45,"y":18,"width":7,"operation":"engrave"},
            {"kind":"text","value":"C Cat","x":70,"y":30,"height":4,"operation":"engrave"},
            {"kind":"icon","value":"cat","x":70,"y":18,"width":7,"operation":"engrave"},
        ])
        fake={"success":True,"file_id":"alphabet.svg","svg_url":"https://example.test/alphabet.svg","dxf_url":"https://example.test/alphabet.dxf"}
        with patch("payas_cad._save_build", return_value=fake):
            result=payas_cad.create_design(primitives=[{"type":"panel","label":"alphabet-board","w":90,"h":125,"edges":"eeee","markings":marks}], parameters={"assembly_mode":"standalone","format":"both"})
        self.assertTrue(result["success"]);self.assertEqual(result["file_id"],"alphabet.svg")
        self.assertEqual(result["final_status"],"PROTOTYPE READY")
        self.assertTrue(result["svg_url"]);self.assertTrue(result["dxf_url"]);self.assertTrue(result["speak"])


if __name__=="__main__": unittest.main()
