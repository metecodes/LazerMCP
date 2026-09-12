"""Laser mcp — HTTP UI + MCP. No shell tools."""

from __future__ import annotations

import hmac
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import boxes_adapter as boxespy
import payas_cad


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))
PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "")
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()
IS_VERCEL = os.environ.get("VERCEL") == "1"
WEB_DIR = Path(__file__).resolve().parent / "web"
BRAND_FILES = {
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/favicon-32.png": ("favicon-32.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/og.png": ("og.png", "image/png"),
    "/site.webmanifest": ("site.webmanifest", "application/manifest+json"),
    "/nav-auth.js": ("nav-auth.js", "text/javascript; charset=utf-8"),
}
PUBLIC_PATHS = {
    "/",
    "/health",
    "/dashboard",
    "/app",
    "/workshop",
    "/account",
    "/connect",
    "/auth/callback",
    "/auth/google",
    "/api/plans",
    "/api/beta",
    "/api/demo",
    "/api/auth/config",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/account",
    *BRAND_FILES,
}
PUBLIC_PREFIXES = ("/demo/", "/oauth/", "/.well-known/", "/auth/")
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
    "studio",
    "create_traffic_light",
    "create_robot_bank",
    "create_drawing_robot",
    "create_product_box",
    "create_yacht",
    "create_astronaut",
]

