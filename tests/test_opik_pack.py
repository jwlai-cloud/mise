"""The Opik wrapper must agree with the harness it wraps, exactly.

The failure this guards against is drift: someone edits TOLERANCE, or the gate,
or the meaning of an abstention in evals/abstention.py, and the numbers Opik
shows a judge keep saying the old thing. So this reproduces the corpus scorer's
output from a stub Opik and asserts it equals abstention.evaluate() to the digit.

Runs with no opik installed and no credentials - the stub is 6 lines.
"""
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, "src")
sys.path.insert(0, ".")


# --- the stub. Same fields as opik.evaluation.metrics.score_result.ScoreResult.
@dataclass
class ScoreResult:
    name: str
    value: float
    reason: Optional[str] = None
    category_name: Optional[str] = None
    metadata: Optional[dict] = None
    scoring_failed: bool = False


_sr = types.ModuleType("opik.evaluation.metrics.score_result")
_sr.ScoreResult = ScoreResult
_metrics = types.ModuleType("opik.evaluation.metrics")
_metrics.score_result = _sr
for _name, _mod in (("opik", types.ModuleType("opik")),
                    ("opik.evaluation", types.ModuleType("opik.evaluation")),
                    ("opik.evaluation.metrics", _metrics),
                    ("opik.evaluation.metrics.score_result", _sr)):
    sys.modules.setdefault(_name, _mod)

from evals.abstention import always_answer_risk, evaluate, load  # noqa: E402
from evals.opik_pack import (FROM_MODEL, build_corpus_scorer, build_task,  # noqa: E402
                             bucket, merge, PROFILES)

ROWS = load(Path("evals/labels.jsonl"))


@dataclass
class FakeCase:
    dataset_item_content: dict
    task_output: dict
    trace_id: str = "t"
    dataset_item_id: str = "i"


@dataclass
class FakeResult:
    test_case: FakeCase
    score_results: list = field(default_factory=list)
    trial_id: int = 0


def _results(rows, task):
    return [FakeResult(FakeCase(dict(r), task(r))) for r in rows]


def test_the_corpus_scorer_reproduces_the_harness_exactly():
    scores = {s.name: s.value for s in
              build_corpus_scorer()(_results(ROWS, build_task(PROFILES["recorded"])))}
    s = evaluate(ROWS)
    assert scores["coverage"] == s.coverage, scores
    assert scores["selective_risk"] == s.risk, scores
    assert scores["abstention_precision"] == s.abstention_precision, scores
    assert scores["always_answer_risk"] == always_answer_risk(ROWS), scores
    assert scores["risk_reduction"] == always_answer_risk(ROWS) - s.risk
    print(f"corpus scorer     -> coverage {scores['coverage']:.0%}, "
          f"risk {scores['selective_risk']:.1%}, "
          f"precision {scores['abstention_precision']:.0%}  (== harness)")


def test_a_task_cannot_overwrite_its_own_ground_truth():
    """The whole eval is worthless if the model can move the label."""
    item = {"doneness": 0.2, "confidence": 0.9, "age": 1.0, "label_doneness": 0.18}
    cheated = merge(item, {"doneness": 0.9, "confidence": 0.9,
                           "label_doneness": 0.9, "age": 0.0})
    assert cheated["label_doneness"] == 0.18, cheated
    assert cheated["age"] == 1.0, cheated
    assert cheated["doneness"] == 0.9, "the estimate must still come from the model"
    print("ground truth      -> label_doneness and age survive a hostile task output")


def test_every_row_lands_in_exactly_one_bucket():
    names = [bucket(evaluate([r]))[0] for r in ROWS]
    assert len(names) == len(ROWS)
    assert set(names) <= {"correct", "wrong", "justified_abstention",
                          "unnecessary_abstention"}, set(names)
    s = evaluate(ROWS)
    assert names.count("correct") == s.correct_answer
    assert names.count("wrong") == s.wrong_answer
    assert names.count("justified_abstention") == s.good_abstention
    assert names.count("unnecessary_abstention") == s.bad_abstention
    print(f"per-row buckets   -> {dict((n, names.count(n)) for n in set(names))}")


def test_a_frame_with_no_reading_is_dropped_not_counted_as_a_free_refusal():
    """A perception failure must not inflate abstention precision."""
    scorer = build_corpus_scorer()
    good = _results(ROWS, build_task(PROFILES["recorded"]))
    broken = good + [FakeResult(FakeCase(dict(ROWS[0]), {"perception_error": "boom"}))]
    a = {s.name: s.value for s in scorer(good)}
    b = {s.name: s.value for s in scorer(broken)}
    assert a["abstention_precision"] == b["abstention_precision"], (a, b)
    assert "1 frame(s) produced no reading" in \
        next(s.reason for s in scorer(broken) if s.name == "coverage")
    print("failed perception -> dropped from the ratios and named in the reason")


def test_the_report_still_refuses_to_be_quoted():
    for s in build_corpus_scorer()(_results(ROWS, build_task(PROFILES["recorded"]))):
        if s.name in ("coverage", "selective_risk", "abstention_precision"):
            assert "NOT A RESULT" in (s.reason or ""), s
    print(f"n={len(ROWS)}              -> every headline score carries the caveat")


for f in (test_the_corpus_scorer_reproduces_the_harness_exactly,
          test_a_task_cannot_overwrite_its_own_ground_truth,
          test_every_row_lands_in_exactly_one_bucket,
          test_a_frame_with_no_reading_is_dropped_not_counted_as_a_free_refusal,
          test_the_report_still_refuses_to_be_quoted):
    f()
print("\nall opik-pack tests passed (no opik, no credentials)")
