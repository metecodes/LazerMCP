"""Studio agent: the Studio's own AI works with the same tools an MCP client gets.

An assistant connected over MCP plans, calls plan_laser_job / create_design / validate /
export_dxf, reads the gate's notes and tries again. The Studio's planner wrote one JSON
draft and stopped. This module gives the Studio the same loop: the model is shown the
server's real tool list (read from the MCP registry, so a tool added to the server is
available here without another line of code), calls tools step by step, and the loop
feeds each result back until the model answers in words.

The loop is provider-neutral: OpenAI-compatible servers (OpenAI, Ollama, llama.cpp) and
Anthropic are two small adapters over one transcript. An image attached to the request is
shown to the model with the first message.

Limits: LASERMCP_AGENT_MAX_STEPS (default 12 model turns), LASERMCP_AGENT_MAX_USD (default
0.50 per request). LASERMCP_AGENT_TOOLS=core shows only the preferred design tools, for
models with a small context.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import threading
from typing import Any, Callable

# Not design tools: account administration and the chunked upload plumbing an MCP client
# needs to send a file. In the Studio the picture arrives with the request itself.
DENY = frozenset({"studio", "start_reference_upload", "upload_reference_chunk", "discard_reference_upload"})
CORE = (
    "plan_laser_job", "create_design", "create_from_reference", "validate_assembly", "validate_svg",
    "payas_defaults", "search_joint_templates", "get_generator_schema", "generate_svg", "render_preview",
    "inspect_design", "export_dxf", "export_svg",
)
RESULT_CHARS = 6000  # what the model reads back from one tool call
STRING_CHARS = 600   # one string inside a result (SVG, base64 and file bodies are far longer)

STUDIO_RULES = """
You are working inside LaserMCP Studio for one user request. Work step by step:
1. Say in one or two sentences what you see or what is asked, and the parts you plan.
2. Call the tools to plan and build it. Read every result: when final_status is BLOCKED,
   read look_again / blocking_reasons, change only what they name and try again.
3. A design that is not BLOCKED already carries its files (dxf_url, svg_url): stop calling
   tools then. Never pass SVG or DXF text through a tool yourself.
4. When a tool answers NEEDS_INPUT with questions and the request does not already answer
   them, stop and ask the user those questions in your final answer.
5. Finish with a short answer in the user's language: what was built, its size and part
   count, and anything the user must check by hand. Never claim a physical fit was verified.
If the request cannot be built after several attempts, say plainly what blocked it.
"""


# --- tools ------------------------------------------------------------------------------------

def _run(coro_factory: Callable[[], Any]) -> Any:
    """Run a coroutine to completion from sync code, inside or outside a running loop.

    The request's context (who is signed in, quota) travels into the worker thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    box: dict[str, Any] = {}
    ctx = contextvars.copy_context()

    def work() -> None:
        try:
            box["value"] = ctx.run(asyncio.run, coro_factory())
        except BaseException as exc:  # handed back to the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def tool_specs(scope: str = "") -> list[dict[str, Any]]:
    """The server's tools as {name, description, parameters}, in the server's own order."""
    import server

    scope = (scope or os.environ.get("LASERMCP_AGENT_TOOLS") or "all").strip().lower()
    out = []
    for tool in _run(lambda: server.mcp.list_tools()):
        if tool.name in DENY or (scope == "core" and tool.name not in CORE):
            continue
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
        out.append({
            "name": tool.name,
            "description": str(tool.description or "")[:1024],
            "parameters": schema if isinstance(schema, dict) and schema.get("type") == "object" else {"type": "object", "properties": {}},
        })
    return out


