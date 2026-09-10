"""Laser mcp — HTTP UI + MCP. No shell tools."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import boxes_adapter as boxespy
import payas_cad

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))
PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()
IS_VERCEL = os.environ.get("VERCEL") == "1"
WEB_DIR = Path(__file__).resolve().parent / "web"
PUBLIC_PATHS = {"/", "/health"}
MCP_TOOLS = [
    "plan_laser_job",
    "create_from_reference",
    "create_design",
    "payas_defaults",
    "list_cad_tools",
    "get_generator_schema",
    "generate_svg",
    "validate_svg",
    "validate_assembly",
    "render_preview",
    "create_traffic_light",
    "create_robot_bank",
    "create_drawing_robot",
    "create_product_box",
    "create_yacht",
    "create_astronaut",
]

mcp = MCPServer(
    "Laser mcp",
    instructions=(
        "You are Payas STEM laser CAD at https://mcp.metehanavci.com/mcp. "
        "This server is a toolbox, not a catalog. Never ask for a new kit or MCP tool. "
        "Never write SVG or DXF yourself and never flip, rotate, or mirror geometry. "
        "Never offer to prepare a file outside this server. "
        "Preferred tools: plan_laser_job, create_design, create_from_reference, "
        "validate_assembly, validate_svg, payas_defaults. "
        "generate_svg only if the plan names a Boxes.py class. Named create_* only if the plan names that Payas product. "
        "For ANY image of a thing to build: (1) look at the photo and describe parts, "
        "(2) call plan_laser_job with user_request, what_you_see, has_photo=true, "
        "(3) execute next_tool. If that is create_design, the call IS the drawing: "
        "Boxes.py compiles your primitives. method=compose_primitives and generator=create_design "
        "means success — not a missed mill kit and not a Boxes.py catalog class. "
        "Door/window are slots cut into the front wall, not separate sliding parts. "
        "If the user stated a size, use it. Else pick ONE photo length and pass "
        "parameters.reference={feature, mm, drawn_mm} so the whole recipe scales. "
        "A 4-blade rotor is type=propeller, not a disc. Odd silhouettes are type=contour with points in mm. "
        "First uncalibrated laser: add {type:coupon} once (FingerJoint dry-fit + 100 mm bar). Do not add it to every mill. "
        "create_from_reference only 2D-traces artwork or etches a photo onto a jigsaw. "
        "Do not skip the plan. Do not use number_match_puzzle unless the plan says so. "
        "create_design returns assembly (f/F, shaft, slots, gable seating) and nesting (translation-only pack on 1500×3000). "
        "If assembly.ok or ready_to_cut is false, fix primitives and call create_design again; do not tell the user to cut. "
        "Defaults: 3 mm poplar, kerf 0.15 mm, 1500×3000 mm bed, SVG, optional DXF, "
        "cut #FF0000, etch #000000, LaserCAD Y-up. "
        "Notches and closed cuts keep ~1 mm holding nicks so pieces do not fall; do not omit them."
    ),
)


def _public_base(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


def _tool_public_base() -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    vercel = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
    if vercel:
        if vercel.startswith("http://") or vercel.startswith("https://"):
            return vercel.rstrip("/")
        return f"https://{vercel}".rstrip("/")
    return f"http://{HOST}:{PORT}"


def _error(exc: Exception, status: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": str(exc)}, status_code=status)


def _token_ok(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    left = provided.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        hmac.compare_digest(right, right)
        return False
    return hmac.compare_digest(left, right)


def _extract_token(scope: dict[str, Any]) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() == "authorization":
            text = value.decode("latin-1").strip()
            if text.lower().startswith("bearer "):
                return text[7:].strip()
            return None
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("token") or []
    return values[0] if values else None


class McpOriginAlias:
    """Claude/ChatGPT often POST the origin URL. Keep GET / as the UI; send other methods to /mcp."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path") or ""
            method = (scope.get("method") or "GET").upper()
            if path in {"", "/"} and method not in {"GET", "HEAD"}:
                scope = dict(scope)
                scope["path"] = "/mcp"
                query = scope.get("query_string") or b""
                raw = b"/mcp" + ((b"?" + query) if query else b"")
                scope["raw_path"] = raw
        await self.app(scope, receive, send)


class BearerGate:
    """Protect /mcp, /api, /files when MCP_AUTH_TOKEN is set. UI and /health stay public."""

    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token or None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        method = scope.get("method") or "GET"
        if method == "OPTIONS" or path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        if _token_ok(_extract_token(scope), self.token):
            await self.app(scope, receive, send)
            return
        body = b'{"error":"unauthorized"}'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"www-authenticate", b'Bearer realm="Laser mcp"'),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})


