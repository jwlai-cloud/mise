"""The judgement. Deterministic, testable, and willing to say no.

Three outcomes, and the third one is the product:
  PROCEED  - the gate is met
  WAIT     - the gate is not met, and here is why, and roughly how long
  REFUSE   - we cannot tell (stale frames, low confidence) so we will not guess
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .recipes import Step
from .state import CookState

Verdict = Literal["proceed", "wait", "refuse", "abort"]


@dataclass
class Decision:
    verdict: Verdict
    reason: str
    seconds_remaining: int | None = None
    evidence: str = ""

    def spoken(self) -> str:
        """What Alexa actually says. Short - the voice budget is 30 seconds."""
        if self.verdict == "abort":
            return f"Take it off the heat. {self.reason}"
        if self.verdict == "refuse":
            return f"I can't tell right now. {self.reason}"
        if self.verdict == "wait":
            t = f" About {self.seconds_remaining} seconds." if self.seconds_remaining else ""
            return f"Not yet. {self.reason}{t}"
        return f"Go ahead. {self.reason}"


def decide(state: CookState, step: Step) -> Decision:
    # 1. Danger first. Always interruptible, never gated on confidence.
    if state.risk == "urgent":
        return Decision("abort", state.evidence or "it's catching.", evidence=state.evidence)

    # 2. The refusal path. No fresh frame means no opinion.
    if state.is_stale:
        return Decision(
            "refuse",
            f"I haven't had a clear view of the pan for {int(state.age_seconds)} seconds.",
            evidence=state.evidence,
        )
    if state.confidence < step.min_confidence:
        return Decision(
            "refuse",
            "the view isn't clear enough for me to judge that.",
            evidence=state.evidence,
        )

    # 3. The gate.
    if state.doneness >= step.gate_doneness:
        return Decision("proceed", step.goal, evidence=state.evidence)

    shortfall = step.gate_doneness - state.doneness
    remaining = max(10, int(shortfall * step.typical_seconds))
    return Decision(
        "wait",
        state.evidence or f"not yet {step.goal}.",
        seconds_remaining=remaining,
        evidence=state.evidence,
    )
