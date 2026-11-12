"""Fine-tune a small open model on LaserMCP designs, on a free Kaggle (or Colab) GPU.

NOT run by LaserMCP and not covered by the test suite: paste this file into one notebook
cell. It needs a GPU runtime and internet access, both free on Kaggle.

Before running:
  1. Locally:  tools/train.py collect   then   tools/train.py build
  2. Upload output/train/train.jsonl and valid.jsonl to the notebook
     (Kaggle: "Add input" -> "Upload" -> new dataset; Colab: the Files panel).
  3. Notebook settings: Accelerator = GPU T4, Internet = on.
  4. Set DATA_DIR below to where the two files appear.

Result: /kaggle/working/lasermcp.gguf. Download it, put it in tools/local_model/ and run
  ollama create lasermcp -f tools/local_model/Modelfile.tuned

BASE must be the same model family the teacher used only if you want a fair comparison;
any small instruct model works. Check the base model's licence before commercial use.
Library versions move fast: if an import or argument fails, follow the current Unsloth
notebook for your base model and keep the data-loading part of this file.
"""

# %pip install -q unsloth          # run this line in its own cell first, then restart the kernel

import json
from pathlib import Path

BASE = "unsloth/Phi-4-mini-instruct"   # ~3.8B parameters; fits a 4 GB GPU after 4-bit export
DATA_DIR = Path("/kaggle/input/lasermcp-train")
OUT_DIR = Path("/kaggle/working")
MAX_TOKENS = 4096                      # prompt + design; longer examples are skipped, not cut
EPOCHS = 3
RANK = 16


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
    from transformers import TrainingArguments
    from trl import SFTTrainer

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

    train = as_text(load_rows(DATA_DIR / "train.jsonl"))
    valid_rows = load_rows(DATA_DIR / "valid.jsonl")
    valid = as_text(valid_rows) if valid_rows else None
    if len(train) < 50:
        raise SystemExit("too few examples to train on; collect more first")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train,
        eval_dataset=valid,
        dataset_text_field="text",
        max_seq_length=MAX_TOKENS,
        args=TrainingArguments(
            output_dir=str(OUT_DIR / "checkpoints"),
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=EPOCHS,
            learning_rate=2e-4,
            warmup_ratio=0.05,
            lr_scheduler_type="cosine",
            logging_steps=10,
            eval_strategy="epoch" if valid is not None else "no",
            save_strategy="no",
            fp16=True,
            optim="adamw_8bit",
            seed=7,
            report_to="none",
        ),
    )
    # Learn only the design JSON (the assistant turn), not to recite the system prompt. The
    # markers below are Phi-4-mini's; for another base model use its own turn markers.
    trainer = train_on_responses_only(trainer, instruction_part="<|user|>", response_part="<|assistant|>")
    trainer.train()

    # One 4-bit GGUF file that Ollama / llama.cpp can serve on a 4 GB GPU.
    model.save_pretrained_gguf(str(OUT_DIR / "gguf"), tokenizer, quantization_method="q4_k_m")
    made = sorted((OUT_DIR / "gguf").glob("*.gguf"))
    if made:
        made[0].rename(OUT_DIR / "lasermcp.gguf")
        print("done:", OUT_DIR / "lasermcp.gguf")


if __name__ == "__main__":
    main()