def compact(value: Any, limit: int = STRING_CHARS) -> Any:
    """A tool result the model can afford to read: long strings cut, structure kept."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"… [{len(value) - limit} more characters]"
    if isinstance(value, dict):
        return {k: compact(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [compact(v, limit) for v in value[:60]]
        return items + [f"… [{len(value) - 60} more items]"] if len(value) > 60 else items
    return value


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one server tool in-process. Always returns a dict; a failure is {"error": ...}."""
    import server

    if name in DENY:
        return {"error": f"{name} is not available in Studio"}
    try:
        result = _run(lambda: server.mcp.call_tool(name, arguments or {}))
    except Exception as exc:
        return {"error": str(exc)[:600]}
    blocks = getattr(result, "content", None)
    if blocks is None and isinstance(result, tuple):  # (content, structured) on some SDK versions
        blocks = result[0]
    texts = [str(getattr(b, "text", "")) for b in (blocks or []) if getattr(b, "type", "") == "text"]
    text = "\n".join(t for t in texts if t)
    try:
        data = json.loads(text)
    except ValueError:
        data = {"text": text}
    if not isinstance(data, dict):
        data = {"result": data}
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        data.setdefault("error", text[:600] or "tool failed")
    return data


# Read first, so a long result is cut in its bulk and never in its verdict.
FIRST_KEYS = ("success", "status", "final_status", "error", "error_code", "error_message", "questions", "look_again",
              "blocking_reasons", "file_id", "dxf_url", "svg_url", "preview_url", "next_tool", "speak")


