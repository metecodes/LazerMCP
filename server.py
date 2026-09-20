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
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
    "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
}
PUBLIC_PATHS = {
    "/",
    "/health",
    "/dashboard",
    "/app",
    "/workshop",
    "/account",
    "/admin",
    "/connect",
    "/auth/callback",
    "/auth/google",
    "/api/plans",
    "/api/beta",
    "/api/demo",
    "/api/auth/config",
    "/api/auth/start",
    "/api/auth/session",
    "/api/auth/logout",
    "/api/account",
    "/api/account/key-request",
    "/api/catalog",
    "/styles.css",
    *BRAND_FILES,
}
PUBLIC_PREFIXES = ("/demo/", "/oauth/", "/.well-known/", "/auth/", "/files/", "/out/", "/edit/")
MCP_TOOLS = [
    "plan_laser_job",
    "create_from_reference",
    "create_design",
    "payas_defaults",
    "get_operation_settings",
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
        "This server is a toolbox with a searchable Boxes.py joint library. Never ask for a new kit or MCP tool. "
        "For interlocking assemblies consult plan_laser_job joint_library or search_joint_templates before inventing joints. Reuse source geometry and paired edge settings; source indexing does not prove physical fit. "
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
        "For large chat images call start_reference_upload, upload_reference_chunk repeatedly, then create_from_reference(reference_upload_id=...). create_from_reference traces flat artwork by itself; with explicit primitives and reference_markings it engraves the supplied artwork on named mechanical panels in the same SVG+DXF sheet. Never infer joints from pixels. "
        "Do not skip the plan. Do not use number_match_puzzle unless the plan says so. "
        "A structural design derived from a photo can never receive PROTOTYPE READY from geometric validity alone. parameters.reference_job=true requires reference_parts:[{reference_part,generated_part,role,expected_outer_shape,silhouette_points?}]. The reviewer must prove one-to-one part mapping, structural OUTER_CUT fidelity, geometric tab-slot alignment, an assembled_preview.svg, nominal hardware fit and motion clearance. panel.tabs metadata is compiled into the panel's actual outer CUT polygon; every slot is compiled as a closed INNER_CUT polygon. Reviewer and preview consume the same origin/u/v transform and compiled CUT geometry. For a directly driven rotor pass hardware:[{id,type:'dc_motor',shaft_diameter,shaft_axis,shaft_origin}] and connections:[{type:'direct_motor_shaft',motor_part,driven_part,shaft_axis:{origin:[x,y,z],direction:[x,y,z]},driven_center:[x,y,z],radius_mm,clearance_mm,allowed_contact_parts:[]}]. A direct_motor_shaft connection verifies hardware→propeller endpoints, hole fit, coaxiality, propeller-normal angle and 360-degree clearance; it never creates a propeller self-connection or infers an extra dowel and does not require two opposite wall holes. Labels, mate metadata, ENGRAVE silhouettes and prose are not physical evidence. A custom reference silhouette mapped to a rectangle is FAIL. "
        "Circular geometry alone never means propeller or rotor. For wheel, road roller drum, pulley, gear, disc, propeller, rotor or flywheel set mechanism:{type,rotating,shaft}; explicit mechanism.type has priority. Use hardware:[{id,type:'shaft',diameter,axis,origin,length}] and connections:[{type:'shaft_rotation',shaft,driven_part,hardware_clearance,required_length,allowed_contact_parts:[]}]. The mechanism-specific validator checks coaxiality, shaft-hole fit, shaft length and 360-degree motion clearance. Each physical part should have placement:{origin,u,v}; when exactly one tab-slot constraint determines a missing pose it is derived, otherwise PLACEMENT_AMBIGUOUS blocks the gate. Names never prove a mate: tab/slot centers, axes, dimensions, normals and insertion are compared in assembled world coordinates. "
        "If final_status is BLOCKED, read look_again, fix primitives, call create_design again. "
        "Do not invent a PASS. Working SVG is not a cuttable product until the gate says so. "
        "Defaults: 3 mm poplar, kerf 0.15 mm, 1500×3000 mm bed, SVG + DXF, "
        "cut #FF0000, text/logo/decor engraving #FFFF00, LaserCAD Y-up. Yellow is always ENGRAVE, not CUT. "
        "The default ENGRAVE intent is 0.65 CUT speed and 0.25 CUT power, one non-through pass; calibrate absolute values with a material coupon. "
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


def _safe_download_name(name: str) -> str:
    base = Path(str(name or "file")).name.replace('"', "").replace("\r", "").replace("\n", "")
    return base or "file"


def _wants_inline_file(request: Request) -> bool:
    flag = (request.query_params.get("view") or request.query_params.get("inline") or "").strip().lower()
    return flag in {"1", "true", "yes"}


def _prefers_html(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return True
    if "application/json" in accept:
        return False
    return True


def _wants_svg_editor(request: Request) -> bool:
    if request.query_params.get("download") in {"1", "true", "yes"}:
        return False
    if _wants_inline_file(request):
        return False
    accept = (request.headers.get("accept") or "").lower()
    if "image/svg" in accept:
        return False
    return "text/html" in accept


def _missing_output(request: Request, *, signed_in: bool = False, expired: bool = False) -> Response:
    if expired:
        if not _prefers_html(request):
            return JSONResponse({"success": False, "code": "expired", "look_again": ["Dosyanın 24 saatlik saklama süresi doldu."]}, status_code=410)
        return Response('<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Saklama süresi doldu — LaserMCP</title><main style="max-width:560px;margin:48px auto;padding:20px;font:16px/1.6 sans-serif"><h1>Dosyanın saklama süresi doldu</h1><p>Oluşturulan dosyalar 24 saat saklanır. Stüdyodan yeni bir dosya oluşturabilirsiniz.</p><a href="/dashboard">Stüdyoyu aç</a></main></html>', status_code=410, media_type="text/html", headers={"Cache-Control": "no-store"})
    if not _prefers_html(request):
        note = "Dosya yok veya bu hesaba ait değil." if signed_in else "Dosyayı görmek için Google ile gir."
        return JSONResponse({"success": True, "look_again": [note]}, status_code=404)
    title = "Dosya yok" if signed_in else "Giriş gerekli"
    body_tr = (
        "Bu dosya yok, süresi dolmuş veya başka bir hesaba ait."
        if signed_in
        else "Bu kesim dosyasını görmek veya indirmek için Google ile gir."
    )
    extra = (
        '<a class="btn ghost" href="/">Ana sayfa</a>'
        if signed_in
        else '<a class="btn" href="/account?next=' + html.escape(quote(request.url.path, safe=""), quote=True) + '">Google ile gir</a>'
    )
    html_page = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>{title} — LaserMCP</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{margin:0;font:16px/1.5 'Segoe UI',sans-serif;background:#fafafa;color:#111}}
.wrap{{width:min(560px,calc(100% - 40px));margin:48px auto}}
.btn{{display:inline-flex;margin-right:8px;padding:10px 16px;background:#111;color:#fff;text-decoration:none;font-weight:600}}
.btn.ghost{{background:transparent;color:#111;border:1px solid #111}}
.lede{{color:#5a5a5a}}
</style></head><body>
<div class="wrap">
<p style="letter-spacing:.14em;text-transform:uppercase;color:#e10600;font:11px monospace">LaserMCP</p>
<h1>{title}</h1>
<p class="lede">{body_tr}</p>
<p>{extra}<a class="btn ghost" href="/dashboard">Stüdyo</a></p>
</div></body></html>"""
    return Response(content=html_page, status_code=404, media_type="text/html; charset=utf-8")


def _file_payload(data: bytes, filename: str, media: str, *, inline: bool) -> Response:
    name = _safe_download_name(filename)
    kind = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=media if inline else "application/octet-stream",
        headers={
            "Content-Disposition": f'{kind}; filename="{name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
        "&flow_type=implicit"
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
        if method == "OPTIONS" or path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES) or (method == "GET" and path.startswith("/api/editor/")):
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
        if (scope.get("method") or "GET").upper() in {"POST", "PUT"} and (
            path.startswith("/mcp") or path.startswith("/api/generate") or path.startswith("/api/cad/") or (path.startswith("/api/editor/") and path.endswith(("/preview", "/save")))
        ):
            from persist.rate_limit import check

            ident = str(key.get("organization_id") or key.get("id") or "anon")
            expensive = path.startswith("/api/generate") or path.startswith("/api/cad/") or path.startswith("/api/editor/")
            if not check("http", ident, limit=30 if expensive else 60, window_sec=3600 if expensive else 60):
                limited = b'{"success":true,"look_again":["Rate limit. Try again later."]}'
                headers = [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(limited)).encode("ascii")),
                    (b"retry-after", b"60"),
                ]
                await send({"type": "http.response.start", "status": 429, "headers": headers})
                await send({"type": "http.response.body", "body": limited})
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
        "parameters.material / parameters.machine pick profiles. Optional parameters.operation_settings overrides CUT/ENGRAVE speed_scale, power_scale, speed_mm_s, power_percent and passes; ENGRAVE must stay lower-power, one-pass and non-through. Photo-derived structures require parameters.reference_job=true and complete reference_parts mapping before PROTOTYPE READY. For a final user assembly request copy it to parameters.assembly_request; use parameters.assembly_order with every explicit placed part label exactly once and parameters.assembly_notes for step text. Successful explicit assemblies return progressive assembly_steps SVG drawings. MCP writes bom. "
        "preset=jigsaw_puzzle or number_match_puzzle only when the plan says so. "
        "Paste speak as the gate card. BLOCKED = no authorized SVG. "
        "PROTOTYPE READY = Prototype SVG only; PRODUCTION EXPORT BLOCKED. "
        "PLT/HP-GL files: pass plt text or plt_base64 to this tool; do not trace a screenshot. "
        "Existing SVG: pass its complete XML in svg, with parameters.svg_default_operation='CUT' only when the user identifies untagged vectors as cut lines. "
        "Text/logo engraving is yellow #FFFF00, DXF ENGRAVE layer ACI 2; CUT stays red. For standalone artwork use preset='engraving_layout', parameters={width_mm,height_mm,items:[{kind:'text',value:'PAYAS STEM',x:50,y:100,height:6,align:'center'},{kind:'path',d:'actual logo SVG path',x:50,y:80,width:30}]}. Coordinates are mm from bottom-left. Supply real logo vectors; never replace unknown logos with generic icons. "
        "Uploaded artwork can be engraved directly: use {kind:'image',image_base64:'PNG/JPEG/WebP base64',crop:[left,top,right,bottom],foreground:'auto',x:50,y:50,width:30,operation:'engrave'} in a part's markings or engraving_layout items. Crop coordinates are normalized 0..1 from image top-left. Trace the provided artwork, never substitute another logo. "
        "SVG import preserves narrow tabs, vertices and existing gaps; do not replace supplied SVG with a generic box or holder preset. "
        "plt_units_per_mm defaults to 40; plt_pen_operations explicitly selects CUT/ENGRAVE. "
        "Never say LAZER KESİME HAZIR. Never request a new tool. Never hand-write SVG."
    )
)
def create_design(
    preset: str | None = None,
    primitives: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
    svg: str | None = None,
    plt: str | None = None,
    plt_base64: str | None = None,
) -> dict[str, Any]:
    return payas_cad.create_design(
        preset=preset,
        primitives=primitives,
        parameters=parameters,
        svg=svg,
        plt=plt,
        plt_base64=plt_base64,
        public_base_url=_tool_public_base(),
    )


@mcp.tool(
    description=(
        "Vectorize 2D artwork, or combine an explicit mechanical recipe and reference artwork in one sheet. "
        "Pass compressed JPEG image_base64, a public HTTPS image_url, or upload large base64 through start_reference_upload + upload_reference_chunk and pass reference_upload_id. "
        "For a mechanical single-sheet output pass primitives plus reference_markings:[{target_part:'named-panel',kind:'image',crop:[left,top,right,bottom],ink_color:'yellow',x:50,y:50,width:30}]. Crop uses normalized image coordinates. parameters controls material/project and optional operation_settings. Text/path marks stay yellow ENGRAVE and are never through-cut. format='both' yields SVG+DXF from the same recipe. Never infer mechanical joints from pixel outlines alone. "
        "layout=jigsaw or trace. format=svg or both. Then validate_svg."
    )
)
def create_from_reference(
    image_base64: str | None = None,
    image_chunks: list[str] | None = None,
    reference_upload_id: str | None = None,
    image_url: str | None = None,
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
    primitives: list[Any] | None = None,
    reference_markings: list[dict[str, Any]] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        if reference_upload_id:
            from reference_upload import read_reference_upload
            image_base64=read_reference_upload(reference_upload_id)
        if not image_base64 and image_url:
            from reference_upload import fetch_public_image
            image_base64=fetch_public_image(image_url)
        if not image_base64 and image_chunks:
            if not all(isinstance(chunk,str) for chunk in image_chunks):raise ValueError('image_chunks must contain base64 strings')
            image_base64=''.join(image_chunks)
        if not image_base64:
            return payas_cad._mcp({'success':False,'ready_to_cut':False,'retryable':True,'error_code':'REFERENCE_IMAGE_MISSING','look_again':['Reference image did not reach LaserMCP. Retry with image_base64 or split the same base64 into image_chunks. For PLT/SVG use compose_source_sheet.']})
        if len(image_base64)>16_000_000:
            return payas_cad._mcp({'success':False,'ready_to_cut':False,'retryable':True,'error_code':'REFERENCE_PAYLOAD_TOO_LARGE','look_again':['Reference payload exceeds 16 MB base64. Resize without changing aspect ratio or use the original SVG/PLT with compose_source_sheet.']})
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
            primitives=primitives,
            reference_markings=reference_markings,
            parameters=parameters,
            public_base_url=_tool_public_base(),
        )
    except Exception as exc:
        return payas_cad._mcp(
            {
                "success": False,
                "ready_to_cut": False,
                "retryable": True,
                "error_code": "REFERENCE_TRANSFER_OR_DECODE_FAILED",
                "hint": (
                    "Compress the photo to ~1200px JPEG and retry. "
                    "This tool only traces 2D artwork. For a mill/house/model, call plan_laser_job "
                    "then create_design with box/panel/disc primitives."
                ),
                "look_again": [str(exc)],
            }
        )


@mcp.tool(description="Begin a short-lived chunked upload for a chat image that is too large for one MCP argument. Returns a secret reference_upload_id valid for one hour.")
def start_reference_upload(expected_chunks: int | None = None, mime_type: str = "image/png") -> dict[str, Any]:
    from reference_upload import start_reference_upload as start
    try:return start(expected_chunks,mime_type)
    except Exception as exc:return {'success':False,'retryable':True,'error_code':'REFERENCE_UPLOAD_START_FAILED','look_again':[str(exc)]}


@mcp.tool(description="Upload one base64 segment (maximum 500,000 characters) for a reference_upload_id. Send sequential indices starting at zero in separate MCP calls.")
def upload_reference_chunk(reference_upload_id: str, index: int, chunk: str) -> dict[str, Any]:
    from reference_upload import upload_reference_chunk as upload
    try:return upload(reference_upload_id,index,chunk)
    except Exception as exc:return {'success':False,'retryable':True,'error_code':'REFERENCE_CHUNK_REJECTED','look_again':[str(exc)]}


@mcp.tool(description="Delete a short-lived chunked reference upload after use or cancellation.")
def discard_reference_upload(reference_upload_id: str) -> dict[str, Any]:
    from reference_upload import discard_reference_upload as discard
    try:return discard(reference_upload_id)
    except Exception as exc:return {'success':False,'error_code':'REFERENCE_UPLOAD_NOT_FOUND','look_again':[str(exc)]}


@mcp.tool(description="Payas STEM defaults: 3mm kavak, kerf 0.15, 1500x3000, SVG.")
def payas_defaults() -> dict[str, Any]:
    result=boxespy.payas_defaults()
    from laser_settings import resolve_operation_settings
    result["operation_settings"]=resolve_operation_settings()
    return result


@mcp.tool(description="Return and validate CUT/ENGRAVE/SCORE/GUIDE speed, power and pass intent. Pass the same parameters.operation_settings object to create_design or create_from_reference. Yellow ENGRAVE remains a one-pass non-through surface operation; absolute values require a material coupon.")
def get_operation_settings(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    from laser_settings import resolve_operation_settings
    try:return {"success":True,**resolve_operation_settings(parameters)}
    except Exception as exc:return {"success":False,"look_again":[str(exc)]}


@mcp.tool(description="List the toolbox. Look, plan_laser_job, then create_design primitives. Do not request new tools.")
def list_cad_tools() -> dict[str, Any]:
    return payas_cad.list_cad_tools()


@mcp.tool(description="Parameter schema for one Boxes.py class. Not used for puzzles or uploaded pictures.")
def get_generator_schema(generator: str) -> dict[str, Any]:
    try:
        return payas_cad._mcp(boxespy.get_generator_schema(generator))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)]})


@mcp.tool(description="Search installed Boxes.py templates, joint settings and literal edge sequences before designing interlocking parts. Includes real parameter schemas and source hashes. Source indexed does not mean assembly/physical PASS.")
def search_joint_templates(query: str, limit: int = 5) -> dict[str, Any]:
    from joint_library import search_joint_templates as search
    return search(query, limit)


@mcp.tool(description="Create editable Arial-compatible text. auto_fit measures real outlines and shrinks within max_width/max_height or the part safe area, but never below min_font_size.")
def create_text(content: str, parent_part_id: str | None = None, font_size: float = 6, placement: str = "center", operation: str = "ENGRAVE", max_width: float | None = None, max_height: float | None = None, min_font_size: float = 1.5, font_weight: str = "normal", letter_spacing: float = 0) -> dict[str, Any]:
    from semantic_cad import create_text as create
    return create(content,parent_part_id=parent_part_id,font_size=font_size,placement=placement,operation=operation,max_width=max_width,max_height=max_height,min_font_size=min_font_size,font_weight=font_weight,letter_spacing=letter_spacing,auto_fit=True)


@mcp.tool(description="Create a product-neutral vector graphic object. Logos/icons/illustrations default to ENGRAVE and require real SVG path data.")
def create_vector_graphic(d: str, parent_part_id: str | None = None, graphic_type: str = "illustration", placement: str = "center", operation: str = "ENGRAVE") -> dict[str, Any]:
    from semantic_cad import create_vector_graphic as create
    return create(d,parent_part_id=parent_part_id,graphic_type=graphic_type,placement=placement,operation=operation)


@mcp.tool(description="Create an editable engraving object from the supplied PNG/JPEG/WebP. exact mode preserves fine contours up to 3000 px; crop, size and placement remain editable.")
def create_image_reference(image_base64: str, parent_part_id: str | None = None, width: float = 30, height: float | None = None, placement: str = "center", trace_quality: str = "exact", crop: list[float] | None = None, foreground: str = "auto") -> dict[str, Any]:
    from semantic_cad import create_image_reference as create
    return create(image_base64,parent_part_id=parent_part_id,width=width,height=height or 0,placement=placement,trace_quality=trace_quality,crop=crop or [],foreground=foreground)


@mcp.tool(description="Create a reusable native vector icon (arrow, circle, cross, heart, plus, square, star, triangle or x); defaults to ENGRAVE.")
def create_icon(name: str, parent_part_id: str | None = None, placement: str = "center", width: float = 10) -> dict[str, Any]:
    from markings import ICONS
    from semantic_cad import create_vector_graphic
    key=name.strip().lower()
    if key not in ICONS:raise ValueError('unknown native icon; supply an SVG path with create_vector_graphic')
    return create_vector_graphic(points=ICONS[key],parent_part_id=parent_part_id,graphic_type='icon',placement=placement,size={'width':width,'height':width},source='native_icon:'+key)


@mcp.tool(description="Edit properties of an unlocked semantic text/graphic object without changing its id or type.")
def edit_design_object(object: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    from semantic_cad import edit_object
    return edit_object(object,changes)


@mcp.tool(description="Move/place a semantic text or graphic object by exact part-local millimetres without regenerating mechanical CAD.")
def place_design_object(object: dict[str, Any], x: float, y: float, parent_part_id: str | None = None) -> dict[str, Any]:
    from semantic_cad import edit_object
    changes={'position':{'x':x,'y':y}}
    if parent_part_id is not None:changes['parent_part_id']=parent_part_id
    return edit_object(object,changes)


@mcp.tool(description="Convert a first-class text object to font-independent vector path geometry.")
def convert_text_to_paths(object: dict[str, Any]) -> dict[str, Any]:
    from semantic_cad import convert_text_to_paths as convert
    return convert(object)


@mcp.tool(description="Align semantic objects left/right/top/bottom/center_x/center_y, optionally inside explicit bounds.")
def align_objects(objects: list[dict[str, Any]], mode: str, bounds: list[float] | None = None) -> list[dict[str, Any]]:
    from semantic_cad import align_objects as align
    return align(objects,mode,bounds)


@mcp.tool(description="Distribute semantic objects evenly by their centers on the horizontal or vertical axis.")
def distribute_objects(objects: list[dict[str, Any]], axis: str = "horizontal") -> list[dict[str, Any]]:
    from semantic_cad import distribute_objects as distribute
    return distribute(objects,axis)


@mcp.tool(description="Inspect semantic objects and detect physical parts from an existing SVG. CAD geometry remains authoritative; UNKNOWN operations are reported.")
def inspect_design(svg: str) -> dict[str, Any]:
    from semantic_cad import inspect_design as inspect
    result=inspect(svg)
    return {k:v for k,v in result.items() if not k.startswith('_')}


@mcp.tool(description="Select one semantic object or detected physical part from an inspected SVG by stable id.")
def select_design_item(svg: str, item_id: str) -> dict[str, Any]:
    result=inspect_design(svg)
    found=next((row for row in result['objects']+result['parts'] if row['id']==item_id),None)
    if not found:raise ValueError('object or part not found')
    return found


@mcp.tool(description="Import a millimetre ASCII DXF into the semantic SVG coordinate system. CUT/ENGRAVE/SCORE/GUIDE layer names are preserved; other layers become UNKNOWN and block export.")
def import_dxf_design(dxf: str) -> dict[str, Any]:
    from dxf_import import dxf_to_svg
    from semantic_cad import inspect_design as inspect
    svg=dxf_to_svg(dxf);result=inspect(svg)
    return {'svg':svg,**{k:v for k,v in result.items() if not k.startswith('_')}}


@mcp.tool(description="Return exact outer bounds for a detected physical part in an SVG document.")
def get_part_bounds(svg: str, part_id: str) -> dict[str, Any]:
    from semantic_cad import get_part_bounds as bounds
    return bounds(svg,part_id)


@mcp.tool(description="Compute part boundary minus cut features, edge margin and mechanical clearance. Returns bounds, area and WKT geometry.")
def compute_safe_design_area(svg: str, part_id: str, safe_margin: float = 3, mechanical_clearance: float = 1) -> dict[str, Any]:
    from semantic_cad import compute_safe_design_area as compute
    result=compute(svg,part_id,safe_margin,mechanical_clearance)
    return {k:v for k,v in result.items() if k not in {'_geom','document'}}


@mcp.tool(description="Compose text, vectors or image references on detected parts in one CAD coordinate system. Calculates safe areas, avoids mechanical features, repairs affected elements up to five times, converts text to paths, and returns semantic SVG.")
def compose_design(svg: str, elements: list[dict[str, Any]], safe_margin: float = 3, mechanical_clearance: float = 1, duplicate_policy: str = "replace") -> dict[str, Any]:
    from semantic_cad import compose_design as compose
    return compose(svg,elements,safe_margin,mechanical_clearance,duplicate_policy)


@mcp.tool(description="Build one persisted sheet from exactly one real geometry source (SVG, PLT/HPGL or primitives), then add editable text/logo/decor objects and export matching SVG+DXF. CUT remains red; ENGRAVE remains yellow. No raster re-measurement of SVG/PLT.")
def compose_source_sheet(elements: list[dict[str, Any]], svg: str | None = None, plt: str | None = None, plt_base64: str | None = None, primitives: list[dict[str, Any]] | None = None, parameters: dict[str, Any] | None = None, safe_margin: float = 3, mechanical_clearance: float = 1) -> dict[str, Any]:
    from design_engine import compile_design,import_svg_document
    sources=sum(value is not None for value in (svg,plt,plt_base64,primitives))
    if sources!=1:return payas_cad._mcp({'success':False,'ready_to_cut':False,'error_code':'SOURCE_COUNT_INVALID','look_again':['Pass exactly one source: svg, plt, plt_base64 or primitives.']})
    try:
        params=dict(parameters or {})
        if svg is not None:built=import_svg_document(svg,params)
        elif plt is not None or plt_base64 is not None:
            import base64 as _base64
            from plt_import import import_plt_document,MAX_BYTES
            if plt_base64 is not None:
                if len(plt_base64)>MAX_BYTES*4//3+4:raise ValueError('PLT payload is too large')
                plt=_base64.b64decode(plt_base64,validate=True).decode('ascii')
            built=import_plt_document(plt,params)
        else:built=compile_design(primitives=primitives,parameters=params)
        from semantic_cad import compose_design as compose
        composed=compose(built['svg_bytes'].decode(),elements,safe_margin,mechanical_clearance)
        if not composed['success']:return payas_cad._mcp({'success':False,'ready_to_cut':False,'error_code':'COMPOSITION_INVALID','composition':composed['validation'],'look_again':[i['note'] for i in composed['issues'] if i['status']=='FAIL']})
        params['format']='both';params['reference_single_sheet']=True
        result=payas_cad.create_design(svg=composed['svg'],parameters=params,public_base_url=_tool_public_base())
        result['composition']=composed['validation'];result['single_sheet']=True
        return result
    except Exception as exc:
        return payas_cad._mcp({'success':False,'ready_to_cut':False,'retryable':True,'error_code':'SOURCE_COMPOSITION_FAILED','look_again':[str(exc)]})


@mcp.tool(description="Validate semantic text/graphics against parent-part safe areas, mechanical cuts, duplicates, size and UNKNOWN operations.")
def validate_composition(svg: str, safe_margin: float = 3, mechanical_clearance: float = 1) -> dict[str, Any]:
    from semantic_cad import validate_composition as validate
    return validate(svg,safe_margin,mechanical_clearance)


@mcp.tool(description="Repair only existing semantic composition objects against current part safe areas, up to five placement/scale attempts per object.")
def repair_composition(svg: str, safe_margin: float = 3, mechanical_clearance: float = 1) -> dict[str, Any]:
    from semantic_cad import repair_composition as repair
    return repair(svg,safe_margin,mechanical_clearance)


@mcp.tool(description="Remove one semantic text/graphic object from an existing design without regenerating mechanical geometry.")
def remove_design_object(svg: str, object_id: str) -> str:
    from semantic_cad import remove_object
    return remove_object(svg,object_id)


@mcp.tool(description="Replace/edit one semantic object in an existing SVG, then recompute safe placement and validation while preserving mechanical geometry.")
def replace_design_object(svg: str, object_id: str, replacement: dict[str, Any], safe_margin: float = 3, mechanical_clearance: float = 1) -> dict[str, Any]:
    from semantic_cad import replace_object
    return replace_object(svg,object_id,replacement,safe_margin,mechanical_clearance)


@mcp.tool(description="Export a semantic SVG document to production DXF layers. Text is vector geometry; no downstream font substitution.")
def export_composed_dxf(svg: str) -> str:
    import base64
    from semantic_cad import export_dxf
    return base64.b64encode(export_dxf(svg)).decode()


@mcp.tool(description="Return a validated semantic production SVG unchanged when composition passes; UNKNOWN or collision failures block export.")
def export_composed_svg(svg: str) -> dict[str, Any]:
    from semantic_cad import validate_composition
    report=validate_composition(svg)
    return {'success':report['status']!='FAIL','svg':svg if report['status']!='FAIL' else None,'validation':report}


@mcp.tool(description="Upload a reusable organization-scoped SVG logo/icon/illustration. Returns a library token once for a new library; save it securely. Assets default to ENGRAVE and contain normalized vector paths.")
def upload_asset(organization_id: str, name: str, asset_type: str, svg: str, library_token: str | None = None) -> dict[str, Any]:
    from asset_library import upload_asset as upload
    return upload(organization_id,name,asset_type,svg,library_token)


@mcp.tool(description="List reusable SVG assets accessible with the organization library token.")
def list_assets(organization_id: str, library_token: str) -> list[dict[str, Any]]:
    from asset_library import list_assets as listing
    return listing(organization_id,library_token)


@mcp.tool(description="Create a semantic graphic object from a reusable organization asset for placement on a named CAD part.")
def place_asset(organization_id: str, library_token: str, asset_id: str, parent_part_id: str, placement: str = "center", width: float | None = None, height: float | None = None) -> dict[str, Any]:
    from asset_library import place_asset as place
    return place(organization_id,library_token,asset_id,parent_part_id,placement,width,height)


@mcp.tool(description="Import a standalone SVG logo/icon/illustration as one editable semantic ENGRAVE graphic.")
def import_svg_graphic(svg: str, parent_part_id: str | None = None, placement: str = "center", graphic_type: str = "illustration") -> dict[str, Any]:
    from semantic_cad import import_svg_graphic as load
    return load(svg,parent_part_id=parent_part_id,placement=placement,graphic_type=graphic_type)


@mcp.tool(description="Create a product-neutral native vector primitive: line, polyline, rectangle, rounded_rectangle, circle, ellipse, arc, polygon, bezier or path.")
def create_primitive(kind: str, parent_part_id: str | None = None, width: float = 10, height: float = 10, points: list[list[float]] | None = None, d: str | None = None, placement: str = "center") -> dict[str, Any]:
    from semantic_cad import create_primitive as create
    return create(kind,parent_part_id=parent_part_id,width=width,height=height,points=points,d=d,placement=placement)


@mcp.tool(description="Edit a first-class text object's content, typography, placement or constraints while preserving its stable id.")
def edit_text(object: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    if object.get('type')!='text':raise ValueError('text object required')
    return edit_design_object(object,changes)


@mcp.tool(description="Place a text object at exact millimetre coordinates on a named physical part.")
def place_text(object: dict[str, Any], x: float, y: float, parent_part_id: str | None = None) -> dict[str, Any]:
    if object.get('type')!='text':raise ValueError('text object required')
    return place_design_object(object,x,y,parent_part_id)


@mcp.tool(description="Place a graphic object at exact millimetre coordinates on a named physical part.")
def place_graphic(object: dict[str, Any], x: float, y: float, parent_part_id: str | None = None) -> dict[str, Any]:
    if object.get('type') not in {'graphic','image_reference'}:raise ValueError('graphic object required')
    return place_design_object(object,x,y,parent_part_id)


@mcp.tool(description="Select one semantic object by stable id.")
def select_object(svg: str, object_id: str) -> dict[str, Any]:
    row=select_design_item(svg,object_id)
    if 'type' not in row:raise ValueError('object not found')
    return row


@mcp.tool(description="Select one detected physical part by stable id.")
def select_part(svg: str, part_id: str) -> dict[str, Any]:
    result=inspect_design(svg);row=next((p for p in result['parts'] if p['id']==part_id),None)
    if not row:raise ValueError('part not found')
    return row


@mcp.tool(description="Get one reusable vector asset and its normalized SVG using the organization library token.")
def get_asset(organization_id: str, library_token: str, asset_id: str) -> dict[str, Any]:
    from asset_library import get_asset_info
    return get_asset_info(organization_id,library_token,asset_id)


@mcp.tool(description="Replace a reusable asset's vector geometry while preserving its stable asset id and access scope.")
def replace_asset(organization_id: str, library_token: str, asset_id: str, svg: str, name: str | None = None, asset_type: str | None = None) -> dict[str, Any]:
    from asset_library import replace_asset as replace
    return replace(organization_id,library_token,asset_id,svg,name,asset_type)


@mcp.tool(description="Validated production SVG export alias for general composition workflows.")
def export_svg(svg: str) -> dict[str, Any]:
    return export_composed_svg(svg)


@mcp.tool(description="Production DXF export alias for general composition workflows; returns base64 DXF.")
def export_dxf(svg: str) -> str:
    return export_composed_dxf(svg)


@mcp.tool(description="Boxes.py class SVG only (ABox, TypeTray, …). Use only if plan_laser_job next_tool is generate_svg. Photos of things to build: plan_laser_job then create_design primitives.")
def generate_svg(generator: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return payas_cad._mcp(boxespy.generate_svg(generator, parameters, public_base_url=_tool_public_base()))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "ready_to_cut": False})


@mcp.tool(description="Validate a generated SVG: XML, 1500×3000 bed, nested part spacing. Pass file_id (for internal) OR url (if user uploaded an SVG directly to you).")
def validate_svg(file_id: str | None = None, url: str | None = None) -> dict[str, Any]:
    try:
        if url and not file_id:
            import urllib.request
            import uuid
            from pathlib import Path
            req = urllib.request.Request(url, headers={"User-Agent": "LazerMCP/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            file_id = f"uploaded_{uuid.uuid4().hex[:8]}.svg"
            out_path = Path("output") / file_id
            out_path.parent.mkdir(exist_ok=True, parents=True)
            out_path.write_bytes(data)
            
        if not file_id:
            return payas_cad._mcp({"look_again": ["Must provide either file_id or url"], "well_formed": False})
            
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


@mcp.tool(description="Return a preview URL. view='cut' shows the laser sheet; view='assembled' shows upright panels only when explicit placements and tab partners were verified.")
def render_preview(file_id: str, view: str = "cut") -> dict[str, Any]:
    if view == "assembled":
        from workshop import editor_context
        data = editor_context(file_id)
        if not data.get("assembled_preview_svg"):
            return {"success": False, "look_again": ["Monte görünüm için doğrulanmış parça konumları ve geçme eşleri gerekli."]}
        return {"success": True, "preview_kind": "assembled", "preview_url": _tool_public_base().rstrip("/") + "/out/" + quote(file_id, safe="") + "?view=assembled", "note": "Nominal digital assembly; physical dry-fit is not verified."}
    try:
        return payas_cad._mcp(boxespy.render_preview(file_id, public_base_url=_tool_public_base()))
    except Exception as exc:
        return payas_cad._mcp({"look_again": [str(exc)], "file_id": file_id})


@mcp.tool(
    description=(
        "Workshop studio — not a kit. action=profiles|calibrate|projects|usage|keys|telemetry. "
        "HTTP /api/studio/{onboard|catalog|feedback|preflight|revise|cost|make_this|activate} is the loop. "
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
    return FileResponse(
        WEB_DIR / "connect.html",
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "private, no-store"},
    )


@mcp.custom_route("/account", methods=["GET"])
async def account_page(request: Request) -> Response:
    return FileResponse(WEB_DIR / "account.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/auth/callback", methods=["GET"])
async def auth_callback_page(request: Request) -> Response:
    return FileResponse(WEB_DIR / "auth-callback.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@mcp.custom_route("/api/auth/start", methods=["GET"])
async def api_auth_start(request: Request) -> Response:
    """Start Google login without rendering an intermediate account page."""
    from supabase_auth import configured, session_ready, session_user

    nxt = _safe_next(request.query_params.get("next") or "", request) or "/dashboard"
    if nxt.startswith("//") or nxt.split("?", 1)[0] in {"/auth/google", "/auth/callback"}:
        nxt = "/dashboard"
    headers = {"Cache-Control": "no-store"}
    if session_user(request.cookies.get("lmcp_sid")):
        return JSONResponse({"url": nxt, "signed_in": True}, headers=headers)
    if not configured() or not session_ready():
        return JSONResponse({"error": "signin_unavailable"}, status_code=503, headers=headers)
    return JSONResponse({"url": _google_authorize_url(request, nxt)}, headers=headers)


@mcp.custom_route("/admin", methods=["GET"])
async def admin_page(request: Request) -> Response:
    return FileResponse(WEB_DIR / "admin.html", media_type="text/html; charset=utf-8")


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
    return _redirect("/dashboard")


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
@mcp.custom_route("/styles.css", methods=["GET"])
@mcp.custom_route("/editor.js", methods=["GET"])
@mcp.custom_route("/ui.js", methods=["GET"])
async def brand_asset(request: Request) -> Response:
    spec = BRAND_FILES.get(request.url.path)
    if not spec:
        return Response(status_code=404)
    name, media = spec
    path = WEB_DIR / name
    if not path.is_file():
        return Response(status_code=404)
    headers = {"Cache-Control": "no-store"} if name == "nav-auth.js" else {}
    return FileResponse(path, media_type=media, headers=headers)


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
            "ui": "/dashboard",
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
    try:
        stored = upsert_user(identity)
    except Exception:
        stored = dict(identity)
    principal = principal_from_identity(identity, stored)
    try:
        from supabase_auth import SessionSecretError, new_session as _new_sid

        sid = _new_sid(stored)
    except Exception as exc:
        from supabase_auth import SessionSecretError

        if isinstance(exc, SessionSecretError) or "MCP_SESSION_SECRET" in str(exc):
            return JSONResponse(
                {"success": True, "look_again": ["Server session secret is not configured."]},
                status_code=503,
            )
        raise
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
        sid,
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
    from supabase_auth import can_mint_keys, is_admin, session_user, user_by_id

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return JSONResponse({"success": True, "look_again": ["Sign in with Google."]}, status_code=401)
    stored = user_by_id(str(key.get("id") or "")) or {}
    uid = str(key.get("id") or "")
    from access_requests import open_request_for

    email = str(key.get("email") or stored.get("email") or "")
    return JSONResponse(
        {
            "success": True,
            "user": {
                "id": key.get("id"),
                "name": key.get("name") or stored.get("name"),
                "email": email,
                "kind": stored.get("kind") or key.get("kind") or "individual",
                "account_model": stored.get("account_model") or key.get("account_model") or "user",
            },
            "can_mint_keys": can_mint_keys(stored or key),
            "admin": is_admin(stored) or is_admin(key),
            "keys": list_keys(owner=uid),
            "usage": _account_usage(uid),
            "key_request": open_request_for(email),
        }
    )


@mcp.custom_route("/api/account/key-request", methods=["POST"])
async def api_account_key_request(request: Request) -> Response:
    from access_requests import submit_key_request
    from keys import current_auth
    from persist.rate_limit import check
    from supabase_auth import session_user, user_by_id

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return JSONResponse({"success": True, "look_again": ["Google ile gir, sonra talep aç."]}, status_code=401)
    stored = user_by_id(str(key.get("id") or "")) or key
    ident = str(stored.get("email") or stored.get("id") or "user")
    if not check("key-request", ident, limit=8, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    return JSONResponse(
        submit_key_request(
            {**stored, **key, "email": key.get("email") or stored.get("email")},
            note=str((body or {}).get("note") or (body or {}).get("use") or ""),
            want=str((body or {}).get("want") or (body or {}).get("model") or "org"),
        )
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
    from persist.rate_limit import check

    owner = str(key.get("id") or "")
    if not check("mint", owner, limit=10, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    created = create_key(
        str((body or {}).get("name") or "workshop"),
        role="workshop",
        plan="maker",
        owner=owner,
        email=str(key.get("email") or stored.get("email") or ""),
        kind="org",
    )
    return JSONResponse({"success": True, **created})


@mcp.custom_route("/api/account/keys/revoke", methods=["POST"])
async def api_account_keys_revoke(request: Request) -> Response:
    from keys import current_auth, revoke_key
    from supabase_auth import session_user

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return JSONResponse({"success": True, "look_again": ["Sign in with Google."]}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    ok = revoke_key(str((body or {}).get("id") or ""), owner=str(key.get("id") or ""))
    return JSONResponse({"success": True, "revoked": ok})


def _admin_actor(request: Request):
    from keys import current_auth
    from supabase_auth import is_admin, session_user, user_by_id

    key = current_auth.get() or session_user(request.cookies.get("lmcp_sid"))
    if not key:
        return None, JSONResponse({"success": True, "look_again": ["Sign in with Google."]}, status_code=401)
    stored = user_by_id(str(key.get("id") or "")) or {}
    if not (is_admin(stored) or is_admin(key)):
        return None, JSONResponse({"success": True, "look_again": ["Bu sayfa yok."]}, status_code=404)
    return {**stored, **key, "email": key.get("email") or stored.get("email")}, None


@mcp.custom_route("/api/admin/overview", methods=["GET"])
async def api_admin_overview(request: Request) -> Response:
    from supabase_auth import session_ready, user_stats

    actor, deny = _admin_actor(request)
    if deny:
        return deny
    from access_requests import list_key_requests

    stats = user_stats(active_days=30)
    pending = list_key_requests(status="open")
    return JSONResponse(
        {
            "success": True,
            "admin": actor.get("email"),
            "session_ready": session_ready(),
            "requests": pending,
            **stats,
        }
    )


@mcp.custom_route("/api/admin/users", methods=["GET"])
async def api_admin_users(request: Request) -> Response:
    from persist.rate_limit import check
    from supabase_auth import search_users

    actor, deny = _admin_actor(request)
    if deny:
        return deny
    ident = str(actor.get("email") or actor.get("id") or "admin")
    if not check("admin-search", ident, limit=60, window_sec=60):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    q = str(request.query_params.get("q") or "")
    return JSONResponse({"success": True, "users": search_users(q)})


@mcp.custom_route("/api/admin/users/org", methods=["POST"])
async def api_admin_grant_org(request: Request) -> Response:
    from persist.rate_limit import check
    from supabase_auth import grant_org

    actor, deny = _admin_actor(request)
    if deny:
        return deny
    ident = str(actor.get("email") or actor.get("id") or "admin")
    if not check("admin-grant", ident, limit=30, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    user = grant_org(str((body or {}).get("email") or ""), by=str(actor.get("email") or ""))
    if not user:
        return JSONResponse({"success": True, "look_again": ["No user with that email. They must sign in with Google first."]})
    return JSONResponse({"success": True, "user": user, "note": "Organization mint is on. They can create lzr_ keys."})


@mcp.custom_route("/api/admin/users/model", methods=["POST"])
async def api_admin_set_model(request: Request) -> Response:
    from persist.rate_limit import check
    from supabase_auth import ACCOUNT_MODELS, set_account_model

    actor, deny = _admin_actor(request)
    if deny:
        return deny
    ident = str(actor.get("email") or actor.get("id") or "admin")
    if not check("admin-model", ident, limit=30, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = str((body or {}).get("model") or (body or {}).get("account_model") or "")
    user = set_account_model(str((body or {}).get("email") or ""), model, by=str(actor.get("email") or ""))
    if not user:
        return JSONResponse(
            {
                "success": True,
                "look_again": [
                    "No user with that email, or model must be user|dealer|org. They must sign in with Google first."
                ],
                "models": list(ACCOUNT_MODELS),
            }
        )
    return JSONResponse({"success": True, "user": user})


@mcp.custom_route("/api/admin/requests", methods=["POST"])
async def api_admin_requests(request: Request) -> Response:
    from access_requests import decide_key_request
    from persist.rate_limit import check

    actor, deny = _admin_actor(request)
    if deny:
        return deny
    ident = str(actor.get("email") or actor.get("id") or "admin")
    if not check("admin-request", ident, limit=40, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        body = {}
    decision = str((body or {}).get("decision") or "").strip().lower()
    hit = decide_key_request(
        str((body or {}).get("id") or (body or {}).get("email") or ""),
        approve=decision in {"approve", "ok", "yes"},
        by=str(actor.get("email") or ""),
        model=str((body or {}).get("model") or "") or None,
    )
    if not hit:
        return JSONResponse({"success": True, "look_again": ["Talep bulunamadı."]})
    return JSONResponse({"success": True, **hit})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    payload = boxespy.health_status()
    payload["auth_required"] = _auth_on()
    commit = os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT") or "local"
    payload["deployment"] = {"commit": commit[:12] if commit != "local" else commit}
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
    from persist.rate_limit import check

    ip = request.client.host if request.client else "anon"
    if not check("beta", ip, limit=5, window_sec=3600):
        return JSONResponse({"success": True, "look_again": ["Rate limit. Try again later."]}, status_code=429)
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


@mcp.custom_route("/api/catalog", methods=["GET"])
async def api_catalog(request: Request) -> Response:
    from catalog import public_catalog
    from profiles import MATERIALS

    payload = public_catalog()
    payload["materials"] = list(MATERIALS.values())
    return JSONResponse(payload)


@mcp.custom_route("/api/studio", methods=["GET"])
async def api_studio(request: Request) -> Response:
    from studio import overview, studio_action

    action = (request.query_params.get("action") or "overview").strip().lower()
    if action in {"", "overview"}:
        return JSONResponse(overview())
    payload = {k: request.query_params.get(k) for k in request.query_params}
    return JSONResponse(
        studio_action(
            action,
            name=request.query_params.get("name") or "",
            project_id=request.query_params.get("project_id") or "",
            role=request.query_params.get("role") or "workshop",
            payload=payload,
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
            payload=body,
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
                plt=payload.get("plt"),
                plt_base64=payload.get("plt_base64"),
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
            primitives=merged.get("primitives"),
            reference_markings=merged.get("reference_markings"),
            parameters=params,
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


def _file_media(name: str, fallback: str = "application/octet-stream") -> str:
    suffix = Path(name).suffix.lower()
    return {
        ".svg": "image/svg+xml",
        ".dxf": "image/vnd.dxf",
        ".png": "image/png",
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".webp": "image/webp",
    }.get(suffix, fallback)


def _authorize_output_file(request: Request, filename: str):
    from keys import auth_required, current_auth, resolve_bearer
    from persist.authz import authorize_customer_file
    from supabase_auth import session_user

    principal = current_auth.get()
    if not principal:
        auth = request.headers.get("authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        if token:
            principal = resolve_bearer(token)
    if not principal:
        principal = session_user(request.cookies.get("lmcp_sid"))
    return authorize_customer_file(filename, principal, auth_on=auth_required()), principal


def _editor_denied(decision: dict, principal, filename: str) -> Response:
    reason = decision.get("reason")
    if reason == "expired":
        code, message, status = "expired", "Bu dosyanın 24 saatlik saklama süresi doldu. Yeni bir dosya oluşturabilirsiniz.", 410
    elif not principal and reason in {"forbidden", "unknown"}:
        code, message, status = "signin_required", "Bu dosyayı açmak için dosyayı oluşturduğunuz hesapla giriş yapın.", 401
    else:
        code, message, status = "unavailable", "Dosya bulunamadı veya bu hesaba ait değil.", 404
    payload = {"success": False, "code": code, "look_again": [message]}
    if status == 401:
        payload["signin_url"] = "/account?next=" + quote("/out/" + quote(filename, safe=""), safe="")
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "private, no-store"})


@mcp.custom_route("/api/editor/{filename}", methods=["GET"])
async def api_editor(request: Request) -> Response:
    from workshop import editor_context
    from persist.storage import StorageService
    filename = _safe_download_name(request.path_params["filename"])
    try:
        decision, principal = _authorize_output_file(request, filename)
        if not decision.get("allow"):
            return _editor_denied(decision, principal, filename)
        artifact = decision.get("artifact")
        source = str(artifact.get("source_file_id") or filename) if artifact else filename
        data = editor_context(source)
        raw = StorageService().get(str(artifact["storage_path"])) if artifact else boxespy._safe_output_file(source).read_bytes()
        data["svg"] = raw.decode("utf-8")
        data["expires_at"] = artifact.get("expires_at") if artifact else None
        return JSONResponse(data, headers={"Cache-Control": "private, no-store"})
    except FileNotFoundError:
        return _editor_denied({"reason": "unknown"}, True, filename)
    except (OSError, ValueError):
        return JSONResponse({"success": False, "code": "temporarily_unavailable", "look_again": ["Dosyaya şu anda ulaşılamıyor. Biraz sonra tekrar deneyin."]}, status_code=503, headers={"Retry-After": "3", "Cache-Control": "no-store"})


@mcp.custom_route("/api/editor/{filename}/{action}", methods=["POST"])
async def api_editor_action(request: Request) -> Response:
    from workshop import editor_context
    from editor_service import editor_action
    filename = _safe_download_name(request.path_params["filename"])
    decision, principal = _authorize_output_file(request, filename)
    if not decision.get("allow"):
        return _editor_denied(decision, principal, filename)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Geçersiz istek.")
        artifact = decision.get("artifact")
        source = str(artifact.get("source_file_id") or filename) if artifact else filename
        context = editor_context(source)
        if not context.get("editable"):
            raise ValueError("Bu dosyada parametrik proje bulunamadı.")
        from keys import current_auth
        token = current_auth.set(principal)
        try:
            return JSONResponse(editor_action(request.path_params["action"], body, context, _public_base(request)))
        finally:
            current_auth.reset(token)
    except (ValueError, TypeError, KeyError) as exc:
        return JSONResponse({"success": False, "look_again": [str(exc)]}, status_code=400)


@mcp.custom_route("/out/{filename}", methods=["GET"])
@mcp.custom_route("/edit/{filename}", methods=["GET"])
async def file_open_page(request: Request) -> Response:
    filename = _safe_download_name(request.path_params["filename"])
    decision, principal = _authorize_output_file(request, filename)
    if not decision.get("allow"):
        return _missing_output(request, signed_in=bool(principal), expired=decision.get("reason") == "expired")
    if Path(filename).suffix.lower() == ".svg":
        page = WEB_DIR / "editor.html"
        if page.is_file():
            return FileResponse(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "private, no-store"})
    safe = html.escape(filename, quote=True)
    body = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>{safe} — LaserMCP</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{margin:0;font:16px/1.5 'Segoe UI',sans-serif;background:#fafafa;color:#111}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid #e4e4e4}}
a.btn{{display:inline-flex;padding:10px 16px;background:#e10600;color:#fff;text-decoration:none;font-weight:600}}
.frame{{margin:20px;padding:16px;background:#fff;border:1px solid #e4e4e4;min-height:50vh}}
.frame img,.frame object{{max-width:100%;background:#fff}}
</style></head><body>
<nav><strong>LaserMCP</strong>
<a class="btn" href="/files/{safe}" download="{safe}">İndir</a>
</nav>
<div class="frame"><object data="/files/{safe}?view=1" type="image/svg+xml" style="width:100%;min-height:60vh">
<img src="/files/{safe}?view=1" alt="{safe}">
</object></div>
</body></html>"""
    return Response(content=body, media_type="text/html; charset=utf-8", headers={"Cache-Control": "private, no-store"})


@mcp.custom_route("/files/{filename}", methods=["GET"])
async def serve_file(request: Request) -> Response:
    from persist.storage import StorageService

    filename = request.path_params["filename"]
    inline = _wants_inline_file(request)
    if Path(filename).suffix.lower() == ".svg" and _wants_svg_editor(request):
        return _redirect("/out/" + quote(_safe_download_name(filename)))
    decision, principal = _authorize_output_file(request, filename)
    if not decision.get("allow"):
        return _missing_output(request, signed_in=bool(principal), expired=decision.get("reason") == "expired")
    artifact = decision.get("artifact")
    if artifact:
        store = StorageService()
        try:
            data = store.get(str(artifact["storage_path"]))
        except FileNotFoundError:
            return _missing_output(request, signed_in=bool(principal), expired=decision.get("reason") == "expired")
        media = str(artifact.get("mime_type") or _file_media(filename))
        return _file_payload(data, str(artifact.get("source_file_id") or filename), media, inline=inline)
    try:
        path = boxespy._safe_output_file(filename)
    except FileNotFoundError:
        return _missing_output(request, signed_in=bool(principal), expired=decision.get("reason") == "expired")
    except ValueError:
        return _missing_output(request, signed_in=bool(principal), expired=decision.get("reason") == "expired")
    return _file_payload(path.read_bytes(), path.name, _file_media(path.name), inline=inline)


def mcp_http_kwargs() -> dict[str, Any]:
    """Streamable HTTP settings. Vercel is stateless JSON so ChatGPT is not tied to /tmp sessions."""
    vercel = os.environ.get("VERCEL") == "1"
    kwargs: dict[str, Any] = {
        "streamable_http_path": "/mcp",
        "host": "0.0.0.0" if vercel else HOST,
        "stateless_http": vercel,
        "json_response": vercel,
        "max_request_body_size": 20 * 1024 * 1024,
        "session_idle_timeout": None,
        "retry_interval": 3000,
    }
    if vercel:
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
    return kwargs


def create_asgi_app():
    """ASGI app for local uvicorn and Vercel (`app` export)."""
    starlette_app = mcp.streamable_http_app(**mcp_http_kwargs())
    return McpOriginAlias(BearerGate(starlette_app, AUTH_TOKEN))


app = create_asgi_app()


def main() -> None:
    import uvicorn

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
