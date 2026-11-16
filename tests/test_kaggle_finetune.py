"""The Kaggle notebook's pure helpers: turn markers and arguments for old and new TRL."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kaggle_finetune as kf


class MarkerTests(unittest.TestCase):
    def test_markers_come_from_the_rendered_template(self):
        qwen = "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nU<|im_end|>\n<|im_start|>assistant\nA<|im_end|>\n"
        self.assertEqual(kf.turn_markers(qwen), ("<|im_start|>user\n", "<|im_start|>assistant\n"))
        phi = "<|system|>S<|end|><|user|>U<|end|><|assistant|>A<|end|>"
        self.assertEqual(kf.turn_markers(phi), ("<|user|>", "<|assistant|>"))

    def test_an_unknown_format_stops_instead_of_training_on_nothing(self):
        with self.assertRaises(SystemExit):
            kf.turn_markers("### User: U ### Bot: A")


class TrlArgumentTests(unittest.TestCase):
    def test_new_trl_names(self):
        class NewConfig:
            def __init__(self, output_dir=None, max_length=None, **kw): ...

        class NewTrainer:
            def __init__(self, model=None, processing_class=None, **kw): ...

        args = kf.config_kwargs(NewConfig, 4096, has_valid=True)
        self.assertEqual(args["max_length"], 4096)
        self.assertNotIn("max_seq_length", args)
        self.assertEqual(args["eval_strategy"], "epoch")
        self.assertEqual(kf.tokenizer_key(NewTrainer), "processing_class")

    def test_old_trl_names(self):
        class OldConfig:
            def __init__(self, output_dir=None, max_seq_length=None, **kw): ...

        class OldTrainer:
            def __init__(self, model=None, tokenizer=None, **kw): ...

        args = kf.config_kwargs(OldConfig, 2048, has_valid=False)
        self.assertEqual(args["max_seq_length"], 2048)
        self.assertEqual(args["eval_strategy"], "no")
        self.assertEqual(kf.tokenizer_key(OldTrainer), "tokenizer")


class DataDirTests(unittest.TestCase):
    def test_finds_the_uploaded_folder_whatever_kaggle_names_it(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "datasets" / "someone" / "lasermcp-data"
            data.mkdir(parents=True)
            (data / "train.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertEqual(kf.find_data_dir(root / "lasermcp-train", root), data)
            self.assertEqual(kf.find_data_dir(data, root / "missing"), data)
            with self.assertRaises(SystemExit):
                kf.find_data_dir(root / "x", root / "missing")


if __name__ == "__main__":
    unittest.main()
