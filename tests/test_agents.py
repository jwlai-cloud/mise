"""The hot graph, exercised for real with no credentials.

These drive actual Strands Agent instances through an actual GraphBuilder graph.
The only thing faked is the model provider, so the topology, the conditional
edge and the arbiter are genuinely executed rather than asserted about.
"""
import asyncio, sys
sys.path.insert(0, "src")
from mise.agents import (CriticVerdict, PanReading, RiskReport, ScriptedModel,
                         arbitrate, build_hot_graph, near_the_gate, run_once)
from mise.gate import decide
from mise.recipes import SOFFRITTO
from mise.state import STORE

step = SOFFRITTO.step(1)          # onions: gate 0.8, min_confidence 0.6
GOAL = step.goal

CLEAR   = {"view": "clear", "obstructions": [], "risk": "none", "stage": "onions sweating",
           "doneness": 0.45, "confidence": 0.92, "evidence": "edges still firm"}
STEAMED = {"view": "obscured", "obstructions": ["steam"], "risk": "none",
           "stage": "onions sweating", "doneness": 0.88, "confidence": 0.93,
           "evidence": "looks translucent"}
NO_RISK = {"risk": "none", "evidence": ""}
SMOKE   = {"risk": "urgent", "evidence": "Dark smoke off the pan."}
AGREES  = {"would_be_wrong": False, "max_confidence": 1.0, "reason": ""}
DISSENT = {"would_be_wrong": True, "max_confidence": 0.2,
           "reason": "steam is across the lens; this reading is a guess"}


def run(coro):
    return asyncio.run(coro)


# ---------- the arbiter, in isolation ----------

def test_the_critic_can_only_lower_confidence():
    r = arbitrate(PanReading(**CLEAR), CriticVerdict(**{**AGREES, "max_confidence": 1.0}), None)
    assert r.confidence == 0.92, "an agreeing critic must not raise confidence"
    d = arbitrate(PanReading(**CLEAR), CriticVerdict(**DISSENT), None)
    assert d.confidence == 0.2, d
    print(f"critic       -> agrees {r.confidence} · dissents {d.confidence}")


def test_danger_escalates_and_is_never_lowered():
    up = arbitrate(PanReading(**CLEAR), None, RiskReport(**SMOKE))
    assert up.risk == "urgent" and "smoke" in up.evidence.lower(), up
    # A 'none' report must not downgrade an urgent perception.
    hot = dict(CLEAR, risk="urgent", evidence="Scorching.")
    down = arbitrate(PanReading(**hot), None, RiskReport(**NO_RISK))
    assert down.risk == "urgent", "risk agent must not be able to de-escalate"
    print(f"risk         -> escalates to {up.risk}, cannot de-escalate")


def test_danger_survives_a_dissenting_critic():
    """Invariant 3: danger is never gated on confidence, including the critic's."""
    r = arbitrate(PanReading(**STEAMED), CriticVerdict(**DISSENT), RiskReport(**SMOKE))
    assert r.risk == "urgent" and r.confidence <= 0.2, r
    from mise.state import CookState
    assert decide(CookState(**r.as_state_fields()), step).verdict == "abort"
    print(f"danger+doubt -> abort at confidence {r.confidence}")


def test_doneness_stays_honest_while_trust_falls():
    r = arbitrate(PanReading(**STEAMED), CriticVerdict(**DISSENT), None)
    assert r.doneness == 0.88, "we clamp what we trust, not what we saw"
    assert r.confidence <= 0.2
    print(f"steamed      -> doneness {r.doneness} kept, confidence {r.confidence}")


# ---------- the conditional edge ----------

class FakeState:
    def __init__(self, reading): self.results = {"perceive": type("R", (), {"result": type("O", (), {"structured_output": reading})()})()}


def test_the_critic_only_runs_where_a_mistake_is_expensive():
    cond = near_the_gate(0.8)
    mid   = PanReading(**dict(CLEAR, doneness=0.45, confidence=0.92))
    edge  = PanReading(**dict(CLEAR, doneness=0.78, confidence=0.92))
    murky = PanReading(**dict(CLEAR, doneness=0.30, confidence=0.40))
    assert cond(FakeState(mid)) is False,  "a clear mid-step frame should not pay for a critic"
    assert cond(FakeState(edge)) is True,  "near the gate is exactly where it must run"
    assert cond(FakeState(murky)) is True, "low confidence must trigger it"
    print("conditional  -> mid=skip · near-gate=run · low-confidence=run")


# ---------- the whole graph, executed ----------

def test_the_graph_runs_end_to_end_offline():
    graph = build_hot_graph(ScriptedModel([CLEAR]),
                            ScriptedModel([AGREES]), ScriptedModel([NO_RISK]))
    r = run(run_once(graph, GOAL))
    assert r is not None and r.doneness == 0.45, r
    assert STORE.read().evidence == "edges still firm"
    print(f"graph clean  -> {r.doneness} / {r.confidence} · {r.evidence!r}")


def test_a_steamed_frame_ends_in_a_refusal_through_the_whole_graph():
    """The headline path: the perception agent over-claims, the view ceiling and
    the critic both pull it down, and the gate refuses."""
    graph = build_hot_graph(ScriptedModel([STEAMED]),
                            ScriptedModel([DISSENT]), ScriptedModel([NO_RISK]))
    r = run(run_once(graph, GOAL))
    assert r is not None, "graph produced nothing"
    from mise.state import CookState
    d = decide(CookState(**r.as_state_fields()), step)
    assert d.verdict == "refuse", (d, r)
    assert r.doneness >= step.gate_doneness, "the point: past the gate and still refusing"
    print(f"graph steam  -> doneness {r.doneness} past gate {step.gate_doneness}, verdict {d.verdict}")


def test_a_dead_model_writes_nothing():
    before = STORE.read().frame_seq
    graph = build_hot_graph(ScriptedModel([]), ScriptedModel([]),
                            ScriptedModel([]))   # exhausted immediately
    assert run(run_once(graph, GOAL)) is None
    assert STORE.read().frame_seq == before, "a failed graph must not write"
    print("graph dead   -> nothing written, view ages into a refusal")


for f in (test_the_critic_can_only_lower_confidence,
          test_danger_escalates_and_is_never_lowered,
          test_danger_survives_a_dissenting_critic,
          test_doneness_stays_honest_while_trust_falls,
          test_the_critic_only_runs_where_a_mistake_is_expensive,
          test_the_graph_runs_end_to_end_offline,
          test_a_steamed_frame_ends_in_a_refusal_through_the_whole_graph,
          test_a_dead_model_writes_nothing):
    f()
print("\nall hot-graph tests passed")
