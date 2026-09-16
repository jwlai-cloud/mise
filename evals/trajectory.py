"""Did the graph take a sane path? The agent eval, as opposed to the pan eval.

TWO EVALS, TWO OBJECTS. They are not alternatives.

  evals/abstention.py   the PERCEPTION layer. One labelled corpus, offline.
                        "Does this model read this pan to +/-0.15, and does it
                        decline when it cannot see?" No AWS required.

  this file             the AGENT layer. Real traces from a real run.
                        "Did perceive -> critique -> risk -> arbitrate fire in
                        the right shape, and did the critic run only where a
                        mistake was expensive?" Scores a trajectory, not a pan.

AgentCore Evaluations is built for the second and cannot do the first:
StartBatchEvaluation's dataSourceConfig accepts CloudWatch log groups or an
online-eval config, never a JSONL corpus, and Evaluate takes OTEL sessionSpans.
Its `level` enum is TOOL_CALL | TRACE | SESSION. It is a trace product.

WHY THE CHECKS LIVE HERE AND NOT IN A LAMBDA
--------------------------------------------
AgentCore's codeBased evaluator takes a `lambdaArn`, not inline code. So the
assertions have to exist somewhere anyway - and if they exist only inside a
deployed Lambda they cannot be unit-tested, cannot run before the account is
unblocked, and will drift from the invariants they are supposed to protect.

So: the assertions are plain functions here, `lambda_handler` wraps them for
AgentCore, and tests/test_trajectory.py runs them on synthetic spans with no
credentials. Same shape as perception.py - the logic is testable, the AWS
surface is a thin wrapper.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

# The graph's contract, as trajectory properties. Each is an invariant from
# CLAUDE.md expressed as something you can check in a trace rather than assert
# in a unit test - because a unit test proves the code can behave, and a trace
# proves it did.
CRITIC_CONFIDENCE_TRIGGER = 0.75
CRITIC_GATE_MARGIN = 0.10


@dataclass
class Finding:
    rule: str
    passed: bool
    detail: str

    def as_score(self) -> dict[str, Any]:
        return {"name": self.rule, "value": 1.0 if self.passed else 0.0,
                "reason": self.detail}


@dataclass
class Trajectory:
    """One frame's pass through the graph, read back off its spans."""

    nodes: list[str] = field(default_factory=list)
    doneness: float | None = None
    confidence_in: float | None = None     # what perception claimed
    confidence_out: float | None = None    # what the arbiter wrote
    risk: str = "none"
    gate: float = 0.8
    wrote: bool = True

    @property
    def near_gate(self) -> bool:
        if self.doneness is None or self.confidence_in is None:
            return True                     # cannot tell; do not penalise
        return (self.confidence_in < CRITIC_CONFIDENCE_TRIGGER
                or abs(self.doneness - self.gate) < CRITIC_GATE_MARGIN)


# ---------- the assertions ----------

def critic_ran_only_where_it_mattered(t: Trajectory) -> Finding:
    """The conditional edge is the reason the critic is affordable at 0.3 Hz.
    A critic that runs on every frame is a cost bug; one that never runs is a
    contract bug."""
    ran = "critique" in t.nodes
    if t.near_gate:
        return Finding("critic_runs_near_the_gate", ran,
                       "ran near the gate" if ran else
                       f"SKIPPED at doneness {t.doneness} / confidence {t.confidence_in} "
                       "- this is where a mistake is expensive")
    return Finding("critic_skipped_when_clear", not ran,
                   "skipped on a clear mid-step frame" if not ran else
                   f"ran unnecessarily at doneness {t.doneness}, confidence "
                   f"{t.confidence_in} - paying for a second opinion nobody needed")


def risk_ran_every_frame(t: Trajectory) -> Finding:
    """Invariant 3. Danger is judged in parallel, never downstream of a
    confidence the perception agent chose."""
    ran = "risk" in t.nodes
    return Finding("risk_always_runs", ran,
                   "risk node present" if ran else
                   "RISK NODE ABSENT - danger was not judged for this frame")


def confidence_never_rose(t: Trajectory) -> Finding:
    """The ceiling table and the critic may only lower. A trace where the
    arbiter's confidence exceeds perception's means something inverted the
    clamp."""
    if t.confidence_in is None or t.confidence_out is None:
        return Finding("confidence_only_falls", True, "not observable in this trace")
    ok = t.confidence_out <= t.confidence_in + 1e-9
    return Finding("confidence_only_falls", ok,
                   f"{t.confidence_in} -> {t.confidence_out}" if ok else
                   f"CONFIDENCE ROSE {t.confidence_in} -> {t.confidence_out}")


def danger_was_not_gated(t: Trajectory) -> Finding:
    """Invariant 3 again, from the other side: an urgent frame must still have
    been written, however little the graph trusted itself."""
    if t.risk != "urgent":
        return Finding("danger_never_suppressed", True, "no danger in this frame")
    return Finding("danger_never_suppressed", t.wrote,
                   "urgent frame written" if t.wrote else
                   "URGENT FRAME DROPPED - danger was suppressed")


def arbiter_is_the_only_writer(t: Trajectory) -> Finding:
    """One author for the cache. A trace that wrote without arbitrating means
    a node reached STORE directly."""
    if not t.wrote:
        return Finding("arbiter_is_sole_writer", True, "nothing written")
    ok = "arbitrate" in t.nodes or "perceive" in t.nodes
    return Finding("arbiter_is_sole_writer", ok,
                   "write followed the graph" if ok else
                   "WROTE WITHOUT RUNNING THE GRAPH")


