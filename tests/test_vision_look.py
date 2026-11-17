"""A picture for the workshop's own model: the vision model looks, the tuned model plans."""

import base64
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "local_model"))

import vision_look as vl

ENV = {"LASERMCP_VISION_MODEL": "qwen3-vl:4b", "LASERMCP_TUNED_BASE_URL": "http://127.0.0.1:11434/v1", "LASERMCP_VISION_BASE_URL": ""}


class ParseTests(unittest.TestCase):
    def test_a_clean_answer(self):
        seen = vl.parse('<think>hm</think>```json\n{"kind":"object","what":"kitaplık","request":"400x200x600 mm 4 raflı kitaplık",'
                        '"sizes_mm":[400,200,"600"],"parts":8,"text":""}\n```')
        self.assertEqual(seen["kind"], "object")
        self.assertEqual(seen["sizes_mm"], [400, 200, 600])
        self.assertEqual(seen["parts"], 8)

    def test_odd_answers_are_tidied_or_refused(self):
        self.assertEqual(vl.parse('{"kind":"thing","request":"kutu"}')["kind"], "object")
        self.assertEqual(vl.parse('{"kind":"art","what":"kedi"}')["request"], "")
        self.assertEqual(vl.parse('{"kind":"sign","request":"levha","sizes_mm":[-1, "x", 99999]}')["sizes_mm"], [])
        for bad in ("no json here", '{"kind":"object","request":""}', "[1, 2]"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    vl.parse(bad)


class RequestTests(unittest.TestCase):
    def test_sizes_and_text_reach_the_planner(self):
        seen = {"request": "isim levhası", "sizes_mm": [200, 3, 80], "text": "ADA"}
        self.assertEqual(vl.to_request(seen), "isim levhası, 200x3x80 mm, üstünde 'ADA' yazsın")
        written = {"request": "120x80x60 mm kapaklı kutu", "sizes_mm": [120, 80, 60], "text": ""}
        self.assertEqual(vl.to_request(written), "120x80x60 mm kapaklı kutu")

    def test_absent_features_and_a_bare_text_copy_are_dropped(self):
        self.assertEqual(vl.to_request({"request": "sehpa 350x200x250 mm, 0 raflar, yazı yazma, metin yok", "text": ""}),
                         "sehpa 350x200x250 mm")
        self.assertEqual(vl.to_request({"request": "isim levhası 200x80x3 mm, ADA", "text": "ADA"}),
                         "isim levhası 200x80x3 mm, üstünde 'ADA' yazsın")
        self.assertEqual(vl.tidy("kutu 100x100x50 mm, 3 bölme, açık üst"), "kutu 100x100x50 mm, 3 bölme, açık üst")

    def test_placeholder_text_is_not_engraved(self):
        # Seen on real photos: the model fills the text field to say "no text".
        for placeholder in ("yazı yazma", "YAZI", "metin yok", "'yazı'"):
            with self.subTest(placeholder=placeholder):
                self.assertEqual(vl.to_request({"request": "kutu 300x200x100 mm, yazı yaz, açık üst", "text": placeholder}),
                                 "kutu 300x200x100 mm, açık üst")
        self.assertEqual(vl.engraving(" 'Ada Nur' "), "Ada Nur")

    def test_the_persons_words_come_first(self):
        seen = {"request": "300x150x400 mm kitaplık", "sizes_mm": [], "text": ""}
        self.assertEqual(vl.to_request(seen, " 5 mm  kontrplak "), "5 mm kontrplak. Görselde: 300x150x400 mm kitaplık")


class ShrinkTests(unittest.TestCase):
    def test_a_big_picture_is_shrunk_and_a_small_one_kept(self):
        from PIL import Image

        def png(size):
            out = io.BytesIO()
            Image.new("RGB", size, (200, 150, 100)).save(out, "PNG")
            return base64.b64encode(out.getvalue()).decode("ascii")

        small = png((300, 200))
        self.assertEqual(vl.shrink(small, "image/png"), (small, "image/png"))
        data, media = vl.shrink(png((3000, 1500)), "image/png")
        self.assertEqual(media, "image/jpeg")
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data))).size, (1024, 512))

    def test_off_without_a_model(self):
        with mock.patch.dict(os.environ, {"LASERMCP_VISION_MODEL": ""}):
            self.assertFalse(vl.ready())
            with self.assertRaises(ValueError):
                vl.look("aGk=")


