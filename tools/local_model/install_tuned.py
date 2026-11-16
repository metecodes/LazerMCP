"""Install LaserMCP's own fine-tuned model on this machine and switch the Studio to it.

  python tools/local_model/install_tuned.py            download (if needed), register, check
  python tools/local_model/install_tuned.py --check    only ask the installed model for one design

What it does:
  1. Uses tools/local_model/lasermcp.gguf when it is already there. Otherwise downloads it
     from the private Kaggle dataset metecodes/lasermcp-model with the Kaggle CLI
     (pip install kaggle; token in ~/.kaggle/access_token).
  2. Registers it in Ollama as "lasermcp" with tools/local_model/Modelfile.tuned.
  3. Asks it for one design through the real gate.
  4. Prints the two settings that put it in the Studio's model list as "lasermcp-tuned".

The weights (about 2.5 GB) are never committed. The model is Qwen3-4B Instruct tuned on
gate-approved designs; see docs/MODEL_TRAINING.md for how it was trained and what it scores.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEIGHTS = HERE / "lasermcp.gguf"
DATASET = "metecodes/lasermcp-model"
NAME = "lasermcp"
BASE_URL = "http://127.0.0.1:11434/v1"
MIN_BYTES = 1_000_000_000  # a cut-off download is far smaller than the real file


def need(tool: str, hint: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise SystemExit(f"{tool} was not found. {hint}")
    return path


def download() -> None:
    kaggle = need("kaggle", "Install it with `pip install kaggle` and save your token to ~/.kaggle/access_token.")
    print(f"downloading {DATASET} (about 2.5 GB)…", flush=True)
    done = subprocess.run([kaggle, "datasets", "download", DATASET, "-p", str(HERE), "--unzip", "--force"])
    if done.returncode != 0 or not WEIGHTS.is_file():
        raise SystemExit("download failed. The dataset is private: sign in with the account that owns it.")


def register() -> None:
    ollama = need("ollama", "Install it from https://ollama.com and open it once.")
    done = subprocess.run([ollama, "create", NAME, "-f", str(HERE / "Modelfile.tuned")], cwd=str(HERE))
    if done.returncode != 0:
        raise SystemExit("ollama create failed; is Ollama running?")


def check() -> bool:
    """One request through the same path the Studio uses. True when the gate accepts it."""
    os.environ["LASERMCP_TUNED_MODEL"] = NAME
    os.environ["LASERMCP_TUNED_BASE_URL"] = BASE_URL
    os.environ.setdefault("MCP_DATA_DIR", tempfile.mkdtemp(prefix="lasermcp-install-"))
    sys.path.insert(0, str(ROOT))
    import workshop

    prompt = "300x150x400 mm 3 raflı kitaplık"
    drafts = workshop._PaidDrafts(thickness=3.0, parameters={"project": prompt, "what_you_see": prompt, "thickness": 3.0}, base="")
    plan = drafts.call(workshop._compose_ai_chat_prompt(prompt, {"messages": [{"role": "user", "text": prompt}]}), "lasermcp-tuned", "low")
    result = drafts.design(plan)
    ok = not workshop._draft_blocked(result)
    parts = len((result.get("assembly_result") or {}).get("parts") or [])
    print(f"check: '{prompt}' -> {plan['primitives'][0].get('type')}, {parts} parts, {'accepted' if ok else 'BLOCKED'} by the gate")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only test the model that is already installed")
    args = ap.parse_args(argv)
    if not args.check:
        if not WEIGHTS.is_file() or WEIGHTS.stat().st_size < MIN_BYTES:
            download()
        else:
            print(f"using {WEIGHTS.name} ({WEIGHTS.stat().st_size / 1e9:.1f} GB)")
        register()
    ok = check()
    print(
        "\nTo use it in the Studio, set these where the server runs (.env or the shell), then restart it:\n"
        f"  LASERMCP_TUNED_MODEL={NAME}\n"
        f"  LASERMCP_TUNED_BASE_URL={BASE_URL}\n"
        "  LASERMCP_LLM_DEFAULT_MODEL=lasermcp-tuned     (optional: make it the default model)\n"
        "A site on Vercel cannot reach this machine directly: it needs a tunnel (docs/MODEL_TRAINING.md, step 8)."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
