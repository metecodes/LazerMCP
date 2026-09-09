"""Hit the local HTTP MCP: /health, tools, generated file URL."""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request

from mcp import Client


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read()


async def call_tools() -> dict:
    async with Client("http://127.0.0.1:8000/mcp") as client:
        listed = await client.call_tool("list_generators")
        generated = await client.call_tool(
            "generate_svg",
            {
                "generator": "SimpleBox",
                "parameters": {"x": 220, "y": 160, "h": 50},
            },
        )
        return {
            "tools": [tool.name for tool in (await client.list_tools()).tools],
            "list_generators": listed,
            "generate_svg": generated,
        }


def _tool_payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    texts = []
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return {"text": texts[0]}
    return {"content": texts}


def main() -> int:
    print("== GET / ==")
    root = get_json("http://127.0.0.1:8000/")
    print(json.dumps(root, ensure_ascii=False, indent=2))

    print("\n== GET /health ==")
    print(get_json("http://127.0.0.1:8000/health"))

    print("\n== MCP tools ==")
    raw = asyncio.run(call_tools())
    print("tool names:", raw["tools"])
    generated = _tool_payload(raw["generate_svg"])
    print("generate_svg:", json.dumps(generated, ensure_ascii=False, indent=2))

    file_id = generated["file_id"]
    svg_url = generated["svg_url"]
    print("\n== GET file ==")
    data = get_bytes(svg_url)
    print(f"{svg_url} -> {len(data)} bytes, starts {data[:40]!r}")

    print("\n== validate + preview ==")

    async def extras() -> None:
        async with Client("http://127.0.0.1:8000/mcp") as client:
            valid = _tool_payload(await client.call_tool("validate_svg", {"file_id": file_id}))
            preview = _tool_payload(await client.call_tool("render_preview", {"file_id": file_id}))
            print("validate_svg:", json.dumps(valid, ensure_ascii=False, indent=2))
            print("render_preview:", json.dumps(preview, ensure_ascii=False, indent=2))

    asyncio.run(extras())
    ok = root.get("status") == "ok" and generated.get("success") and data.startswith(b"<?xml")
    print("\n== RESULT ==")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