mcp = MCPServer(
    "LaserMCP",
    instructions=(
        "You are Payas STEM laser CAD at https://mcp.metehanavci.com/mcp. "
        "This server is a toolbox, not a catalog. Never ask for a new kit or MCP tool. "
        "Never write SVG or DXF yourself and never flip, rotate, or mirror geometry. "
        "Never offer to prepare a file outside this server. "
        "Pipeline (runs inside create_design — do not skip, do not add extra tools): "
        "Designer → Reviewer → Repair → Reviewer → Final Gate → SVG. "
        "Paste speak verbatim as the status card. "
        "final_status is BLOCKED | PROTOTYPE READY. Software never authorizes production. "
        "Physical Kerf Test, Physical Assembly, Movement Test, and After Assembly Use stay NOT VERIFIED. "
        "AUTHORIZED OUTPUT is Prototype SVG. PRODUCTION EXPORT is BLOCKED. "
        "Never say LAZER KESİME HAZIR or production-ready. "
        "Preferred tools: plan_laser_job, create_design, create_from_reference, "
        "validate_assembly, validate_svg, payas_defaults. "
        "generate_svg only if the plan names a Boxes.py class. Named create_* only if the plan names that Payas product. "
        "For ANY image of a thing to build: (1) look at the photo and describe parts, "
        "(2) call plan_laser_job with user_request, what_you_see, has_photo=true, "
        "(3) execute next_tool. If that is create_design, the call IS the drawing: "
        "Boxes.py compiles your primitives, then the reviewer/repair/gate run automatically. "
        "method=compose_primitives and generator=create_design "
        "means the designer step ran — not a missed mill kit and not a Boxes.py catalog class. "
        "Door/window are slots cut into the front wall, not separate sliding parts. "
        "If the user stated a size, use it. Else pick ONE photo length (or count 3 mm plywood edges) and pass "
        "parameters.reference={feature, mm, drawn_mm} so the whole recipe scales. "
        "Copy what_you_see into parameters.what_you_see. "
        "After a coupon cut, pass the human's measured_bar_mm — never invent it. "
        "physical_assembly, movement_test, and use_test are human-only; inventing them is a FAIL. "
        "A 4-blade rotor is type=propeller, not a disc. Odd silhouettes are type=contour with points in mm. "
        "First uncalibrated laser: add {type:coupon} once (FingerJoint dry-fit + 100 mm bar). Do not add it to every mill. "
        "Pass parameters.material (poplar_3mm|poplar_4mm|mdf_3mm|acrylic_3mm) and parameters.machine "
        "(payas_workshop|desktop_400|lasercad_900). Do not invent kerf. "
        "MCP writes the kit material list (bom / MATERIALS (MCP)). Never invent hardware. "
        "Optional parameters.project names the job for version history. "
        "create_from_reference only 2D-traces artwork or etches a photo onto a jigsaw. "
        "Do not skip the plan. Do not use number_match_puzzle unless the plan says so. "
        "If final_status is BLOCKED, read look_again, fix primitives, call create_design again. "
        "Do not invent a PASS. Working SVG is not a cuttable product until the gate says so. "
        "Defaults: 3 mm poplar, kerf 0.15 mm, 1500×3000 mm bed, SVG + DXF, "
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


def _auth_on() -> bool:
    try:
        from keys import auth_required

        return auth_required()
    except Exception:
        return bool(AUTH_TOKEN)


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


def _request_host(scope: dict[str, Any]) -> str:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() == "host":
            return value.decode("latin-1").split(":")[0].lower()
    return ""


def _extract_token(scope: dict[str, Any]) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() == "authorization":
            text = value.decode("latin-1").strip()
            if text.lower().startswith("bearer "):
                return text[7:].strip()
            return None
    if _request_host(scope) not in {"127.0.0.1", "localhost", "::1"}:
        return None
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    values = query.get("token") or []
    return values[0] if values else None


def _next_origins(request: Request) -> list[str]:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    origins = [f"{proto}://{host}"]
    if PUBLIC_BASE_URL:
        origins.append(PUBLIC_BASE_URL.rstrip("/"))
    return origins


def _safe_next(raw: str, request: Request) -> str:
    from supabase_auth import safe_next_path

    return safe_next_path(raw, origins=_next_origins(request))


def _redirect(url: str, *, status: int = 302) -> Response:
    """HTML + Location. Avoid Starlette RedirectResponse — Vercel 500s when it follows 302."""
    safe = html.escape(url, quote=True)
    body = (
        "<!doctype html><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='0;url={safe}'>"
        f"<a href='{safe}'>Continue</a>"
        f"<script>location.replace({json.dumps(url)})</script>"
    )
    return Response(
        content=body,
        status_code=status,
        media_type="text/html; charset=utf-8",
        headers={"Location": url, "Cache-Control": "no-store"},
    )


def _google_authorize_url(request: Request, nxt: str = "") -> str:
    from supabase_auth import supabase_anon_key, supabase_url

    redirect_to = f"{_public_base(request)}/auth/callback"
    if nxt:
        redirect_to += "?next=" + quote(nxt, safe="")
    return (
        f"{supabase_url()}/auth/v1/authorize?provider=google"
        f"&redirect_to={quote(redirect_to, safe='')}"
        f"&apikey={quote(supabase_anon_key(), safe='')}"
    )


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
    """Protect /mcp, /api, /files when MCP_AUTH_TOKEN or hashed keys exist. UI and /health stay public."""

    def __init__(self, app, token: str | None = None):
        self.app = app
        self.token = token or None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        method = scope.get("method") or "GET"
        if method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return
        from keys import auth_required, current_auth, resolve_bearer

        if not auth_required():
            await self.app(scope, receive, send)
            return
        key = resolve_bearer(_extract_token(scope))
        if not key:
            try:
                from supabase_auth import principal_from_identity, session_user

                cookie_header = ""
                for hk, hv in scope.get("headers") or []:
                    if hk.decode("latin-1").lower() == "cookie":
                        cookie_header = hv.decode("latin-1")
                        break
                sid = ""
                for part in cookie_header.split(";"):
                    name, _, val = part.strip().partition("=")
                    if name == "lmcp_sid":
                        sid = val
                        break
                stored = session_user(sid)
                if stored:
                    key = principal_from_identity(stored, stored)
            except Exception:
                key = None
        if not key:
            host = ""
            for hk, hv in scope.get("headers") or []:
                if hk.decode("latin-1").lower() == "host":
                    host = hv.decode("latin-1")
                    break
            proto = "https" if (scope.get("scheme") == "https" or host.endswith("metehanavci.com")) else "http"
            meta = f'{proto}://{host}/.well-known/oauth-protected-resource'.encode("ascii") if host else b""
            body = b'{"error":"unauthorized","look_again":["Sign in with Google or use an organization API key."]}'
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (
                    b"www-authenticate",
                    b'Bearer realm="LaserMCP"' + (b', resource_metadata="' + meta + b'"' if meta else b""),
                ),
            ]
            await send({"type": "http.response.start", "status": 401, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return
        token = current_auth.set(key)
        try:
            await self.app(scope, receive, send)
        finally:
            current_auth.reset(token)


@mcp.tool(
    description=(
        "STEP 2 after you looked at the photo: Laser MCP teaches the toolbox grammar and how to scale. "
        "Pass user_request, what_you_see (parts you see: walls, roof, holes, discs), has_photo, want_dxf. "
        "Then execute next_tool. If next_tool is create_design, overwrite millimetres from the photo "
        "or set parameters.reference. create_design already runs Reviewer → Repair → Final Gate. "
        "Never ask for a new kit. Do not draw SVG yourself."
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
        "Designer + Reviewer + Repair + Final Gate. This IS the drawing tool — not a catalog preset. "
        "Passing primitives does not select a 'toolbox generator'; Boxes.py cuts those parts, "
        "then mechanical review/repair runs until the gate. "
        "primitives: box (finger-joint walls+floor), panel (motor plate, solar, roof), "
        "disc (washer/shaft adapter), triangle (roof support), propeller (n-blade rotor), "
        "contour (closed points [[x,y],...] mm), coupon (kerf test). "
        "Door/window = slots on box.walls.front, not type=slot. "
        "Optional marks: part.markings or {type:marking, target_part} "
        "(kind=text|path|icon|line, x,y,width or height, rotation, align, operation=engrave|cut). "
        "Scale with parameters.scale or parameters.reference={feature, mm, drawn_mm}. "
        "parameters.material / parameters.machine pick profiles. MCP writes bom. "
        "preset=jigsaw_puzzle or number_match_puzzle only when the plan says so. "
        "Paste speak as the gate card. BLOCKED = no authorized SVG. "
        "PROTOTYPE READY = Prototype SVG only; PRODUCTION EXPORT BLOCKED. "
        "Never say LAZER KESİME HAZIR. Never request a new tool. Never hand-write SVG."
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
    try:
        return payas_cad._mcp(boxespy.get_generator_schema(generator))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)]})


@mcp.tool(description="Boxes.py class SVG only (ABox, TypeTray, …). Use only if plan_laser_job next_tool is generate_svg. Photos of things to build: plan_laser_job then create_design primitives.")
def generate_svg(generator: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return payas_cad._mcp(boxespy.generate_svg(generator, parameters, public_base_url=_tool_public_base()))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "ready_to_cut": False})


