"""Laser mcp — HTTP UI + MCP. No shell tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp.server.mcpserver import MCPServer

import boxes_adapter as boxespy
import payas_cad

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))
PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "")
WEB_DIR = Path(__file__).resolve().parent / "web"

mcp = MCPServer("Laser mcp")


def _public_base(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


def _error(exc: Exception, status: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": str(exc)}, status_code=status)


@mcp.tool(description="Payas STEM defaults: 3mm kavak, kerf 0.15, 1500x3000, SVG.")
def payas_defaults() -> dict[str, Any]:
    return boxespy.payas_defaults()


@mcp.tool(description="List Payas STEM CAD product tools. Use these instead of Boxes.py source.")
def list_cad_tools() -> dict[str, Any]:
    return payas_cad.list_cad_tools()


@mcp.tool(description="List Boxes.py generators. Optional group filter. Payas defaults are included.")
def list_generators(group: str | None = None) -> dict[str, Any]:
    return boxespy.list_generators(group)


@mcp.tool(description="Return parameter schema for one Boxes.py generator.")
def get_generator_schema(generator: str) -> dict[str, Any]:
    return boxespy.get_generator_schema(generator)


@mcp.tool(description="Generate an SVG via a Boxes.py class. Payas defaults apply unless overridden.")
def generate_svg(generator: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    return boxespy.generate_svg(generator, parameters, public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


@mcp.tool(description="Validate a generated SVG: well-formed XML and 1500×3000 mm bed fit.")
def validate_svg(file_id: str) -> dict[str, Any]:
    return boxespy.validate_svg(file_id)


@mcp.tool(description="Return a preview URL for a previously generated SVG.")
def render_preview(file_id: str) -> dict[str, Any]:
    return boxespy.render_preview(file_id, public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


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
        public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}",
    )


@mcp.tool(description="Payas STEM robot kumbara (Hayal kumbara) kesim SVG.")
def create_robot_bank() -> dict[str, Any]:
    return payas_cad.create_robot_bank(public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


@mcp.tool(description="Payas STEM ressam/çizim robotu kesim SVG.")
def create_drawing_robot() -> dict[str, Any]:
    return payas_cad.create_drawing_robot(public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


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
        public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}",
    )


@mcp.tool(description="Payas STEM statik yat kiti kesim SVG.")
def create_yacht() -> dict[str, Any]:
    return payas_cad.create_yacht(public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


@mcp.tool(description="Payas STEM açık şase astronot kiti kesim SVG.")
def create_astronaut() -> dict[str, Any]:
    return payas_cad.create_astronaut(public_base_url=PUBLIC_BASE_URL or f"http://{HOST}:{PORT}")


@mcp.custom_route("/", methods=["GET"])
async def ui(request: Request) -> Response:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")


@mcp.custom_route("/api/status", methods=["GET"])
async def api_status(request: Request) -> Response:
    return JSONResponse(
        {
            "name": "Laser mcp",
            "status": "ok",
            "mcp": "/mcp",
            "ui": "/",
            "boxes_path": boxespy.BOXES_PATH,
            "defaults": boxespy.PAYAS_DEFAULTS,
            "tools": [
                "payas_defaults",
                "list_cad_tools",
                "list_generators",
                "get_generator_schema",
                "generate_svg",
                "validate_svg",
                "render_preview",
                "create_traffic_light",
                "create_robot_bank",
                "create_drawing_robot",
                "create_product_box",
                "create_yacht",
                "create_astronaut",
            ],
            "cad_products": payas_cad.CAD_PRODUCTS,
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


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
        return JSONResponse(boxespy.validate_svg(body.get("file_id") or "Laser mcp.svg"))
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/preview", methods=["GET"])
async def api_preview(request: Request) -> Response:
    file_id = request.query_params.get("file_id") or "Laser mcp.svg"
    try:
        return JSONResponse(boxespy.render_preview(file_id, public_base_url=_public_base(request)))
    except FileNotFoundError as exc:
        return _error(exc, 404)
    except Exception as exc:
        return _error(exc)


@mcp.custom_route("/api/cad/products", methods=["GET"])
async def api_cad_products(request: Request) -> Response:
    return JSONResponse(payas_cad.list_cad_tools())


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
    return FileResponse(path, media_type="image/svg+xml", filename=path.name)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
    )
