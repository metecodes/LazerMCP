"""Password-protected door in front of the local model, for a tunnel from the deployed site.

Ollama has no sign-in and its API can also pull and delete models, so it must never be put
on a public address as it is. This proxy is what the tunnel points at instead:

  - it listens on 127.0.0.1 only;
  - every request must carry `Authorization: Bearer <LASERMCP_LOCAL_API_KEY>`;
  - only POST /v1/chat/completions is passed on, and only for the model "lasermcp";
  - request bodies are capped, and nothing else on the machine is reachable.

  python tools/local_model/tunnel_proxy.py            listens on 127.0.0.1:8790
  python tools/local_model/tunnel_proxy.py --new-key  writes a fresh key to .env and exits

The key lives in the project's .env (never committed). The deployed site needs the same
value as LASERMCP_LOCAL_API_KEY, the tunnel's public address + "/v1" as
LASERMCP_TUNED_BASE_URL, and LASERMCP_TUNED_MODEL=lasermcp.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
KEY_NAME = "LASERMCP_LOCAL_API_KEY"
UPSTREAM = "http://127.0.0.1:11434"
ALLOWED_PATH = "/v1/chat/completions"
ALLOWED_MODELS = frozenset({"lasermcp"})
MAX_BODY = 200_000


def read_key(env_path: Path = ENV) -> str:
    value = str(os.environ.get(KEY_NAME) or "").strip()
    if value or not env_path.is_file():
        return value
    for line in env_path.read_text(encoding="utf-8").splitlines():
        name, _, rest = line.partition("=")
        if name.strip() == KEY_NAME:
            return rest.strip().strip('"').strip("'")
    return ""


def write_new_key(env_path: Path = ENV) -> str:
    """Create a key and store it in .env, replacing an older one. Returns the key."""
    key = "lmk_" + secrets.token_urlsafe(32)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    lines = [line for line in lines if line.partition("=")[0].strip() != KEY_NAME]
    lines.append(f"{KEY_NAME}={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return key


def check(method: str, path: str, auth: str, body: bytes, key: str) -> tuple[int, str]:
    """(status, reason) for a request. 200 means it may be passed on. Pure: no I/O."""
    if not key:
        return 503, "proxy has no key configured"
    given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not given or not hmac.compare_digest(given.encode(), key.encode()):
        return 401, "unauthorized"
    if method != "POST" or path.split("?")[0].rstrip("/") != ALLOWED_PATH:
        return 404, "only POST /v1/chat/completions is served"
    if len(body) > MAX_BODY:
        return 413, "request too large"
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 400, "body is not JSON"
    if not isinstance(data, dict) or str(data.get("model")) not in ALLOWED_MODELS:
        return 403, "model not served here"
    if data.get("stream"):
        return 400, "streaming is not supported"
    return 200, ""


class Handler(BaseHTTPRequestHandler):
    key = ""
    upstream = UPSTREAM

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self) -> None:
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._reply(413, {"error": {"message": "request too large"}})
            return
        body = self.rfile.read(length) if length else b""
        status, reason = check(self.command, self.path, self.headers.get("authorization") or "", body, self.key)
        if status != 200:
            self._reply(status, {"error": {"message": reason}})
            return
        req = urllib.request.Request(self.upstream + ALLOWED_PATH, data=body, headers={"content-type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            self._reply(exc.code, {"error": {"message": "model error"}})
        except OSError:
            self._reply(502, {"error": {"message": "the local model is not running"}})

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _handle

    def log_message(self, fmt: str, *args) -> None:  # status lines only; never bodies or keys
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--new-key", action="store_true", help="write a fresh key to .env and exit")
    args = ap.parse_args(argv)
    if args.new_key:
        write_new_key()
        print(f"A new key was written to {ENV} as {KEY_NAME}. Copy it from there into the site's settings.")
        return 0
    key = read_key()
    if not key:
        print(f"No {KEY_NAME} yet. Run with --new-key first.")
        return 1
    Handler.key = key
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"proxy for the local model on http://127.0.0.1:{args.port} (key required)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
