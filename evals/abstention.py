"""Abstention evaluation - the part that is research-grade, not demo-grade.

Accuracy alone is the wrong metric. A system that always answers scores well on
accuracy and is dangerous in a kitchen; a system that always abstains is safe
and useless. What matters is whether it declines EXACTLY when its perception is
unreliable.

Four outcomes per labelled frame:
  correct_answer   - answered, and got it right
  wrong_answer     - answered, and got it wrong        <- the costly one
  good_abstention  - declined, and would have been wrong
  bad_abstention   - declined, but would have been right

Headline metric: risk coverage. Of the frames it chose to answer, how often was
it right? A useful system keeps coverage high AND risk low.

Feed it frames from evals/labels.jsonl:
  {"doneness": 0.62, "confidence": 0.91, "age": 1.2, "label_ready": false}
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mise.gate import decide          # noqa: E402
from mise.recipes import SOFFRITTO    # noqa: E402
from mise.state import CookState      # noqa: E402


@dataclass
class Scores:
    correct_answer: int = 0
    wrong_answer: int = 0
    good_abstention: int = 0
    bad_abstention: int = 0

    @property
    def answered(self) -> int:
        return self.correct_answer + self.wrong_answer

    @property
    def total(self) -> int:
        return self.answered + self.good_abstention + self.bad_abstention

    @property
    def coverage(self) -> float:
        """Fraction of frames it was willing to judge."""
        return self.answered / self.total if self.total else 0.0

    @property
    def risk(self) -> float:
        """Of the frames it judged, how often was it wrong. Lower is better."""
        return self.wrong_answer / self.answered if self.answered else 0.0

    @property
    def abstention_precision(self) -> float:
        """When it declined, how often was declining the right call."""
        abst = self.good_abstention + self.bad_abstention
        return self.good_abstention / abst if abst else 0.0


def evaluate(rows: list[dict], step_index: int = 1) -> Scores:
    step = SOFFRITTO.step(step_index)
    s = Scores()
    for r in rows:
        state = CookState(
            doneness=float(r["doneness"]),
            confidence=float(r["confidence"]),
            evidence=r.get("evidence", ""),
            risk=r.get("risk", "none"),
        )
        state.updated_at -= float(r.get("age", 0.0))
        d = decide(state, step)
        truth = bool(r["label_ready"])

        if d.verdict in ("refuse",):
            predicted = state.doneness >= step.gate_doneness
            if predicted == truth:
                s.bad_abstention += 1
            else:
                s.good_abstention += 1
        else:
            said_ready = d.verdict in ("proceed",)
            if said_ready == truth:
                s.correct_answer += 1
            else:
                s.wrong_answer += 1
    return s


def report(s: Scores) -> str:
    return (
        f"frames              {s.total}\n"
        f"answered            {s.answered}  (coverage {s.coverage:.0%})\n"
        f"  correct           {s.correct_answer}\n"
        f"  WRONG             {s.wrong_answer}   <- risk {s.risk:.1%}\n"
        f"abstained           {s.good_abstention + s.bad_abstention}\n"
        f"  justified         {s.good_abstention}\n"
        f"  unnecessary       {s.bad_abstention}\n"
        f"abstention precision {s.abstention_precision:.0%}\n"
    )


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "labels.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    print(report(evaluate(rows)))