def result_text(data: dict[str, Any]) -> str:
    ordered = {k: data[k] for k in FIRST_KEYS if k in data}
    ordered.update((k, v) for k, v in data.items() if k not in ordered)
    text = json.dumps(compact(ordered), ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + "… [truncated]"


# --- providers --------------------------------------------------------------------------------
# One transcript, two wire formats. Transcript items:
#   {"role": "user", "text": str, "image": {"media": "image/png", "data": base64} | None}
#   {"role": "assistant", "text": str, "calls": [{"id", "name", "arguments": dict}]}
#   {"role": "tool", "id": str, "name": str, "text": str}

def _openai_messages(system: str, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for item in transcript:
        if item["role"] == "user":
            if item.get("image"):
                img = item["image"]
                out.append({"role": "user", "content": [
                    {"type": "text", "text": item["text"]},
                    {"type": "image_url", "image_url": {"url": f"data:{img['media']};base64,{img['data']}"}},
                ]})
            else:
                out.append({"role": "user", "content": item["text"]})
        elif item["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": item.get("text") or ""}
            if item.get("calls"):
                msg["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}} for c in item["calls"]]
            out.append(msg)
        else:
            out.append({"role": "tool", "tool_call_id": item["id"], "content": item["text"]})
    return out


def openai_step(api_key: str, model: str, system: str, transcript: list[dict[str, Any]], tools: list[dict[str, Any]], base_url: str = "") -> dict[str, Any]:
    from llm_client import _OPENAI_IDS, _http_json, _tokens, output_cap
    from llm_keys import LOCAL_PREFIX

    local_name = str(model)[len(LOCAL_PREFIX):] if str(model).startswith(LOCAL_PREFIX) else ""
    body: dict[str, Any] = {
        "model": local_name or _OPENAI_IDS.get(model, model),
        "messages": _openai_messages(system, transcript),
        "tools": [{"type": "function", "function": t} for t in tools],
    }
    if local_name or model in _OPENAI_IDS:
        body["temperature"] = 0.2
        body["max_tokens"] = output_cap()
    else:
        body["max_completion_tokens"] = max(output_cap(), 8000)
    data = _http_json((base_url or "https://api.openai.com/v1") + "/chat/completions",
                      headers={"authorization": f"Bearer {api_key}"}, body=body, timeout=600.0 if base_url else 120.0)
    choice = (data.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    calls = []
    for i, call in enumerate(msg.get("tool_calls") or []):
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {"_unparsed": str(fn.get("arguments"))[:400]}
        calls.append({"id": str(call.get("id") or f"call_{i}"), "name": str(fn.get("name") or ""), "arguments": args if isinstance(args, dict) else {}})
    return {"text": str(msg.get("content") or ""), "calls": calls, "usage": _tokens(data.get("usage"), "prompt_tokens", "completion_tokens")}


def _anthropic_messages(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in transcript:
        if item["role"] == "user":
            content: list[dict[str, Any]] = []
            if item.get("image"):
                img = item["image"]
                content.append({"type": "image", "source": {"type": "base64", "media_type": img["media"], "data": img["data"]}})
            content.append({"type": "text", "text": item["text"]})
            out.append({"role": "user", "content": content})
        elif item["role"] == "assistant":
            content = [{"type": "text", "text": item["text"]}] if item.get("text") else []
            content += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]} for c in item.get("calls") or []]
            out.append({"role": "assistant", "content": content or [{"type": "text", "text": "…"}]})
        else:
            block = {"type": "tool_result", "tool_use_id": item["id"], "content": item["text"]}
            if out and out[-1]["role"] == "user" and all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                out[-1]["content"].append(block)  # results of one turn travel in one user message
            else:
                out.append({"role": "user", "content": [block]})
    return out


def anthropic_step(api_key: str, model: str, system: str, transcript: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    from llm_client import _ANTHROPIC_IDS, _http_json, _tokens, output_cap

    specs = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    if specs:
        # The tool list and the system prompt never change within a request: cache them.
        specs[-1]["cache_control"] = {"type": "ephemeral"}
    body = {
        "model": _ANTHROPIC_IDS.get(model, model),
        "max_tokens": max(output_cap(), 8000),
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "tools": specs,
        "messages": _anthropic_messages(transcript),
    }
    data = _http_json("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, body=body, timeout=180.0)
    if data.get("stop_reason") == "refusal":
        raise ValueError("The model declined this request")
    blocks = [b for b in data.get("content") or [] if isinstance(b, dict)]
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    tokens = _tokens(usage, "input_tokens", "output_tokens")
    tokens["cache_read_tokens"] = int(usage.get("cache_read_input_tokens") or 0)
    tokens["cache_write_tokens"] = int(usage.get("cache_creation_input_tokens") or 0)
    return {
        "text": "\n".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text"),
        "calls": [{"id": str(b.get("id")), "name": str(b.get("name") or ""), "arguments": b.get("input") if isinstance(b.get("input"), dict) else {}} for b in blocks if b.get("type") == "tool_use"],
        "usage": tokens,
    }


def model_step(model: str, system: str, transcript: list[dict[str, Any]], tools: list[dict[str, Any]], key_owner: str = "") -> dict[str, Any]:
    """One model turn through the right provider, with the workshop's or the user's own key."""
    from llm_client import provider_for_model
    from llm_keys import get_raw_key, own_endpoint

    provider = provider_for_model(model)
    if key_owner:
        from llm_keys import get_user_key

        api_key = get_user_key(key_owner, provider)
        if not api_key:
            raise ValueError(f"Kendi {provider} anahtarın bulunamadı (Hesap → Kendi AI anahtarım)")
    else:
        api_key = get_raw_key(provider)
        if not api_key:
            raise ValueError(f"No {provider} API key configured (Account → LLM or env)")
    if provider == "local":
        return openai_step(api_key, model, system, transcript, tools, base_url=own_endpoint(model))
    if provider == "openai":
        return openai_step(api_key, model, system, transcript, tools)
    return anthropic_step(api_key, model, system, transcript, tools)


# --- the loop ---------------------------------------------------------------------------------

def system_text() -> str:
    import server

    return str(getattr(server.mcp, "instructions", "") or "").strip() + "\n" + STUDIO_RULES


def _limit(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def _step_note(name: str, arguments: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """What a person needs to follow one tool call, without the payload."""
    note: dict[str, Any] = {"tool": name, "ok": not data.get("error") and data.get("success") is not False}
    for key in ("final_status", "file_id", "error", "error_code"):
        if data.get(key):
            note[key] = str(data[key])[:200]
    look = data.get("look_again") or data.get("blocking_reasons")
    if isinstance(look, list) and look:
        note["notes"] = [str(x)[:200] for x in look[:4]]
    keys = sorted(arguments)[:8]
    if keys:
        note["arguments"] = keys
    return note


def run_agent(
    request: str,
    *,
    model: str,
    key_owner: str = "",
    image: dict[str, str] | None = None,
    thickness: Any = None,
    choices: dict[str, Any] | None = None,
    step: Callable[..., dict[str, Any]] | None = None,
    tool: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """Let the model work on one request with the server's tools until it answers in words.

    `choices` are project settings the user already made in the Studio (material, holding
    nicks, texts…): the model passes them on instead of asking again.
    Returns {success, message, steps, file_id, final_status, design, dxf_url, questions,
    usage, stopped}.
    `step`, `tool`, `tools` and `system` are injectable for tests.
    """
    from ai_cost import usage_cost

    step = step or model_step
    tool = tool or call_tool
    tools = tools if tools is not None else tool_specs()
    system = system if system is not None else system_text()
    known = {t["name"] for t in tools}
    max_steps = int(_limit("LASERMCP_AGENT_MAX_STEPS", 12))
    max_usd = _limit("LASERMCP_AGENT_MAX_USD", 0.50)

    text = str(request or "").strip() or "Build what the picture shows."
    if thickness not in (None, ""):
        text += f"\nMaterial thickness_mm={float(thickness):g}"
    if choices:
        text += "\nProject choices already made (pass them in parameters, do not ask again): " + json.dumps(choices, ensure_ascii=False)
    transcript: list[dict[str, Any]] = [{"role": "user", "text": text, "image": image}]
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "usd": 0.0}
    steps: list[dict[str, Any]] = []
    design: dict[str, Any] = {}
    questions: list[Any] = []
    message, stopped = "", ""
    nudges = 0

    for turn in range(1, max_steps + 1):
        reply = step(model, system, transcript, tools, key_owner)
        used = reply.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            usage[key] += int(used.get(key) or 0)
        usage["usd"] = round(usage["usd"] + float(usage_cost(model, used.get("input_tokens") or 0, used.get("output_tokens") or 0, used.get("cache_read_tokens") or 0, used.get("cache_write_tokens") or 0)), 6)
        calls = reply.get("calls") or []
        transcript.append({"role": "assistant", "text": str(reply.get("text") or ""), "calls": calls})
        if reply.get("text") and calls:
            steps.append({"say": str(reply["text"])[:600]})
        if not calls:
            message = str(reply.get("text") or "").strip()
            if not message and nudges < 2 and turn < max_steps:
                # An empty turn (a small model that lost the thread): ask once more, plainly.
                nudges += 1
                transcript.append({"role": "user", "text": "Continue: call the next tool, or give your final answer.", "image": None})
                continue
            break
        for call in calls:
            name, arguments = call["name"], call.get("arguments") or {}
            data = tool(name, arguments) if name in known else {"error": f"unknown tool {name}; use one of the listed tools"}
            transcript.append({"role": "tool", "id": call["id"], "name": name, "text": result_text(data)})
            steps.append(_step_note(name, arguments, data))
            if data.get("file_id") and data.get("final_status"):
                design = data
            questions = data["questions"] if data.get("status") == "NEEDS_INPUT" and isinstance(data.get("questions"), list) else []
        if usage["usd"] > max_usd:
            stopped = f"cost limit ${max_usd:.2f} reached"
            break
    else:
        stopped = f"step limit {max_steps} reached"

    status = str(design.get("final_status") or "")
    return {
        "success": bool(design) and status not in {"", "BLOCKED", "FAIL"},
        "message": message or (f"Stopped: {stopped}." if stopped else ""),
        "steps": steps,
        "turns": turn,
        "file_id": design.get("file_id"),
        "final_status": status or "BLOCKED",
        "design": design,
        "dxf_url": design.get("dxf_url"),
        "svg_url": design.get("svg_url"),
        "questions": questions,
        "usage": usage,
        "stopped": stopped,
    }