@mcp.tool(description="Validate a generated SVG: XML, 1500×3000 bed, nested part spacing. Loads assembly report if present.")
def validate_svg(file_id: str) -> dict[str, Any]:
    try:
        return payas_cad._mcp(boxespy.validate_svg(file_id))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "file_id": file_id, "well_formed": False})


@mcp.tool(
    description=(
        "Re-run the mechanical reviewer / final gate. Pass primitives to compile+review a recipe, "
        "or file_id after create_design. Returns design_map, connections, category PASS/WARNING/FAIL, "
        "and the speak gate card. Never say LAZER KESİME HAZIR. PRODUCTION EXPORT stays BLOCKED."
    )
)
def validate_assembly(
    file_id: str | None = None,
    primitives: list[Any] | None = None,
) -> dict[str, Any]:
    return payas_cad.validate_assembly(file_id=file_id, primitives=primitives)


@mcp.tool(description="Return a preview URL for a previously generated SVG.")
def render_preview(file_id: str) -> dict[str, Any]:
    try:
        return payas_cad._mcp(boxespy.render_preview(file_id, public_base_url=_tool_public_base()))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "file_id": file_id})


@mcp.tool(
    description=(
        "Workshop studio — not a kit. action=profiles|calibrate|projects|usage|keys|telemetry. "
        "profiles lists materials/machines. projects lists design versions. "
        "keys with name= creates a token (shown once). Do not invent kerf or hardware."
    )
)
def studio(
    action: str = "profiles",
    name: str = "",
    project_id: str = "",
    role: str = "workshop",
    plan: str = "",
) -> dict[str, Any]:
    from studio import studio_action

    return payas_cad._mcp(studio_action(action, name=name, project_id=project_id, role=role, plan=plan))


def _named_kit(fn, **kwargs):
    try:
        return payas_cad._mcp(fn(public_base_url=_tool_public_base(), **kwargs))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "ready_to_cut": False})