@mcp.tool(
    description=(
        "STEP 2 after you looked at the photo: Laser MCP teaches the toolbox grammar and how to scale. "
        "Pass user_request, what_you_see (parts you see: walls, roof, holes, discs), has_photo, want_dxf. "
        "Then execute next_tool. If next_tool is create_design, overwrite millimetres from the photo "
        "or set parameters.reference. Never ask for a new kit. Do not draw SVG yourself."
    )
)
def plan_laser_job(
    user_request: str,
    what_you_see: str = "",
    has_photo: bool = False,
    want_dxf: bool = False,
) -> dict[str, Any]:
    from job_planner import plan_laser_job as _plan

    return _plan(user_request, what_you_see, has_photo, want_dxf)


@mcp.tool(
    description=(
        "Toolbox compiler. This IS the drawing tool — not a catalog preset. "
        "Passing primitives does not select a 'toolbox generator'; Boxes.py cuts those parts. "
        "primitives: box (finger-joint walls+floor), panel (motor plate, solar, roof), "
        "disc (washer/shaft adapter), triangle (roof support), propeller (n-blade rotor), "
        "contour (closed points [[x,y],...] mm), coupon (kerf test). "
        "Door/window = slots on box.walls.front, not type=slot. "
        "Scale with parameters.scale or parameters.reference={feature, mm, drawn_mm}. "
        "preset=jigsaw_puzzle or number_match_puzzle only when the plan says so. "
        "Never request a new tool. Never hand-write SVG."
    )
)
def create_design(
    preset: str | None = None,
    primitives: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
    svg: str | None = None,
) -> dict[str, Any]:
    return payas_cad.create_design(
        preset=preset,
        primitives=primitives,
        parameters=parameters,
        svg=svg,
        public_base_url=_tool_public_base(),
    )


@mcp.tool(
    description=(
        "2D artwork only: vectorize a photo or etch it onto a jigsaw. "
        "Pass compressed JPEG image_base64 plus next_arguments from the plan. "
        "To build walls/roofs/propellers, use create_design (type=propeller or type=contour), not this tool. "
        "layout=jigsaw or trace. format=svg or both. Then validate_svg."
    )
)
def create_from_reference(
    image_base64: str,
    width_mm: float = 200.0,
    height_mm: float | None = None,
    style: str = "cut_and_etch",
    invert: bool | None = None,
    threshold: int = 0,
    layout: str = "trace",
    rows: int = 10,
    cols: int = 10,
    seed: int = 1,
    format: str = "svg",
) -> dict[str, Any]:
    try:
        return payas_cad.create_from_reference(
            image_base64=image_base64,
            width_mm=width_mm,
            height_mm=height_mm,
            style=style,
            invert=invert,
            threshold=threshold,
            layout=layout,
            rows=rows,
            cols=cols,
            seed=seed,
            format=format,
            public_base_url=_tool_public_base(),
        )
    except Exception as exc:
        return payas_cad._mcp(
            {
                "ready_to_cut": False,
                "hint": (
                    "Compress the photo to ~1200px JPEG and retry. "
                    "This tool only traces 2D artwork. For a mill/house/model, call plan_laser_job "
                    "then create_design with box/panel/disc primitives."
                ),
                "look_again": [str(exc)],
            }
        )


@mcp.tool(description="Payas STEM defaults: 3mm kavak, kerf 0.15, 1500x3000, SVG.")
def payas_defaults() -> dict[str, Any]:
    return boxespy.payas_defaults()


@mcp.tool(description="List the toolbox. Look, plan_laser_job, then create_design primitives. Do not request new tools.")
def list_cad_tools() -> dict[str, Any]:
    return payas_cad.list_cad_tools()


@mcp.tool(description="Parameter schema for one Boxes.py class. Not used for puzzles or uploaded pictures.")
def get_generator_schema(generator: str) -> dict[str, Any]:
    return boxespy.get_generator_schema(generator)


