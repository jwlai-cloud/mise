"""The hot graph: a real Strands multi-agent graph on the slow plane.

This is where the agentic reasoning lives, and it deliberately does NOT live on
the MCP request path. Alexa+ budgets ~500ms per tool round-trip; a multi-agent
graph does not fit and never will. So the graph runs on its own clock at ~0.3Hz
and writes CookState to a cache, and the tools only read it.

  frame ──▶ perceive ──┬──▶ critique ──┐
                       │  (conditional) │
                       └──▶ risk ───────┼──▶ arbitrate ──▶ STORE
                          (every tick)  │   (deterministic)
                                        │
                       └────────────────┘

Each node earns its place by a distinct trigger, model tier, or failure domain:

  perceive    every frame. The only node that must call a vision model.
  critique    CONDITIONAL - only near the gate or under low confidence, which is
              where a mistake is expensive. Asked to REFUTE, not to agree. Its
              dissent can only lower confidence, never raise it.
  risk        every frame, in PARALLEL with the critic rather than downstream of
              it, because danger must never be gated on the perception agent's
              confidence (invariant 3).
  arbitrate   deliberately NOT an agent. A deterministic merge and the single
              writer to STORE, so the write path stays unit-testable with no
              model in it.

Runs offline: ScriptedModel drives real Agent instances with no credentials, so
the graph's structure, its conditional edge and the arbiter are all exercised by
tests. Swap in BedrockModel and the same graph runs against a real model.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .perception import (OBSTRUCTION_CEILING, VIEW_CEILING, PerceptionError,
                         Reading, clamp_confidence, validate)
from .state import STORE

log = logging.getLogger(__name__)

# Only near the gate is a second opinion worth paying for. Everywhere else the
# critic would burn a model call to agree.
CRITIC_CONFIDENCE_TRIGGER = 0.75
CRITIC_GATE_MARGIN = 0.10


# ---------- what each agent must return ----------

class PanReading(BaseModel):
    """The perception agent's structured output. Mirrors CookState plus the two
    fields that set the confidence ceiling."""

    view: Literal["clear", "partly_obscured", "obscured", "no_pan"]
    obstructions: list[str] = Field(default_factory=list)
    risk: Literal["none", "watch", "urgent"] = "none"
    stage: str = ""
    doneness: float = 0.0
    confidence: float = 0.0
    evidence: str = ""


class CriticVerdict(BaseModel):
    """The critic is asked what would make the reading WRONG, not whether it agrees."""

    would_be_wrong: bool = Field(description="True if this judgement is unsafe to act on.")
    max_confidence: float = Field(default=1.0, description="Ceiling this reading deserves.")
    reason: str = ""


class RiskReport(BaseModel):
    """Danger, judged independently of readiness."""

    risk: Literal["none", "watch", "urgent"] = "none"
    evidence: str = ""


# ---------- prompts ----------

PERCEIVE_PROMPT = """You are the eye of a cooking assistant. Report only what is visible.

Your numbers go to a deterministic gate, not to a person. A refusal is a correct,
useful answer; a confident wrong answer puts someone in front of a ruined pan.

Say what is in the way BEFORE you give a confidence. Steam, a lid, glare, darkness,
motion blur, a hand over the food, or no pan in frame all mean you cannot judge.

Report smoke, flame or scorching regardless of how well you can see."""

CRITIQUE_PROMPT = """You are a sceptic. You are given another agent's reading of a pan.

Your job is NOT to agree. Name what would make this judgement wrong, and decide
whether it is safe to act on. Default to would_be_wrong=true when uncertain.

You may only LOWER the confidence this reading deserves, never raise it. Saying
"looks fine" costs nothing and buys nothing; catching one over-confident reading
on a steamed lens is the entire reason you exist."""

RISK_PROMPT = """You watch for danger only. Ignore readiness entirely.

Report urgent for smoke, flame or scorching. Report watch for ambiguous haze.
Being unsure points UP, not down — never lower your report because the view is
poor. A pan that might be burning is worth interrupting for."""


# ---------- nodes ----------

def _reading_from(state: Any, node_id: str) -> PanReading | None:
    """Pull one node's structured output back off the graph state."""
    try:
        result = state.results[node_id].result
    except (AttributeError, KeyError, TypeError):
        return None
    for attr in ("structured_output", "output"):
        got = getattr(result, attr, None)
        if isinstance(got, PanReading):
            return got
    return None


