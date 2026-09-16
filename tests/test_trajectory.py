"""The agent eval, checked offline.

A unit test proves the graph CAN behave. These rules prove, from a trace, that
it DID — which is the only thing that survives contact with a real model. They
run here on synthetic spans so the assertions are exercised before the Lambda
that will host them exists.
"""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, ".")
from evals.trajectory import (Trajectory, evaluator_definitions, from_spans,
                              judge, lambda_handler)


def failures(t):
    return {f.rule for f in judge(t) if not f.passed}


def test_a_clean_frame_that_skips_the_critic_passes():
    t = Trajectory(nodes=["perceive", "risk", "arbitrate"],
                   doneness=0.45, confidence_in=0.92, confidence_out=0.92)
    assert not failures(t), failures(t)
    print("clean frame       -> critic skipped, all rules pass")


def test_skipping_the_critic_near_the_gate_is_caught():
    """The expensive mistake: 0.78 against a 0.8 gate with no second opinion."""
    t = Trajectory(nodes=["perceive", "risk", "arbitrate"],
                   doneness=0.78, confidence_in=0.92, confidence_out=0.92)
    assert "critic_runs_near_the_gate" in failures(t), failures(t)
    print("skipped near gate -> caught")


def test_running_the_critic_on_every_frame_is_caught():
    """A critic that always runs is a cost bug the conditional edge exists to
    prevent, and nothing else in the system would notice."""
    t = Trajectory(nodes=["perceive", "critique", "risk", "arbitrate"],
                   doneness=0.30, confidence_in=0.95, confidence_out=0.95)
    assert "critic_skipped_when_clear" in failures(t), failures(t)
    print("critic overran    -> caught")


def test_a_missing_risk_node_is_caught():
    t = Trajectory(nodes=["perceive", "arbitrate"], doneness=0.5, confidence_in=0.9,
                   confidence_out=0.9)
    assert "risk_always_runs" in failures(t), failures(t)
    print("risk node absent  -> caught")


def test_confidence_rising_is_caught():
    """The clamp and the critic may only lower. Anything else inverted them."""
    t = Trajectory(nodes=["perceive", "risk", "arbitrate"],
                   doneness=0.4, confidence_in=0.3, confidence_out=0.9)
    assert "confidence_only_falls" in failures(t), failures(t)
    print("confidence rose   -> caught")


def test_a_dropped_urgent_frame_is_caught():
    """Invariant 3 from the trace side: danger must reach the cache however
    little the graph trusted itself."""
    t = Trajectory(nodes=["perceive", "risk", "arbitrate"], doneness=0.4,
                   confidence_in=0.2, confidence_out=0.2, risk="urgent", wrote=False)
    assert "danger_never_suppressed" in failures(t), failures(t)
    # And the same frame with risk="none" is legitimately dropped.
    ok = Trajectory(nodes=["perceive", "risk"], doneness=0.4, confidence_in=0.2,
                    confidence_out=0.2, risk="none", wrote=False)
    assert "danger_never_suppressed" not in failures(ok)
    print("urgent dropped    -> caught; a safe drop is not flagged")


def test_spans_parse_into_a_trajectory():
    spans = [
        {"name": "graph.node.perceive", "attributes": {"gen_ai.doneness": 0.88,
                                                       "gen_ai.confidence": 0.93}},
        {"name": "graph.node.critique", "attributes": {}},
        {"name": "graph.node.risk", "attributes": {"gen_ai.risk": "none"}},
        {"name": "graph.node.arbitrate", "attributes": {"gen_ai.confidence": 0.2,
                                                        "gen_ai.wrote": True}},
    ]
    t = from_spans(spans)
    assert t.nodes == ["perceive", "critique", "risk", "arbitrate"], t.nodes
    assert t.doneness == 0.88 and t.confidence_in == 0.93 and t.confidence_out == 0.2
    assert not failures(t), failures(t)
    print(f"span parse        -> {t.nodes}, {t.confidence_in} -> {t.confidence_out}")


def test_an_unrecognised_span_shape_does_not_crash():
    """This runs in a Lambda. A span it cannot read must leave a field
    unobservable, never raise."""
    t = from_spans([{"name": "???", "attributes": {"gen_ai.doneness": "not-a-number"}},
                    {}, {"name": "graph.node.perceive"}])
    assert t.doneness is None and t.nodes == ["perceive"]
    print("odd spans         -> parsed without raising")


def test_the_lambda_wrapper_returns_agentcore_shaped_scores():
    out = lambda_handler({"evaluationInput": {"sessionSpans": [
        {"name": "graph.node.perceive", "attributes": {"gen_ai.doneness": 0.45,
                                                       "gen_ai.confidence": 0.92}},
        {"name": "graph.node.risk"}, {"name": "graph.node.arbitrate",
                                      "attributes": {"gen_ai.confidence": 0.92}},
    ]}})
    assert out["passed"] is True and out["failures"] == []
    assert all({"name", "value", "reason"} <= set(s) for s in out["scores"])
    print(f"lambda handler    -> {len(out['scores'])} scores, passed={out['passed']}")


def test_evaluator_definitions_match_the_real_api():
    defs = evaluator_definitions()
    levels = {"TOOL_CALL", "TRACE", "SESSION"}
    for d in defs:
        assert d["level"] in levels, d["level"]
        cfg = d["evaluatorConfig"]
        assert set(cfg) <= {"llmAsAJudge", "codeBased", "derived"}, set(cfg)
        if "codeBased" in cfg:
            assert set(cfg["codeBased"]["lambdaConfig"]) <= {"lambdaArn",
                                                             "lambdaTimeoutInSeconds"}
        if "llmAsAJudge" in cfg:
            assert "instructions" in cfg["llmAsAJudge"]
    print(f"definitions       -> {len(defs)} evaluators, shapes match CreateEvaluator")


for f in (test_a_clean_frame_that_skips_the_critic_passes,
          test_skipping_the_critic_near_the_gate_is_caught,
          test_running_the_critic_on_every_frame_is_caught,
          test_a_missing_risk_node_is_caught,
          test_confidence_rising_is_caught,
          test_a_dropped_urgent_frame_is_caught,
          test_spans_parse_into_a_trajectory,
          test_an_unrecognised_span_shape_does_not_crash,
          test_the_lambda_wrapper_returns_agentcore_shaped_scores,
          test_evaluator_definitions_match_the_real_api):
    f()
print("\nall trajectory tests passed")
