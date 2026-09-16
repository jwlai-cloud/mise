"""Mise - the cooking assistant that tells you to wait.

Self-hosted MCP server, streamable HTTP, MCP spec 2025-11-25.

Every tool here reads cached state and returns immediately. Nothing in this
file calls a vision model. That is the point: Alexa+ allows roughly 500ms
per tool round-trip, so the slow work happens on its own clock in vision.py
and lands in state.STORE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .gate import decide
from .memory import CALIBRATION
from .policy import LEDGER
from .steering import guarded_advance
from .recipes import REGISTRY
from .state import STORE

PANEL_URI = "ui://mise/panel"
UI_DIR = Path(__file__).resolve().parents[2] / "ui"

mcp = FastMCP(
    "mise",
    instructions=(
        "Mise watches a pan through a camera and decides whether the cook may move "
        "to the next step. Prefer check_doneness over guessing. If it returns "
        "'refuse', say so plainly - do not invent an answer about food safety."
    ),
    stateless_http=True,
    json_response=True,
)

# Session state. One cook at a time; a real deployment keys this per user.
_session: dict[str, Any] = {"recipe": None, "step_index": 0}


class DecisionOut(BaseModel):
    verdict: str = Field(description="proceed | wait | refuse | abort")
    say: str = Field(description="Exactly what to speak aloud. Under 30 seconds.")
    reason: str
    seconds_remaining: int | None = None
    step: int
    instruction: str
    doneness: float
    confidence: float


def _panel_meta(visibility: list[str] | None = None) -> dict[str, Any]:
    ui: dict[str, Any] = {"resourceUri": PANEL_URI}
    if visibility:
        ui["visibility"] = visibility
    return {"ui": ui}


@mcp.tool(
    name="start_recipe",
    description="Begin a recipe. Call this before check_doneness. Returns the first instruction.",
    meta=_panel_meta(),
)
def start_recipe(slug: str = "soffritto") -> dict[str, Any]:
    recipe = REGISTRY.get(slug)
    if recipe is None:
        return {
            "error": f"No recipe '{slug}'.",
            "available": sorted(REGISTRY),
            "next_step": "Ask the cook to choose one of the available recipes.",
        }
    _session["recipe"] = recipe.slug
    _session["step_index"] = 0
    first = recipe.step(0)
    return {"title": recipe.title, "step": 0, "instruction": first.instruction, "goal": first.goal}


@mcp.tool(
    name="check_doneness",
    description=(
        "Ask whether the cook may move to the next step yet. This is the primary tool. "
        "It may answer 'wait' or 'refuse' - relay that honestly rather than encouraging "
        "the cook to proceed."
    ),
    meta=_panel_meta(),
    annotations={"readOnlyHint": True, "openWorldHint": True},
)
def check_doneness() -> DecisionOut:
    recipe = REGISTRY.get(_session["recipe"] or "")
    if recipe is None:
        return DecisionOut(
            verdict="refuse", say="Which recipe are we cooking?",
            reason="no recipe started", step=0, instruction="", doneness=0.0, confidence=0.0,
        )
    step = recipe.step(_session["step_index"])
    # The cook's own threshold for this step, learned from their corrections.
    step.gate_doneness = CALIBRATION.gate_for(recipe.slug, step.index, step.gate_doneness)
    state = STORE.read()
    d = decide(state, step)

    # Feed the policy ledger: what the agent has observed and said this session.
    suppressed = False
    if d.verdict == "proceed":
        LEDGER.note_gate_passed()
    elif d.verdict in ("wait", "refuse"):
        if LEDGER.may_speak_refusal(step.index).allowed:
            LEDGER.note_refusal(step.index)
        else:
            # Rule 2: already said this within two minutes. The panel keeps
            # showing the detail; the voice shortens rather than nagging.
            suppressed = True
    say = "Still not yet." if suppressed else d.spoken()
    return DecisionOut(
        verdict=d.verdict, say=say, reason=d.reason,
        seconds_remaining=d.seconds_remaining, step=step.index,
        instruction=step.instruction, doneness=state.doneness, confidence=state.confidence,
    )


@mcp.tool(
    name="advance_step",
    description="Move to the next step. Refuses unless check_doneness currently returns 'proceed'.",
    meta=_panel_meta(),
)
def advance_step() -> dict[str, Any]:
    recipe = REGISTRY.get(_session["recipe"] or "")
    if recipe is None:
        return {"advanced": False, "reason": "No recipe started."}
    # Enforced in three places, deliberately: here, in AgentCore Policy
    # (policies/mise.dogwood), and at the tool boundary by Strands steering.
    allowed = guarded_advance()
    d = decide(STORE.read(), recipe.step(_session["step_index"]))
    if not allowed.allowed or d.verdict != "proceed":
        return {
            "advanced": False,
            "verdict": d.verdict,
            "reason": d.spoken(),
            "policy_rule": allowed.rule,
            "policy_explanation": allowed.explanation,
        }
    _session["step_index"] = min(_session["step_index"] + 1, len(recipe.steps) - 1)
    nxt = recipe.step(_session["step_index"])
    return {"advanced": True, "step": nxt.index, "instruction": nxt.instruction, "goal": nxt.goal}


@mcp.tool(
    name="panel_state",
    description="Internal: current pan state for the live panel. Not for conversational use.",
    meta=_panel_meta(visibility=["app"]),
    annotations={"readOnlyHint": True},
)
def panel_state() -> dict[str, Any]:
    recipe = REGISTRY.get(_session["recipe"] or "")
    state = STORE.read()
    out = state.to_dict()
    if recipe is not None:
        step = recipe.step(_session["step_index"])
        d = decide(state, step)
        out |= {
            "title": recipe.title, "step": step.index, "steps_total": len(recipe.steps),
            "instruction": step.instruction, "goal": step.goal,
            "gate": step.gate_doneness, "verdict": d.verdict,
            "reason": d.reason, "seconds_remaining": d.seconds_remaining,
        }
    return out


@mcp.tool(
    name="record_correction",
    description=(
        "The cook says the last advance was wrong. direction is 'too_early' or 'too_late'. "
        "This permanently adjusts the readiness threshold for this step, for this cook."
    ),
    meta=_panel_meta(),
)
def record_correction(direction: str, note: str = "") -> dict[str, Any]:
    recipe = REGISTRY.get(_session["recipe"] or "")
    if recipe is None or direction not in ("too_early", "too_late"):
        return {"recorded": False, "reason": "Need a running recipe and 'too_early' or 'too_late'."}
    step = recipe.step(_session["step_index"])
    old = CALIBRATION.gate_for(recipe.slug, step.index, step.gate_doneness)
    new = CALIBRATION.record_correction(recipe.slug, step.index, old, direction, note)
    LEDGER.note_correction(step.index)
    give_up = LEDGER.should_stop_gating(step.index)
    return {
        "recorded": True, "step": step.index, "was": old, "now": new,
        "backend": CALIBRATION.backend,
        "say": (
            f"Noted. I'll wait {'longer' if direction == 'too_early' else 'less'} on that step from now on."
            + (" And I'll stop gating this step - I've been wrong too often." if give_up.allowed else "")
        ),
    }


@mcp.resource(
    PANEL_URI,
    name="Mise panel",
    description="Live pan-readiness panel. Polls panel_state; keeps updating after the voice turn ends.",
    mime_type="text/html;profile=mcp-app",
)
def panel() -> str:
    return (UI_DIR / "panel.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
