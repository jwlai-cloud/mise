"""Abstention evaluation - the part that is research-grade, not demo-grade.

Accuracy alone is the wrong metric. A system that always answers scores well on
accuracy and is dangerous in a kitchen; a system that always abstains is safe
and useless. What matters is whether it declines EXACTLY when its perception is
unreliable. That is selective prediction, and the right headline is a
risk-coverage pair, not an accuracy.

WHAT AN ABSTENTION IS JUDGED AGAINST
------------------------------------
An earlier version of this harness asked: "if it had answered, would it have
landed on the right side of the gate?" That question is answerable - the labels
are independent - but it is the wrong question, because it scores a LUCKY
estimate as a reason the refusal was unnecessary.

Concretely: steam crosses the lens, confidence collapses to 0.31, and the model
still emits doneness=0.88. That number is noise. If the pan happens to be ready,
the old metric recorded the refusal as a mistake - penalising the system for
exactly the behaviour the project exists to demonstrate.

So an abstention is justified here when the ESTIMATE WAS ACTUALLY UNRELIABLE:

    |doneness - label_doneness| > TOLERANCE

which requires a continuous ground-truth label, not just a ready/not-ready bit.
That is why rows carry `label_doneness`. Rows with only the older `label_ready`
still run, but fall back to the side-of-gate test and are reported as degraded.

CORPUS
------
  {"doneness":0.62,"confidence":0.88,"age":0.9,"label_doneness":0.58,
   "evidence":"softening","source":"seed"}

  doneness/confidence  what the model said
  age                  seconds since the frame was taken (drives staleness)
  label_doneness       what a human says the pan actually was  <- ground truth
  label_ready          legacy bit; derived from label_doneness when absent
  source               "seed" rows are hand-written to exercise this harness.
                       They are a smoke test. They are NOT evidence, and the
                       report refuses to call them a result.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mise.gate import decide          # noqa: E402
from mise.recipes import SOFFRITTO    # noqa: E402
from mise.state import CookState      # noqa: E402

# How far a point estimate may be from the truth and still count as reliable.
# The SPIKE.md pass criterion is the same number, deliberately: the eval and the
# go/no-go decision must not drift apart.
TOLERANCE = 0.15

# Below this many labelled frames, report percentages as indicative only.
CREDIBLE_N = 100


@dataclass
class Scores:
    correct_answer: int = 0
    wrong_answer: int = 0
    good_abstention: int = 0
    bad_abstention: int = 0
    degraded: int = 0          # rows judged without a continuous label
    n: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def answered(self) -> int:
        return self.correct_answer + self.wrong_answer

    @property
    def abstained(self) -> int:
        return self.good_abstention + self.bad_abstention

    @property
    def coverage(self) -> float:
        """Fraction of frames it was willing to judge."""
        return self.answered / self.n if self.n else 0.0

    @property
    def risk(self) -> float:
        """Of the frames it judged, how often was it wrong. Lower is better."""
        return self.wrong_answer / self.answered if self.answered else 0.0

    @property
    def abstention_precision(self) -> float:
        """When it declined, how often was the estimate genuinely unreliable."""
        return self.good_abstention / self.abstained if self.abstained else 0.0


def _truth_ready(row: dict, gate: float) -> bool:
    if "label_doneness" in row:
        return float(row["label_doneness"]) >= gate
    return bool(row["label_ready"])


def _estimate_unreliable(row: dict, gate: float) -> tuple[bool, bool]:
    """(unreliable, degraded). Degraded means we had to guess from a bare bit."""
    if "label_doneness" in row:
        return abs(float(row["doneness"]) - float(row["label_doneness"])) > TOLERANCE, False
    # No continuous label: fall back to the side-of-gate test, and say so.
    return (float(row["doneness"]) >= gate) != bool(row["label_ready"]), True


def evaluate(rows: list[dict], step_index: int = 1,
             min_confidence: float | None = None) -> Scores:
    step = SOFFRITTO.step(step_index)
    if min_confidence is not None:
        from dataclasses import replace
        step = replace(step, min_confidence=min_confidence)

    s = Scores(n=len(rows))
    for row in rows:
        state = CookState(
            doneness=float(row["doneness"]),
            confidence=float(row["confidence"]),
            evidence=row.get("evidence", ""),
            risk=row.get("risk", "none"),
        )
        state.updated_at -= float(row.get("age", 0.0))

        d = decide(state, step)
        truth_ready = _truth_ready(row, step.gate_doneness)
        unreliable, degraded = _estimate_unreliable(row, step.gate_doneness)
        s.degraded += degraded

        if d.verdict == "refuse":
            if unreliable:
                s.good_abstention += 1
            else:
                s.bad_abstention += 1
        else:
            if (d.verdict == "proceed") == truth_ready:
                s.correct_answer += 1
            else:
                s.wrong_answer += 1
                s.misses.append(
                    f"said {d.verdict!r} at doneness {row['doneness']} "
                    f"(truth {row.get('label_doneness', truth_ready)}) - {row.get('evidence','')}"
                )
    return s


def always_answer_risk(rows: list[dict], step_index: int = 1) -> float:
    """What a system that never refuses would get wrong. The comparison that
    shows whether abstention is buying anything at all."""
    step = SOFFRITTO.step(step_index)
    wrong = sum(
        1 for r in rows
        if (float(r["doneness"]) >= step.gate_doneness) != _truth_ready(r, step.gate_doneness)
    )
    return wrong / len(rows) if rows else 0.0


def sweep(rows: list[dict], step_index: int = 1) -> list[tuple[float, Scores]]:
    """Risk-coverage curve over the confidence floor.

    The threshold is the one tunable in the whole contract, and 'too
    conservative' is a claim you can only make against this table.
    """
    out = []
    for i in range(0, 20):
        t = round(i * 0.05, 2)
        out.append((t, evaluate(rows, step_index, min_confidence=t)))
    return out


def report(s: Scores, rows: list[dict], step_index: int = 1) -> str:
    step = SOFFRITTO.step(step_index)
    base = always_answer_risk(rows, step_index)
    seeds = sum(1 for r in rows if r.get("source") == "seed")

    lines = [
        f"frames               {s.n}",
        f"answered             {s.answered}  (coverage {s.coverage:.0%})",
        f"  correct            {s.correct_answer}",
        f"  WRONG              {s.wrong_answer}   <- selective risk {s.risk:.1%}",
        f"abstained            {s.abstained}",
        f"  justified          {s.good_abstention}   (estimate was off by >{TOLERANCE})",
        f"  unnecessary        {s.bad_abstention}",
        f"abstention precision {s.abstention_precision:.0%}",
        "",
        f"a system that never refused would be wrong {base:.0%} of the time",
        f"this one is wrong {s.risk:.1%} of the time, on {s.coverage:.0%} of frames",
    ]
    if s.misses:
        lines += ["", "misses:"] + [f"  - {m}" for m in s.misses]
    if s.degraded:
        lines += ["", f"WARNING: {s.degraded} row(s) had no label_doneness; abstention for "
                      "those was judged by side-of-gate, which rewards a lucky estimate."]
    if s.n < CREDIBLE_N:
        lines += [
            "",
            f"NOT A RESULT: {s.n} frames"
            + (f", {seeds} of them hand-written seeds" if seeds else "")
            + f". Percentages over fewer than {CREDIBLE_N} frames are a smoke test",
            "for this harness, not evidence about the system. Do not quote them.",
        ]
    return "\n".join(lines) + "\n"


def sweep_report(rows: list[dict], step_index: int = 1) -> str:
    step = SOFFRITTO.step(step_index)
    lines = [
        "confidence floor -> risk / coverage   (current floor "
        f"{step.min_confidence:.2f})",
        "  floor   coverage   risk   abstained  justified",
    ]
    for t, s in sweep(rows, step_index):
        mark = "  <- current" if abs(t - step.min_confidence) < 0.001 else ""
        lines.append(
            f"  {t:.2f}    {s.coverage:>6.0%}   {s.risk:>5.1%}   "
            f"{s.abstained:>8}   {s.good_abstention:>8}{mark}"
        )
    lines += [
        "",
        "Pick the floor from this table, not by feel: the lowest floor whose risk",
        "is still 0% is the most useful system that never gave a wrong answer.",
    ]
    return "\n".join(lines) + "\n"


def load(path: Path) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for i, r in enumerate(rows, 1):
        if "label_doneness" not in r and "label_ready" not in r:
            raise ValueError(f"{path}:{i} needs label_doneness (preferred) or label_ready")
    return rows


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "labels.jsonl"
    rows = load(path)
    print(report(evaluate(rows), rows))
    print(sweep_report(rows))
