"""Run the Studio on this machine with LaserMCP's own fine-tuned model as its AI.

  python tools/local_model/run_studio.py            http://127.0.0.1:8765/studio
  python tools/local_model/run_studio.py --no-auth  single-user: no sign-in on this machine

No provider key and no bill: every AI request goes to the model installed by
install_tuned.py ("lasermcp" in Ollama). Nothing here changes the deployed site.
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = "http://127.0.0.1:11434"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-auth", action="store_true", help="run as a single-user install without sign-in")
    args = ap.parse_args(argv)
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read()
    except OSError:
        print("Ollama is not running. Open Ollama, then run this again (install_tuned.py registers the model).")
        return 1
    os.environ["LASERMCP_TUNED_MODEL"] = "lasermcp"
    os.environ["LASERMCP_TUNED_BASE_URL"] = OLLAMA + "/v1"
    os.environ["LASERMCP_LLM_DEFAULT_MODEL"] = "lasermcp-tuned"
    os.environ["LASERMCP_LLM_MODELS"] = "lasermcp-tuned"
    os.environ["MCP_PORT"] = str(args.port)
    if args.no_auth:
        # Present but empty, so the .env file does not switch accounts back on.
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "MCP_AUTH_TOKEN"):
            os.environ[key] = ""
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.argv = [str(ROOT / "server.py")]
    print(f"Studio with the local model: http://127.0.0.1:{args.port}/studio", flush=True)
    runpy.run_path(str(ROOT / "server.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