@mcp.tool(description="Payas STEM trafik lambası SVG. led=LED çapı mm.")
def create_traffic_light(
    thickness: float = 3.0,
    burn: float = 0.15,
    led: float | None = None,
    base_width: float | None = None,
    base_depth: float | None = None,
    base_height: float | None = None,
    tower_width: float | None = None,
    tower_depth: float | None = None,
    tower_height: float | None = None,
) -> dict[str, Any]:
    return _named_kit(
        payas_cad.create_traffic_light,
        thickness=thickness,
        burn=burn,
        led=led,
        base_width=base_width,
        base_depth=base_depth,
        base_height=base_height,
        tower_width=tower_width,
        tower_depth=tower_depth,
        tower_height=tower_height,
    )


@mcp.tool(description="Payas STEM robot kumbara (PayasRobot) kesim SVG.")
def create_robot_bank() -> dict[str, Any]:
    return _named_kit(payas_cad.create_robot_bank)


@mcp.tool(description="Payas STEM ressam/çizim robotu kesim SVG.")
def create_drawing_robot() -> dict[str, Any]:
    return _named_kit(payas_cad.create_drawing_robot)


@mcp.tool(description="Basit ürün kutusu SVG. x, y, h mm, dış ölçü.")
def create_product_box(
    x: float = 220,
    y: float = 160,
    h: float = 50,
    thickness: float = 3.0,
    burn: float = 0.15,
) -> dict[str, Any]:
    return _named_kit(payas_cad.create_product_box, x=x, y=y, h=h, thickness=thickness, burn=burn)


@mcp.tool(description="Payas STEM statik yat kiti kesim SVG.")
def create_yacht() -> dict[str, Any]:
    return _named_kit(payas_cad.create_yacht)


@mcp.tool(description="Payas STEM açık şase astronot kiti kesim SVG.")
def create_astronaut() -> dict[str, Any]:
    return _named_kit(payas_cad.create_astronaut)


@mcp.custom_route("/", methods=["GET"])
async def landing(request: Request) -> Response:
    return FileResponse(WEB_DIR / "landing.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/connect", methods=["GET"])
async def connect_page(request: Request) -> Response:
    return FileResponse(WEB_DIR / "connect.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/account", methods=["GET"])
@mcp.custom_route("/auth/callback", methods=["GET"])
async def account_page(request: Request) -> Response:
    return FileResponse(WEB_DIR / "account.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/auth/google", methods=["GET"])
async def auth_google(request: Request) -> Response:
    from supabase_auth import configured

    if not configured():
        return _redirect("/account", status=200)
    try:
        nxt = _safe_next(request.query_params.get("next") or "", request)
        # 200: Vercel follows 302 Location server-side and 500s on supabase.co
        return _redirect(_google_authorize_url(request, nxt), status=200)
    except Exception:
        return _redirect("/account", status=200)


@mcp.custom_route("/app", methods=["GET"])
@mcp.custom_route("/workshop", methods=["GET"])
async def ui(request: Request) -> Response:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(request: Request) -> Response:
    return FileResponse(WEB_DIR / "dashboard.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/favicon.svg", methods=["GET"])
@mcp.custom_route("/favicon.ico", methods=["GET"])
@mcp.custom_route("/favicon-32.png", methods=["GET"])
@mcp.custom_route("/apple-touch-icon.png", methods=["GET"])
@mcp.custom_route("/icon-512.png", methods=["GET"])
@mcp.custom_route("/og.png", methods=["GET"])
@mcp.custom_route("/site.webmanifest", methods=["GET"])
@mcp.custom_route("/nav-auth.js", methods=["GET"])
async def brand_asset(request: Request) -> Response:
    spec = BRAND_FILES.get(request.url.path)
    if not spec:
        return Response(status_code=404)
    name, media = spec
    path = WEB_DIR / name
    if not path.is_file():
        return Response(status_code=404)
    return FileResponse(path, media_type=media)


@mcp.custom_route("/api/demo", methods=["GET"])
async def api_demo(request: Request) -> Response:
    from demo_kits import list_kits

    return JSONResponse(list_kits())


@mcp.custom_route("/demo/{filename}", methods=["GET"])
async def serve_demo(request: Request) -> Response:
    from demo_kits import demo_file

    try:
        path = demo_file(request.path_params["filename"])
    except FileNotFoundError:
        return JSONResponse({"look_again": ["unknown demo file"]}, status_code=404)
    except ValueError:
        return JSONResponse({"look_again": ["invalid filename"]}, status_code=400)
    media = "image/svg+xml" if path.suffix.lower() == ".svg" else "application/octet-stream"
    return FileResponse(path, media_type=media)


