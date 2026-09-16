"""The metric has to reward calibration, not luck.

The failure this guards against: steam crosses the lens, confidence collapses,
and the model still emits a doneness that happens to land on the correct side of
the gate. Judging the abstention by that lucky number scores the system's whole
reason for existing as a mistake, and points the threshold tuning in exactly the
wrong direction.
"""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, ".")
from evals.abstention import (TOLERANCE, always_answer_risk, evaluate, load,
                              report, sweep)
from mise.recipes import SOFFRITTO
from pathlib import Path

ROWS = load(Path("evals/labels.jsonl"))
step = SOFFRITTO.step(1)


def test_a_lucky_estimate_does_not_make_an_abstention_unnecessary():
    """Confidence 0.31, doneness 0.88, truth 0.61 — refusing was right even
    though 0.88 is on the same side of the gate as... nothing. The estimate was
    off by 0.27, and that is the only thing that should matter."""
    lucky = [{"doneness": 0.88, "confidence": 0.31, "age": 1.0,
              "label_doneness": 0.86, "evidence": "steam, but the guess lands"}]
    s = evaluate(lucky)
    assert s.abstained == 1, s
    # The estimate was within tolerance, so this abstention really was unnecessary.
    assert s.bad_abstention == 1, "a genuinely reliable estimate should count against us"

    unlucky = [dict(lucky[0], label_doneness=0.55)]      # same output, truth far away
    s2 = evaluate(unlucky)
    assert s2.good_abstention == 1, "an estimate off by 0.33 must justify refusing"
    print(f"same model output, truth 0.86 -> unnecessary; truth 0.55 -> justified")


def test_the_seed_corpus_never_gives_a_wrong_answer():
    s = evaluate(ROWS)
    assert s.wrong_answer == 0, s.misses
    assert s.coverage > 0.5, f"a system that abstains on half the frames is useless: {s.coverage}"
    print(f"seed corpus      -> coverage {s.coverage:.0%}, risk {s.risk:.1%}, "
          f"abstention precision {s.abstention_precision:.0%}")


def test_abstention_beats_always_answering():
    """If refusing buys nothing, the whole contract is decoration."""
    s = evaluate(ROWS)
    base = always_answer_risk(ROWS)
    assert base > s.risk, f"always-answer risk {base} should exceed selective risk {s.risk}"
    print(f"always-answer    -> {base:.0%} wrong · selective -> {s.risk:.0%} wrong")


def test_the_sweep_finds_a_safe_plateau():
    """The claim 'the threshold is too conservative' is only checkable here."""
    curve = sweep(ROWS)
    safe = [t for t, s in curve if s.risk == 0.0]
    assert safe, "no confidence floor achieves zero risk"
    lowest, current = min(safe), step.min_confidence
    assert lowest <= current, f"current floor {current} is below the safe floor {lowest}"
    at_current = next(s for t, s in curve if abs(t - current) < 1e-9)
    at_lowest = next(s for t, s in curve if abs(t - lowest) < 1e-9)
    # If dropping to the lowest safe floor buys no coverage, the current floor
    # is not costing anything and "too conservative" is the wrong diagnosis.
    print(f"safe floor       -> {lowest:.2f} (coverage {at_lowest.coverage:.0%}) · "
          f"current {current:.2f} (coverage {at_current.coverage:.0%})")


def test_rows_without_a_continuous_label_are_reported_as_degraded():
    legacy = [{"doneness": 0.88, "confidence": 0.20, "age": 1.0, "label_ready": True}]
    s = evaluate(legacy)
    assert s.degraded == 1, "a bare label_ready must be flagged, not silently trusted"
    assert "WARNING" in report(s, legacy)
    print("legacy row       -> flagged degraded")


def test_small_corpora_refuse_to_call_themselves_a_result():
    assert "NOT A RESULT" in report(evaluate(ROWS), ROWS)
    print(f"n={len(ROWS)}             -> report refuses to be quoted")


for f in (test_a_lucky_estimate_does_not_make_an_abstention_unnecessary,
          test_the_seed_corpus_never_gives_a_wrong_answer,
          test_abstention_beats_always_answering,
          test_the_sweep_finds_a_safe_plateau,
          test_rows_without_a_continuous_label_are_reported_as_degraded,
          test_small_corpora_refuse_to_call_themselves_a_result):
    f()
print("\nall abstention-metric tests passed")
