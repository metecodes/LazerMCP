"""Fine-tune a small open model on LaserMCP designs, on a free Kaggle (or Colab) GPU.

NOT run by LaserMCP: paste this file into one notebook cell. It needs a GPU runtime and
internet access, both free on Kaggle. Only the pure helpers (turn markers, trainer
arguments) are covered by tests/test_kaggle_finetune.py.

Before running:
  1. Locally:  tools/train.py collect   then   tools/train.py build
  2. Upload output/train/train.jsonl and valid.jsonl to the notebook
     (Kaggle: "Add input" -> "Upload" -> new dataset; Colab: the Files panel).
  3. Notebook settings: Accelerator = GPU T4, Internet = on.
  4. Set DATA_DIR below to where the two files appear.

Result: /kaggle/working/lasermcp.gguf. Download it, put it in tools/local_model/ and run
  ollama create lasermcp -f tools/local_model/Modelfile.tuned

BASE: the first pilots kept 62% of qwen3:4b drafts against 21% for phi4-mini, so the
default is the Qwen3 4B instruct model. Any small instruct model works; the turn markers
are read from its own chat template. Check the base model's licence before commercial use.
Library versions move fast: the trainer arguments below adapt to old and new TRL; if
something else fails, follow the current Unsloth notebook for your base model and keep the
data-loading part of this file.
"""

# %pip install -q unsloth          # run this line in its own cell first, then restart the kernel

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

BASE = "unsloth/Qwen3-4B-Instruct-2507"   # ~4B parameters; q4 GGUF is ~2.5 GB
DATA_DIR = Path("/kaggle/input/lasermcp-train")
OUT_DIR = Path("/kaggle/working")
MAX_TOKENS = 4096                      # prompt + design; longer examples are skipped, not cut
EPOCHS = 3
RANK = 16

# (user turn start, assistant turn start) for the chat formats of common small models.
KNOWN_MARKERS: tuple[tuple[str, str], ...] = (
    ("<|im_start|>user\n", "<|im_start|>assistant\n"),  # Qwen2.5 / Qwen3, ChatML
    ("<|user|>", "<|assistant|>"),  # Phi-3 / Phi-4-mini
    ("<start_of_turn>user\n", "<start_of_turn>model\n"),  # Gemma
    ("<|start_header_id|>user<|end_header_id|>\n\n", "<|start_header_id|>assistant<|end_header_id|>\n\n"),  # Llama 3
)


def turn_markers(rendered: str) -> tuple[str, str]:
    """The user/assistant markers present in a chat-template rendering.

    Training only on the assistant turn needs the base model's own markers; a wrong pair
    silently trains on nothing (or on the system prompt), so an unknown format stops here.
    """
    for user, assistant in KNOWN_MARKERS:
        if user in rendered and assistant in rendered:
            return user, assistant
    raise SystemExit("unknown chat format: add this base model's user/assistant markers to KNOWN_MARKERS\n" + rendered[:400])


def config_kwargs(config_cls: Any, max_tokens: int, has_valid: bool) -> dict[str, Any]:
    """SFTConfig arguments for the installed TRL (max_seq_length became max_length in 0.20)."""
    params = inspect.signature(config_cls).parameters
    length_key = "max_length" if "max_length" in params else "max_seq_length"
    return {
        "output_dir": str(OUT_DIR / "checkpoints"),
        "dataset_text_field": "text",
        length_key: max_tokens,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "num_train_epochs": EPOCHS,
        "learning_rate": 2e-4,
        "warmup_ratio": 0.05,
        "lr_scheduler_type": "cosine",
        "logging_steps": 10,
        "eval_strategy": "epoch" if has_valid else "no",
        "save_strategy": "no",
        "fp16": True,
        "optim": "adamw_8bit",
        "seed": 7,
        "report_to": "none",
    }


def tokenizer_key(trainer_cls: Any) -> str:
    """TRL renamed SFTTrainer(tokenizer=) to processing_class=; older builds only know the first."""
    params = inspect.signature(trainer_cls).parameters
    return "tokenizer" if "tokenizer" in params and "processing_class" not in params else "processing_class"


def load_rows(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    from unsloth import FastLanguageModel  # must be imported before transformers
    from unsloth.chat_templates import train_on_responses_only
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(BASE, max_seq_length=MAX_TOKENS, load_in_4bit=True)
    model = FastLanguageModel.get_peft_model(
        model,
        r=RANK,
        lora_alpha=RANK,
        lora_dropout=0.0,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=7,
    )

    def as_text(rows: list[dict]) -> Dataset:
        texts = []
        for row in rows:
            text = tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=False)
            # A design cut off mid-JSON would teach the model to stop early: skip, never truncate.
            if len(tokenizer(text).input_ids) <= MAX_TOKENS:
                texts.append(text)
        print(f"kept {len(texts)} of {len(rows)} examples under {MAX_TOKENS} tokens")
        return Dataset.from_dict({"text": texts})

    train_rows = load_rows(DATA_DIR / "train.jsonl")
    train = as_text(train_rows)
    valid_rows = load_rows(DATA_DIR / "valid.jsonl")
    valid = as_text(valid_rows) if valid_rows else None
    if len(train) < 50:
        raise SystemExit("too few examples to train on; collect more first")
    user_marker, assistant_marker = turn_markers(train["text"][0])
    print("turn markers:", repr(user_marker), repr(assistant_marker))

    trainer = SFTTrainer(
        model=model,
        train_dataset=train,
        eval_dataset=valid,
        args=SFTConfig(**config_kwargs(SFTConfig, MAX_TOKENS, valid is not None)),
        **{tokenizer_key(SFTTrainer): tokenizer},
    )
    # Learn only the design JSON (the assistant turn), not to recite the system prompt.
    trainer = train_on_responses_only(trainer, instruction_part=user_marker, response_part=assistant_marker)
    trainer.train()

    # One 4-bit GGUF file that Ollama / llama.cpp can serve on a 4 GB GPU.
    model.save_pretrained_gguf(str(OUT_DIR / "gguf"), tokenizer, quantization_method="q4_k_m")
    # Some Unsloth versions also leave a full-precision GGUF; the q4 file is the smallest.
    made = [p for p in OUT_DIR.rglob("*.gguf") if p.name != "lasermcp.gguf"]
    if not made:
        raise SystemExit("no .gguf was written; check the save step output above")
    min(made, key=lambda p: p.stat().st_size).rename(OUT_DIR / "lasermcp.gguf")
    print("done:", OUT_DIR / "lasermcp.gguf")


if __name__ == "__main__":
    main()