def near_the_gate(gate_doneness: float = 0.8):
    """Edge condition: only run the critic where a mistake is expensive.

    Strands calls this with the GraphState before deciding whether to traverse
    the edge, so a clear, confident, mid-step frame simply never pays for a
    second model call. That is what keeps the critic affordable at 0.3Hz.
    """

    def condition(state: Any) -> bool:
        r = _reading_from(state, "perceive")
        if r is None:
            return False
        return (r.confidence < CRITIC_CONFIDENCE_TRIGGER
                or abs(r.doneness - gate_doneness) < CRITIC_GATE_MARGIN)

    return condition


def arbitrate(perception: PanReading | None,
              critique: CriticVerdict | None,
              risk: RiskReport | None) -> Reading:
    """Merge three opinions into one reading. No model, on purpose.

    Rules, in the order the gate itself applies them:
      1. Danger wins outright and is never lowered by anything else.
      2. Confidence only ever falls - from the view ceiling, then from the
         critic's dissent. Neither can raise it.
      3. Doneness stays honest. We clamp what we TRUST, not what we SAW.
    """
    if perception is None:
        raise PerceptionError("no perception result to arbitrate")

    raw = perception.model_dump()

    # 1. Danger: the risk agent can only escalate.
    if risk is not None:
        rank = {"none": 0, "watch": 1, "urgent": 2}
        if rank.get(risk.risk, 0) > rank.get(raw.get("risk", "none"), 0):
            raw["risk"] = risk.risk
            if risk.evidence:
                raw["evidence"] = risk.evidence

    # 2. The view ceiling, from the perception agent's own admission.
    raw = clamp_confidence(raw)

    # 3. The critic's dissent, which can only lower.
    if critique is not None and critique.would_be_wrong:
        raw["confidence"] = min(raw.get("confidence", 0.0), critique.max_confidence)
        if critique.reason:
            raw["evidence"] = critique.reason

    return validate(raw)


# ---------- offline model provider ----------

class ScriptedModel:
    """A Strands Model that answers from a queue. No network, no credentials.

    Lets the graph's real structure - the conditional edge, the parallel risk
    node, the arbiter - be exercised by tests. The alternative is asserting that
    the topology is correct, which is not a test.
    """

    # Strands reads this on Agent construction to decide whether it may attach a
    # conversation manager. A scripted model carries no server-side state.
    stateful = False

    def __init__(self, payloads: list[dict] | None = None) -> None:
        self.payloads = list(payloads or [])
        self.calls: list[str] = []

    def get_config(self) -> dict:
        return {}

    def update_config(self, **_: Any) -> None:
        pass

    def _next(self) -> dict:
        if not self.payloads:
            raise PerceptionError("scripted model exhausted")
        return self.payloads.pop(0)

    async def structured_output(self, output_model, prompt, system_prompt=None, **_):
        yield {"output": output_model(**self._next())}

    async def stream(self, messages, tool_specs=None, system_prompt=None, **_):
        # Structured output is forced through a tool call, so the stream has to
        # emit a toolUse block - a text block is rejected as a failure to comply.
        name = tool_specs[0]["name"] if tool_specs else "answer"
        self.calls.append(name)
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": "t1"}}}}
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(self._next())}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}


def bedrock_model(model_id: str | None = None):
    """The real thing. Imported lazily so no-credential runs never touch boto3."""
    import os

    from strands.models import BedrockModel

    return BedrockModel(
        model_id=model_id or os.getenv(
            "MISE_VISION_MODEL", "au.anthropic.claude-haiku-4-5-20251001-v1:0"),
        region_name=os.getenv("AWS_REGION", "ap-southeast-2"),
        temperature=0,
    )


# ---------- the graph ----------

def build_hot_graph(perceive_model, critique_model=None, risk_model=None,
                    gate_doneness: float = 0.8):
    """Wire the per-frame graph. Returns a Strands Graph.

    Separate model handles per node on purpose: perception and risk want a fast
    cheap tier, and a critic that is the same model answering the same question
    twice is not a second opinion.
    """
    from strands import Agent
    from strands.multiagent import GraphBuilder

    perceive = Agent(model=perceive_model, name="perceive",
                     system_prompt=PERCEIVE_PROMPT, structured_output_model=PanReading)
    critique = Agent(model=critique_model or perceive_model, name="critique",
                     system_prompt=CRITIQUE_PROMPT, structured_output_model=CriticVerdict)
    risk = Agent(model=risk_model or perceive_model, name="risk",
                 system_prompt=RISK_PROMPT, structured_output_model=RiskReport)

    b = GraphBuilder()
    b.add_node(perceive, "perceive")
    b.add_node(critique, "critique")
    b.add_node(risk, "risk")
    b.add_edge("perceive", "critique", condition=near_the_gate(gate_doneness))
    b.add_edge("perceive", "risk")
    b.set_entry_point("perceive")
    # Drop the tick rather than let it queue: a late answer is worse than none,
    # and is_stale reports the gap honestly.
    b.set_execution_timeout(20)
    return b.build()


