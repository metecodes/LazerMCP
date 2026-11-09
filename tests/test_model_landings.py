"""Generator SEO landings for Studio deep-links."""

from __future__ import annotations

import unittest

from model_landings import get_model, list_models, render_model_html


class ModelLandingTests(unittest.TestCase):
    def test_first_three_landings(self):
        rows = list_models()
        ids = {r["slug"] for r in rows}
        self.assertEqual(ids, {"parametric-box", "name-ornament", "birdhouse"})
        for slug in ids:
            model = get_model(slug)
            html = render_model_html(model)
            self.assertIn(model["title"], html)
            self.assertIn("/studio", html)
            self.assertIn("NOT_VERIFIED", html)
            self.assertIn("SSS", html)

    def test_unknown(self):
        self.assertIsNone(get_model("no-such-model"))


if __name__ == "__main__":
    unittest.main()
