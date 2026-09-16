"""ASGI app: the MCP endpoint plus the two dev routes the phone and browser need."""
from __future__ import annotations

import json
from pathlib import Path

from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .server import mcp, panel_state, start_recipe, _session
from .vision import SimulatedSource

UI = Path(__file__).resolve().parents[2] / "ui" / "panel.html"


async def dev_state(_request):
    return JSONResponse(panel_state())


async def dev_panel(_request):
    return HTMLResponse(UI.read_text(encoding="utf-8"))


async def dev_start(request):
    """Dev harness: start a recipe in THIS process (the MCP session lives here)."""
    slug = request.query_params.get("slug", "soffritto")
    out = start_recipe(slug)
    if "step" in request.query_params:
        _session["step_index"] = int(request.query_params["step"])
        out["step_index"] = _session["step_index"]
    return JSONResponse(out)


app = mcp.streamable_http_app()
app.router.routes.append(Route("/dev/state", dev_state))
app.router.routes.append(Route("/dev/panel", dev_panel))
app.router.routes.append(Route("/dev/start", dev_start))

# Until the vision model is wired, drive the panel from the simulator.
SimulatedSource(seconds_to_done=45).start()
