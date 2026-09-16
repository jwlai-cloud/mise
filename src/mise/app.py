"""ASGI app: the MCP endpoint, the camera intake, and the demo controls.

Three kinds of route live here:

  /mcp          the real surface. Alexa+ talks to this.
  /ingest       real frames from the phone. The only write path that isn't a scenario.
  /dev/*        the demo rig - a panel, a phone camera page, and an operator
                remote that can jump to any of the four verdicts on command.

The dev routes exist because a demo you cannot replay is a demo you get one
take of.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .server import mcp, panel_state, start_recipe, _session
from .vision import DEFAULT_SCENARIO, SCENARIOS, ScenarioSource, ingest_frame

log = logging.getLogger(__name__)

UI = Path(__file__).resolve().parents[2] / "ui"

# The scenarios are written against step 1 of the soffritto - the onions, the
# step with the 0.8 gate. The demo recipe is the same gates on a compressed
# clock so the spoken estimate matches what the panel is doing.
DEMO_RECIPE, DEMO_STEP = "soffritto-demo", 1

SOURCE = ScenarioSource(DEFAULT_SCENARIO)

# Exactly one writer to STORE at a time. The scripted pan owns it until a real
# frame lands; after that the camera does, until an operator arms a scenario.
_live_camera = False


def stop_scenarios(why: str) -> None:
    global _live_camera
    if not _live_camera:
        _live_camera = True
        SOURCE.stop()
        log.info("scripted pan stopped: %s", why)

# One frame in flight at a time. Drop the rest rather than queue them: a stale
# answer is worse than no answer, and state.is_stale reports the gap honestly.
_ingesting = asyncio.Lock()


def _page(name: str):
    async def route(_request):
        return HTMLResponse((UI / name).read_text(encoding="utf-8"))
    return route


async def dev_state(_request):
    return JSONResponse(panel_state())


async def dev_start(request):
    """Start a recipe in THIS process (the MCP session lives here)."""
    slug = request.query_params.get("slug", DEMO_RECIPE)
    out = start_recipe(slug)
    if "step" in request.query_params:
        _session["step_index"] = int(request.query_params["step"])
    # Report the step the session is actually on, not the one start_recipe reset to.
    out["step"] = _session["step_index"]
    return JSONResponse(out)


async def dev_scenarios(_request):
    return JSONResponse({
        "scenarios": sorted(SCENARIOS),
        "running": SOURCE.name,
        "elapsed": round(SOURCE.elapsed, 1),
        "source": "camera" if _live_camera else "scenario",
    })


async def dev_scenario(request):
    """The operator's remote. One call puts the whole rig in a known state."""
    global _live_camera
    name = request.query_params.get("name", SOURCE.name)
    at = float(request.query_params.get("at", 0))
    try:
        SOURCE.restart(name, at)
    except KeyError:
        return JSONResponse(
            {"error": f"No scenario '{name}'.", "available": sorted(SCENARIOS)},
            status_code=404,
        )
    # Put the recipe on the step the scenarios are written for, so a single
    # click is always enough to reach the verdict being demonstrated.
    start_recipe(DEMO_RECIPE)
    _session["step_index"] = DEMO_STEP
    # Arming a scenario takes the store back from the camera, so an operator can
    # always recover the rig mid-shoot without restarting the server.
    if _live_camera:
        _live_camera = False
        SOURCE.resume()
    return JSONResponse({"running": name, "at": at, "recipe": DEMO_RECIPE,
                         "step": DEMO_STEP, "source": "scenario"})


async def dev_reset(_request):
    """Wipe learned calibration and the session ledger.

    Calibration surviving a restart is the point of AgentCore Memory, not a
    bug - but it means a test run, or the Memory demo itself, leaves the gate
    moved. Without this the next take opens with a pan that reads 0.91 against
    a 0.95 threshold and the panel says NOT YET forever, on camera, for no
    visible reason.
    """
    from .memory import CALIBRATION
    from .policy import LEDGER

    was = dict(CALIBRATION._local)
    CALIBRATION._local.clear()
    CALIBRATION._save_local()
    LEDGER.gate_passed_at = None
    LEDGER.refusals.clear()
    LEDGER.corrections.clear()
    return JSONResponse({"cleared": was, "backend": CALIBRATION.backend})


async def ingest(request):
    """Real frames from the phone. Never called by an MCP tool."""
    # Stamp the shutter BEFORE the model runs. A vision call costs seconds, and
    # is_stale has to measure the age of the view, not our own latency.
    captured_at = time.time()
    body = await request.body()
    if not body:
        return JSONResponse({"error": "empty frame"}, status_code=400)
    # Check the lock AFTER reading the body, immediately before taking it.
    # Checking earlier lets a second frame pass the test and then queue on the
    # lock instead of being dropped, which is the backlog this design exists to
    # avoid: by the time it ran, the pan would have moved on.
    if _ingesting.locked():
        return JSONResponse({"dropped": True, "reason": "a frame is already in flight"})
    async with _ingesting:
        try:
            wrote = await run_in_threadpool(ingest_frame, body, captured_at)
        except NotImplementedError:
            # The Bedrock call is the one unimplemented piece. Say so plainly
            # rather than 500-ing at a phone that is doing nothing wrong.
            return JSONResponse(
                {"accepted": False, "bytes": len(body),
                 "reason": "vision backend not wired yet - run a /dev/scenario instead"},
                status_code=501,
            )
    if wrote:
        # A real camera has arrived, so the scripted pan must stop writing.
        # Both write to the same STORE and the scenario ticks at 1 Hz, so
        # leaving it running means the script wins the last write and the panel
        # shows a simulated pan while a real one is on the hob. Silent, and
        # fatal to the demo it was built for.
        stop_scenarios("a real frame arrived")
    # A dropped frame is not an error: the view simply ages until the gate
    # refuses. Report it honestly rather than acknowledging a discard.
    return JSONResponse({"accepted": bool(wrote), "bytes": len(body),
                         "source": "camera" if _live_camera else SOURCE.name})


app = mcp.streamable_http_app(stateless_http=True, json_response=True,
                              host="0.0.0.0")
for path, handler in (
    ("/ingest", ingest),
    ("/dev/state", dev_state),
    ("/dev/start", dev_start),
    ("/dev/scenario", dev_scenario),
    ("/dev/scenarios", dev_scenarios),
    ("/dev/reset", dev_reset),
    ("/dev/panel", _page("panel.html")),
    ("/dev/camera", _page("camera.html")),
    ("/dev/control", _page("control.html")),
):
    app.router.routes.append(
        Route(path, handler, methods=["POST"] if path == "/ingest" else ["GET"])
    )

SOURCE.start()