@mcp.tool(description="Boxes.py class SVG only (ABox, TypeTray, …). Use only if plan_laser_job next_tool is generate_svg. Photos of things to build: plan_laser_job then create_design primitives.")
def generate_svg(generator: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    return payas_cad._mcp(boxespy.generate_svg(generator, parameters, public_base_url=_tool_public_base()))


@mcp.tool(description="Validate a generated SVG: XML, 1500×3000 bed, nested part spacing. Loads assembly report if present.")
def validate_svg(file_id: str) -> dict[str, Any]:
    return payas_cad._mcp(boxespy.validate_svg(file_id))


@mcp.tool(
    description=(
        "Mechanical fit + assembly check. Pass primitives to check a recipe before cut, "
        "or file_id after create_design. Fingers must be complementary f/F of the same length (Boxes.py). "
        "Shaft holes on opposite walls must share diameter and height. ready_to_cut must be true before cutting."
    )
)
def validate_assembly(
    file_id: str | None = None,
    primitives: list[Any] | None = None,
) -> dict[str, Any]:
    return payas_cad.validate_assembly(file_id=file_id, primitives=primitives)


@mcp.tool(description="Return a preview URL for a previously generated SVG.")
def render_preview(file_id: str) -> dict[str, Any]:
    return boxespy.render_preview(file_id, public_base_url=_tool_public_base())


@mcp.tool(description="Payas STEM trafik lambası SVG. led=LED çapı mm.")
def create_traffic_light(
    thickness: float = 3.0,
    burn: float = 0.15,
    led: float | None = None,
    base_width: float | None = None,
    base_depth: float | None = None,
    base_height: float | None = None,
    tower_height: float | None = None,
) -> dict[str, Any]:
    return payas_cad.create_traffic_light(
        thickness=thickness,
        burn=burn,
        led=led,
        base_width=base_width,
        base_depth=base_depth,
        base_height=base_height,
        tower_height=tower_height,
        public_base_url=_tool_public_base(),
    )


@mcp.tool(description="Payas STEM robot kumbara (PayasRobot) kesim SVG.")
def create_robot_bank() -> dict[str, Any]:
    return payas_cad.create_robot_bank(public_base_url=_tool_public_base())


@mcp.tool(description="Payas STEM ressam/çizim robotu kesim SVG.")
def create_drawing_robot() -> dict[str, Any]:
    return payas_cad.create_drawing_robot(public_base_url=_tool_public_base())


@mcp.tool(description="Basit ürün kutusu SVG. x, y, h mm, dış ölçü.")
def create_product_box(
    x: float = 220,
    y: float = 160,
    h: float = 50,
    thickness: float = 3.0,
    burn: float = 0.15,
) -> dict[str, Any]:
    return payas_cad.create_product_box(
        x=x, y=y, h=h, thickness=thickness, burn=burn,
        public_base_url=_tool_public_base(),
    )


@mcp.tool(description="Payas STEM statik yat kiti kesim SVG.")
def create_yacht() -> dict[str, Any]:
    return payas_cad.create_yacht(public_base_url=_tool_public_base())


@mcp.tool(description="Payas STEM açık şase astronot kiti kesim SVG.")
def create_astronaut() -> dict[str, Any]:
    return payas_cad.create_astronaut(public_base_url=_tool_public_base())


@mcp.custom_route("/", methods=["GET"])
async def ui(request: Request) -> Response:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> Response:
    health = boxespy.health_status()
    return JSONResponse(
        {
            "name": "Laser mcp",
            "status": health["status"],
            "mcp": "/mcp",
            "ui": "/",
            "auth_required": bool(AUTH_TOKEN),
            "boxes": health["boxes"],
            "generator_count": health["generator_count"],
            "defaults": boxespy.PAYAS_DEFAULTS,
            "tools": MCP_TOOLS,
            "cad_products": payas_cad.CAD_PRODUCTS,
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    payload = boxespy.health_status()
    payload["auth_required"] = bool(AUTH_TOKEN)
    status = 200 if payload["status"] == "ok" else 503
    return JSONResponse(payload, status_code=status)


@mcp.custom_route("/api/generators", methods=["GET"])
async def api_generators(request: Request) -> Response:
    group = request.query_params.get("group") or None
    return JSONResponse(boxespy.list_generators(group))


@mcp.custom_route("/api/schema", methods=["GET"])
async def api_schema(request: Request) -> Response:
    generator = request.query_params.get("generator", "")
    try:
        return JSONResponse(boxespy.get_generator_schema(generator))
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/generate", methods=["POST"])
async def api_generate(request: Request) -> Response:
    try:
        body = await request.json()
        generator = body.get("generator")
        parameters = body.get("parameters") or {}
        result = boxespy.generate_svg(generator, parameters, public_base_url=_public_base(request))
        return JSONResponse(result)
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/validate", methods=["POST"])
async def api_validate(request: Request) -> Response:
    try:
        body = await request.json()
        return JSONResponse(boxespy.validate_svg(body.get("file_id") or boxespy.LATEST_SVG))
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/preview", methods=["GET"])
async def api_preview(request: Request) -> Response:
    file_id = request.query_params.get("file_id") or boxespy.LATEST_SVG
    try:
        return JSONResponse(boxespy.render_preview(file_id, public_base_url=_public_base(request)))
    except FileNotFoundError as exc:
        return _error(exc, 404)
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/cad/products", methods=["GET"])
async def api_cad_products(request: Request) -> Response:
    return JSONResponse(payas_cad.list_cad_tools())


@mcp.custom_route("/api/cad/design", methods=["POST"])
async def api_cad_design(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        payload = body if isinstance(body, dict) else {}
        params = dict(payload.get("parameters") or {}) if isinstance(payload.get("parameters"), dict) else {}
        for key in ("count", "card_w", "card_h", "columns", "width_mm", "height_mm", "rows", "cols", "seed", "format"):
            if key in payload and key not in params:
                params[key] = payload[key]
        return JSONResponse(
            payas_cad.create_design(
                preset=payload.get("preset") or params.get("preset"),
                primitives=payload.get("primitives") or params.get("primitives"),
                parameters=params,
                svg=payload.get("svg") or params.get("svg"),
                public_base_url=_public_base(request),
            )
        )
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/cad/from_reference", methods=["POST"])
async def api_from_reference(request: Request) -> Response:
    try:
        ctype = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in ctype:
            form = await request.form()
            upload = form.get("image")
            image_bytes = await upload.read() if upload is not None and hasattr(upload, "read") else None
            width_mm = float(form.get("width_mm") or 200)
            height_raw = form.get("height_mm")
            height_mm = float(height_raw) if height_raw not in (None, "", "0") else None
            style = str(form.get("style") or "cut_and_etch")
            invert_raw = form.get("invert")
            invert = None if invert_raw in (None, "", "auto") else str(invert_raw).lower() in {"1", "true", "yes"}
            threshold = int(form.get("threshold") or 0)
            layout = str(form.get("layout") or "trace")
            rows = int(form.get("rows") or 10)
            cols = int(form.get("cols") or 10)
            fmt = str(form.get("format") or "svg")
            result = payas_cad.create_from_reference(
                image_bytes=image_bytes,
                width_mm=width_mm,
                height_mm=height_mm,
                style=style,
                invert=invert,
                threshold=threshold,
                layout=layout,
                rows=rows,
                cols=cols,
                format=fmt,
                public_base_url=_public_base(request),
            )
            return JSONResponse(result)
        body = await request.json()
        params = body.get("parameters") if isinstance(body.get("parameters"), dict) else {}
        merged = {**params, **{k: body[k] for k in body if k != "parameters"}}
        height_raw = merged.get("height_mm")
        height_mm = float(height_raw) if height_raw not in (None, "", 0, "0") else None
        result = payas_cad.create_from_reference(
            image_base64=merged.get("image_base64"),
            width_mm=float(merged.get("width_mm") or 200),
            height_mm=height_mm,
            style=str(merged.get("style") or "cut_and_etch"),
            invert=merged.get("invert"),
            threshold=int(merged.get("threshold") or 0),
            layout=str(merged.get("layout") or "trace"),
            rows=int(merged.get("rows") or 10),
            cols=int(merged.get("cols") or 10),
            seed=int(merged.get("seed") or 1),
            format=str(merged.get("format") or "svg"),
            public_base_url=_public_base(request),
        )
        return JSONResponse(result)
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/cad/{product_id}", methods=["POST"])
async def api_cad_create(request: Request) -> Response:
    product_id = request.path_params["product_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return JSONResponse(
            payas_cad.create_product(
                product_id,
                body.get("parameters") if isinstance(body, dict) else {},
                public_base_url=_public_base(request),
            )
        )
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/files/{filename}", methods=["GET"])
async def serve_file(request: Request) -> Response:
    filename = request.path_params["filename"]
    try:
        path = boxespy._safe_output_file(filename)
    except FileNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=404)
    except ValueError:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    suffix = path.suffix.lower()
    media = "image/svg+xml" if suffix == ".svg" else "image/vnd.dxf" if suffix == ".dxf" else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=path.name)


def create_asgi_app():
    """ASGI app for local uvicorn and Vercel (`app` export)."""
    kwargs: dict[str, Any] = {
        "streamable_http_path": "/mcp",
        "host": "0.0.0.0" if IS_VERCEL else HOST,
        "stateless_http": IS_VERCEL,
        "max_request_body_size": 20 * 1024 * 1024,
    }
    if IS_VERCEL:
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
    starlette_app = mcp.streamable_http_app(**kwargs)
    return McpOriginAlias(BearerGate(starlette_app, AUTH_TOKEN))


app = create_asgi_app()


def main() -> None:
    import uvicorn

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