RULES = (critic_ran_only_where_it_mattered, risk_ran_every_frame,
         confidence_never_rose, danger_was_not_gated, arbiter_is_the_only_writer)


def judge(t: Trajectory) -> list[Finding]:
    return [rule(t) for rule in RULES]


# ---------- reading a trajectory out of OTEL spans ----------

def from_spans(spans: Iterable[dict]) -> Trajectory:
    """Build a Trajectory from the spans Strands emits for one graph run.

    Defensive by design: a span shape we do not recognise must not crash an
    evaluator running in a Lambda, it must just leave that field unobservable
    and let the rules say so.
    """
    t = Trajectory(nodes=[], wrote=False)
    for s in spans:
        name = (s.get("name") or "").lower()
        attrs = s.get("attributes") or {}
        # Strands names a node span "invoke_agent <name>"; the structured-output
        # tool call shows up separately as "execute_tool <Model>". Either is
        # evidence the node ran, and the tool span is the more reliable of the
        # two because it only exists if the agent actually produced output.
        for node, tool in (("perceive", "panreading"), ("critique", "criticverdict"),
                           ("risk", "riskreport"), ("arbitrate", "mise.frame")):
            if (node in name or tool in name) and node not in t.nodes:
                t.nodes.append(node)
        for key, val in attrs.items():
            k = key.split(".")[-1]
            # mise.* attributes come from the frame span the graph emits; the
            # bare names are accepted too so a hand-written trace still parses.
            if k == "doneness" and t.doneness is None:
                t.doneness = _f(val)
            elif k == "confidence_in" and t.confidence_in is None:
                t.confidence_in = _f(val)
            elif k == "confidence_out":
                t.confidence_out = _f(val)
            elif k == "confidence":
                if "perceive" in name and t.confidence_in is None:
                    t.confidence_in = _f(val)
                elif t.confidence_out is None or "arbitrate" in name:
                    t.confidence_out = _f(val)
            elif k == "risk" and isinstance(val, str):
                t.risk = val
            elif k in ("gate", "gate_doneness"):
                t.gate = _f(val) or t.gate
            elif k == "wrote":
                t.wrote = bool(val)
    return t


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------- the AgentCore surface ----------

def lambda_handler(event: dict, _context: Any = None) -> dict:
    """AgentCore codeBased evaluator entry point.

    `codeBased` takes a lambdaArn, so this is the wrapper AgentCore invokes. It
    does no judging of its own - every assertion above is a plain function that
    tests/test_trajectory.py already exercises offline.
    """
    spans = (event.get("evaluationInput") or {}).get("sessionSpans") or event.get("spans") or []
    findings = judge(from_spans(spans))
    return {
        "scores": [f.as_score() for f in findings],
        "passed": all(f.passed for f in findings),
        # Surfaced so a failing evaluation names the rule rather than a number.
        "failures": [f.rule for f in findings if not f.passed],
    }


def evaluator_definitions() -> list[dict]:
    """Declarative config for CreateEvaluator, so the evaluators can be reviewed
    now and created the moment the account is unblocked.

    The deterministic rules are codeBased (this module, as a Lambda). The one
    genuinely judgement-shaped question gets llmAsAJudge, because "was the
    evidence sentence actually checkable by a human looking at the pan" is not
    something an assertion can answer.
    """
    return [
        {
            "evaluatorName": "mise-graph-contract",
            "description": "Trajectory invariants for the hot graph: the critic's "
                           "conditional edge, danger never gated, confidence only falls.",
            "level": "TRACE",
            "evaluatorConfig": {
                "codeBased": {
                    "lambdaConfig": {
                        "lambdaArn": "${MISE_TRAJECTORY_LAMBDA_ARN}",
                        "lambdaTimeoutInSeconds": 30,
                    }
                }
            },
        },
        {
            "evaluatorName": "mise-evidence-is-checkable",
            "description": "Is the spoken evidence a thing a human could verify by "
                           "glancing at the pan?",
            "level": "TOOL_CALL",
            "evaluatorConfig": {
                "llmAsAJudge": {
                    "instructions": (
                        "You are given the `evidence` sentence a cooking assistant "
                        "spoke about a pan, and the verdict it gave.\n\n"
                        "Score 1 if a cook standing at the hob could confirm or refute "
                        "that sentence by looking at the pan for two seconds — "
                        "'edges still firm', 'steam across the lens'.\n"
                        "Score 0 if it restates the verdict without evidence ('it is "
                        "not ready'), is unfalsifiable ('needs more time'), or claims "
                        "something invisible ('the sugars are caramelising').\n\n"
                        "Evidence is read aloud and shown on screen; an unverifiable "
                        "sentence is how the assistant loses trust."
                    ),
                    "ratingScale": {
                        "numerical": [
                            {"name": "checkable", "value": 1.0},
                            {"name": "not_checkable", "value": 0.0},
                        ]
                    },
                }
            },
        },
    ]


if __name__ == "__main__":
    import sys
    spans = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else []
    out = lambda_handler({"spans": spans})
    for s in out["scores"]:
        print(f"  [{'ok  ' if s['value'] else 'FAIL'}] {s['name']:<32} {s['reason']}")
    print(f"\n{'PASS' if out['passed'] else 'FAILED: ' + ', '.join(out['failures'])}")