class StudioRouteTests(unittest.TestCase):
    """workshop._look_then_plan: which pictures reach the tuned model, and in what words."""

    def route(self, seen=None, error=None, prompt=""):
        import workshop

        payload = {"image_base64": "data:image/png;base64,aGk=", "file_kind": "photo", "model": "lasermcp-tuned",
                   "prompt": prompt, "messages": [], "thickness": 3}
        calls = []

        def fake_design(body, **_):
            calls.append(body)
            return {"success": True, "final_status": "PROTOTYPE READY", "look_again": ["ok"]}

        look = mock.Mock(side_effect=error) if error else mock.Mock(return_value=seen)
        with mock.patch.dict(os.environ, ENV), mock.patch.object(vl, "look", look), \
                mock.patch.object(workshop, "create_studio_ai", fake_design):
            reply = workshop._look_then_plan(payload, raw_prompt=prompt, public_base_url="", client_ip="t")
        return reply, calls, payload

    def test_an_object_is_planned_from_words_without_the_picture(self):
        seen = {"kind": "object", "what": "kitaplık", "request": "400x200x600 mm 4 raflı kitaplık", "sizes_mm": [400, 200, 600],
                "parts": 8, "text": "", "seconds": 3.0, "model": "qwen3-vl:4b"}
        reply, calls, _ = self.route(seen, prompt="kayın kontrplak")
        self.assertEqual(len(calls), 1)
        body = calls[0]
        self.assertEqual(body["prompt"], "kayın kontrplak. Görselde: 400x200x600 mm 4 raflı kitaplık")
        self.assertEqual(body["model"], "lasermcp-tuned")
        self.assertFalse(any(k in body for k in ("image_base64", "file_kind")))
        self.assertTrue(body["_seen"])
        self.assertEqual(reply["look"]["what"], "kitaplık")
        self.assertIn("Görselde gördüğüm: kitaplık", reply["look_again"][0])

    def test_art_and_failures_go_back_to_tracing(self):
        art = {"kind": "art", "what": "kedi silueti", "request": "", "sizes_mm": [], "parts": 1, "text": "", "seconds": 1, "model": "m"}
        reply, calls, payload = self.route(art)
        self.assertIsNone(reply)
        self.assertFalse(calls)
        self.assertIn("motif", payload["_look_note"])
        reply, calls, payload = self.route(error=ValueError("the vision model is not reachable"))
        self.assertIsNone(reply)
        self.assertIn("bakamadı", payload["_look_note"])

    def test_nothing_changes_without_a_vision_model(self):
        import workshop

        with mock.patch.dict(os.environ, {"LASERMCP_VISION_MODEL": ""}):
            self.assertIsNone(workshop._look_then_plan({"image_base64": "aGk="}, raw_prompt="", public_base_url="", client_ip=""))


class ProxyTests(unittest.TestCase):
    def test_the_vision_model_is_served_only_when_set_up(self):
        import tempfile

        import tunnel_proxy as tp

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"LASERMCP_VISION_MODEL": ""}):
            env = Path(tmp) / ".env"
            env.write_text("LASERMCP_LOCAL_API_KEY=k\n", encoding="utf-8")
            self.assertEqual(tp.served_models(env), frozenset({"lasermcp"}))
            env.write_text("LASERMCP_LOCAL_API_KEY=k\nLASERMCP_VISION_MODEL=qwen3-vl:4b\n", encoding="utf-8")
            models = tp.served_models(env)
        self.assertEqual(models, frozenset({"lasermcp", "qwen3-vl:4b"}))
        body = b'{"model": "qwen3-vl:4b", "messages": []}'
        self.assertEqual(tp.check("POST", "/v1/chat/completions", "Bearer k", body, "k", models)[0], 200)
        self.assertEqual(tp.check("POST", "/v1/chat/completions", "Bearer k", body, "k")[0], 403)


class ScoreTests(unittest.TestCase):
    def test_traced_blocked_and_a_good_reply(self):
        import vision_eval as ve

        row = {"id": "s", "kind": "sketch", "about": "kitaplık", "min_panels": 6, "max_panels": 10,
               "types": ["shelf_unit"], "size_mm": [400, 200, 600], "text": ""}
        good = {"success": True, "final_status": "PROTOTYPE READY",
                "assembly": {"panels": [{"label": n} for n in ("bottom", "top", "left", "right", "back", "shelf-1", "shelf-2")]},
                "look": {"what": "kitaplık", "request": "400x200x600 mm 4 raflı kitaplık", "seconds": 2}}
        self.assertEqual(ve.score_reply(row, good)["problems"], [])
        self.assertEqual(ve.score_reply(row, {"success": True, "final_status": "PROTOTYPE READY"})["problems"], ["traced"])
        wrong = {**good, "look": {"what": "kutu", "request": "300x200x600 mm kutu"},
                 "assembly": {"panels": [{"label": f"P01/{n}"} for n in ("bottom", "left", "right", "back", "front")]}}
        self.assertEqual(ve.score_reply(row, wrong)["problems"], ["parts:5<6", "type", "size"])
        plate = {"id": "p", "kind": "sketch", "about": "levha", "min_panels": 1, "max_panels": 2, "text": "ADA"}
        flat = {"success": True, "final_status": "PROTOTYPE READY", "look": {"what": "levha", "request": "levha, üstünde 'ADA' yazsın"}}
        self.assertEqual(ve.score_reply(plate, flat)["problems"], [])


if __name__ == "__main__":
    unittest.main()