async def judge_frame(graph, goal: str) -> Reading:
    """One frame through the graph, arbitrated. Pure - does not touch STORE.

    Raises PerceptionError on anything unusable, so the caller can apply the
    rule that holds everywhere on this path: a failure writes NOTHING, and the
    last frame ages until the gate refuses on its own.
    """
    try:
        result = await graph.invoke_async(f"Report this pan against the goal: {goal}")
    except Exception as exc:
        raise PerceptionError(f"hot graph failed ({type(exc).__name__}): {exc}") from exc

    def out(node_id, kind):
        try:
            r = result.results[node_id].result
        except (AttributeError, KeyError, TypeError):
            return None
        got = getattr(r, "structured_output", None)
        return got if isinstance(got, kind) else None

    perception = out("perceive", PanReading)
    reading = arbitrate(perception, out("critique", CriticVerdict), out("risk", RiskReport))

    # Strands traces the mechanics - which agent ran, tokens, tool calls - but
    # nothing about a pan. The trajectory evaluator needs the domain values to
    # judge "confidence only ever fell" and "the critic ran where it mattered",
    # so emit them on one span of our own. Without this the evaluator can see
    # the shape of a run and none of its meaning.
    _record_frame_span(perception, reading)

    log.info("graph ran %s -> %s",
             [n.node_id for n in getattr(result, "execution_order", [])], reading.evidence)
    return reading


def _record_frame_span(perception: PanReading | None, reading: Reading) -> None:
    """One span carrying what the frame actually decided. Never raises: a
    telemetry failure must not drop a frame."""
    try:
        from opentelemetry import trace as trace_api

        tracer = trace_api.get_tracer("mise.agents")
        with tracer.start_as_current_span("mise.frame") as span:
            if perception is not None:
                span.set_attribute("mise.doneness", perception.doneness)
                span.set_attribute("mise.confidence_in", perception.confidence)
                span.set_attribute("mise.view", perception.view)
            span.set_attribute("mise.confidence_out", reading.confidence)
            span.set_attribute("mise.risk", reading.risk)
            span.set_attribute("mise.wrote", True)
    except Exception as exc:                      # no otel, no provider, no matter
        log.debug("frame span not recorded: %s", exc)


class GraphVision:
    """The hot graph, wearing the VisionModel interface.

    This is what makes the agentic path a drop-in: `ingest_frame` already
    validates, timestamps by the shutter, and drops the frame on failure, and
    all of that is tested. Swapping one model call for a multi-agent graph
    changes nothing downstream.
    """

    def __init__(self, graph=None, gate_doneness: float = 0.8) -> None:
        self._graph = graph
        self._gate = gate_doneness

    @property
    def graph(self):
        if self._graph is None:                # built lazily: touches boto3
            m = bedrock_model()
            self._graph = build_hot_graph(m, m, m, gate_doneness=self._gate)
        return self._graph

    def judge(self, jpeg: bytes, goal: str) -> Reading:
        import asyncio

        # ingest_frame already runs us in a worker thread, so there is no loop
        # in this thread to conflict with.
        return asyncio.run(judge_frame(self.graph, goal))


async def run_once(graph, goal: str, captured_at: float | None = None) -> Reading | None:
    """judge_frame plus the STORE write. For a standalone loop with no server."""
    captured_at = time.time() if captured_at is None else captured_at
    try:
        reading = await judge_frame(graph, goal)
    except PerceptionError as exc:
        log.warning("dropped frame: %s", exc)
        return None
    STORE.write(updated_at=captured_at, **reading.as_state_fields())
    return reading


def enable_tracing(console: bool = False):
    """Emit OpenTelemetry spans for every node in the graph.

    This is the evidence that the critic is conditional rather than decorative:
    a waterfall showing `critique` firing on one tick in twelve proves the edge
    is doing work. Exports to anything that speaks OTLP - AgentCore
    Observability, or a local collector.

    Set OTEL_EXPORTER_OTLP_ENDPOINT before calling.
    """
    from strands.telemetry import StrandsTelemetry

    t = StrandsTelemetry()
    t.setup_console_exporter() if console else t.setup_otlp_exporter()
    log.info("tracing enabled (%s)", "console" if console else "otlp")
    return t