@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> Response:
    health = boxespy.health_status()
    return JSONResponse(
        {
            "name": "LaserMCP",
            "status": health["status"],
            "mcp": "/mcp",
            "ui": "/app",
            "landing": "/",
            "auth_required": _auth_on(),
            "dashboard": "/dashboard",
            "boxes": health["boxes"],
            "generator_count": health["generator_count"],
            "defaults": boxespy.PAYAS_DEFAULTS,
            "tools": MCP_TOOLS,
            "cad_products": payas_cad.CAD_PRODUCTS,
            "connect": "/connect",
            "account": "/account",
        }
    )


def _cors(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    response = JSONResponse(payload, status_code=status)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _cookie_secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


async def _oauth_body(request: Request) -> dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in ctype:
        form = await request.form()
        return {str(k): str(v) for k, v in form.items()}
    try:
        raw = await request.json()
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_as_meta(request: Request) -> Response:
    from oauth_mcp import metadata

    return _cors(metadata(_public_base(request)))


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def oauth_rs_meta(request: Request) -> Response:
    from oauth_mcp import resource_metadata

    return _cors(resource_metadata(_public_base(request)))


@mcp.custom_route("/oauth/register", methods=["POST", "OPTIONS"])
async def oauth_register(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors({"ok": True})
    from oauth_mcp import register_client

    try:
        body = await _oauth_body(request)
        return _cors(register_client(body), 201)
    except ValueError as exc:
        return _cors({"error": "invalid_client_metadata", "error_description": str(exc)}, 400)


@mcp.custom_route("/oauth/authorize", methods=["GET"])
async def oauth_authorize(request: Request) -> Response:
    from oauth_mcp import authorize_redirect, issue_code
    from supabase_auth import session_user

    q = request.query_params
    nxt = _safe_next(str(request.url), request)
    user = session_user(request.cookies.get("lmcp_sid"))
    if not user:
        return _redirect("/account?next=" + quote(nxt or "/connect", safe=""))
    try:
        code = issue_code(
            client_id=str(q.get("client_id") or ""),
            redirect_uri=str(q.get("redirect_uri") or ""),
            state=str(q.get("state") or ""),
            challenge=str(q.get("code_challenge") or ""),
            user=user,
        )
        return _redirect(authorize_redirect(str(q.get("redirect_uri") or ""), code, str(q.get("state") or "")))
    except ValueError as exc:
        return _cors({"error": "invalid_request", "error_description": str(exc)}, 400)


@mcp.custom_route("/oauth/token", methods=["POST", "OPTIONS"])
async def oauth_token(request: Request) -> Response:
    if request.method == "OPTIONS":
        return _cors({"ok": True})
    from oauth_mcp import exchange_token

    try:
        return _cors(exchange_token(await _oauth_body(request)))
    except ValueError as exc:
        return _cors({"error": "invalid_grant", "error_description": str(exc)}, 400)


@mcp.custom_route("/api/auth/config", methods=["GET"])
async def api_auth_config(request: Request) -> Response:
    from supabase_auth import public_config

    return JSONResponse(public_config(f"{_public_base(request)}/mcp"))


@mcp.custom_route("/api/auth/session", methods=["POST"])
async def api_auth_session(request: Request) -> Response:
    from supabase_auth import (
        can_mint_keys,
        configured,
        new_session,
        principal_from_identity,
        upsert_user,
        verify_access_token,
    )

    if not configured():
        return JSONResponse({"success": True, "look_again": ["Supabase is not configured."], "configured": False})
    try:
        body = await request.json()
    except Exception:
        body = {}
    token = str((body or {}).get("access_token") or "")
    identity = verify_access_token(token)
    if not identity:
        return JSONResponse({"success": True, "look_again": ["Google sign-in failed."]}, status_code=401)
    stored = upsert_user(identity)
    principal = principal_from_identity(identity, stored)
    response = JSONResponse(
        {
            "success": True,
            "user": principal,
            "can_mint_keys": can_mint_keys(stored),
            "configured": True,
        }
    )
    response.set_cookie(
        "lmcp_sid",
        new_session(stored),
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        secure=_cookie_secure(request),
        path="/",
    )
    return response


@mcp.custom_route("/api/auth/logout", methods=["POST", "GET"])
async def api_auth_logout(request: Request) -> Response:
    response = JSONResponse({"success": True, "signed_out": True})
    response.delete_cookie("lmcp_sid", path="/")
    return response


def _account_usage(user_id: str) -> dict[str, Any]:
    from metering import designs_this_month, usage_summary

    uid = str(user_id or "")
    summary = usage_summary()
    return {
        "total": int((summary.get("by_key") or {}).get(uid, 0)),
        "month": designs_this_month(uid),
    }


@mcp.custom_route("/api/account", methods=["GET"])
async def api_account(request: Request) -> Response:
    from keys import current_auth, list_keys
    from supabase_auth import can_mint_keys, session_user, user_by_id

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return JSONResponse({"success": True, "look_again": ["Sign in with Google."]}, status_code=401)
    stored = user_by_id(str(key.get("id") or "")) or {}
    uid = str(key.get("id") or "")
    return JSONResponse(
        {
            "success": True,
            "user": {
                "id": key.get("id"),
                "name": key.get("name") or stored.get("name"),
                "email": key.get("email") or stored.get("email"),
                "kind": stored.get("kind") or key.get("kind") or "individual",
            },
            "can_mint_keys": can_mint_keys(stored or key),
            "keys": list_keys(owner=uid),
            "usage": _account_usage(uid),
        }
    )


@mcp.custom_route("/api/account/keys", methods=["POST"])
async def api_account_keys(request: Request) -> Response:
    from keys import create_key, current_auth
    from supabase_auth import can_mint_keys, session_user, user_by_id

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return JSONResponse({"success": True, "look_again": ["Sign in with Google."]}, status_code=401)
    stored = user_by_id(str(key.get("id") or "")) or key
    if not can_mint_keys(stored):
        return JSONResponse(
            {
                "success": True,
                "look_again": ["Organization accounts mint API keys. Individuals sign in with Google."],
            }
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    created = create_key(
        str((body or {}).get("name") or "workshop"),
        role="workshop",
        plan="maker",
        owner=str(key.get("id") or ""),
        email=str(key.get("email") or stored.get("email") or ""),
        kind="org",
    )
    return JSONResponse({"success": True, **created})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    payload = boxespy.health_status()
    payload["auth_required"] = _auth_on()
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


@mcp.custom_route("/api/plans", methods=["GET"])
async def api_plans(request: Request) -> Response:
    from plans import public_plans

    return JSONResponse(public_plans())


@mcp.custom_route("/api/beta", methods=["POST"])
async def api_beta(request: Request) -> Response:
    from studio_store import append_jsonl, now_iso

    try:
        body = await request.json()
    except Exception:
        body = {}
    email = str((body or {}).get("email") or "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"success": True, "look_again": ["Pass a real email."]})
    append_jsonl(
        "beta.jsonl",
        {
            "at": now_iso(),
            "email": email[:120],
            "use": str((body or {}).get("use") or "")[:160],
        },
    )
    return JSONResponse({"success": True, "joined": True, "note": "You're on the LaserMCP beta list."})


@mcp.custom_route("/api/studio", methods=["GET"])
async def api_studio(request: Request) -> Response:
    from studio import overview, studio_action

    action = (request.query_params.get("action") or "overview").strip().lower()
    if action in {"", "overview"}:
        return JSONResponse(overview())
    return JSONResponse(
        studio_action(
            action,
            name=request.query_params.get("name") or "",
            project_id=request.query_params.get("project_id") or "",
            role=request.query_params.get("role") or "workshop",
        )
    )


@mcp.custom_route("/api/studio/{action}", methods=["GET", "POST"])
async def api_studio_action(request: Request) -> Response:
    from studio import studio_action

    action = request.path_params.get("action") or "profiles"
    body: dict[str, Any] = {}
    if request.method == "POST":
        try:
            raw = await request.json()
            if isinstance(raw, dict):
                body = raw
        except Exception:
            body = {}
    return JSONResponse(
        studio_action(
            action,
            name=str(body.get("name") or request.query_params.get("name") or ""),
            project_id=str(body.get("project_id") or request.query_params.get("project_id") or ""),
            role=str(body.get("role") or request.query_params.get("role") or "workshop"),
        )
    )


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
    media = {
        ".svg": "image/svg+xml",
        ".dxf": "image/vnd.dxf",
        ".png": "image/png",
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }.get(suffix, "application/octet-stream")
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
