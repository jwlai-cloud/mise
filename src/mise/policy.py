"""The refusal contract.

The policy source of truth is policies/mise.dogwood - real Dogwood, which
AgentCore Policy evaluates server-side against the agent's own action history
within a session.

This module provides the same four decisions locally, so the contract holds
with or without AWS reachable, and so the rules are unit-testable. When
AgentCore Policy is configured the remote decision wins; the local evaluator is
the fallback, not a second opinion.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

GATE_OBSERVATION_TTL = 20.0     # rule 1
REFUSAL_COOLDOWN = 120.0        # rule 2
CORRECTION_GIVE_UP = 3          # rule 4
CORRECTION_WINDOW = 3600.0


@dataclass
class PolicyDecision:
    allowed: bool
    rule: str
    explanation: str


class SessionLedger:
    """What this agent has already done. Dogwood's `since within` operates on
    exactly this shape; we keep a local mirror so the rules are testable."""

    def __init__(self) -> None:
        self.gate_passed_at: float | None = None
        # The step the session is on. Set by the tools; read by rule 4, which
        # has to know which step's corrections it is counting.
        self.step: int = 0
        # Keyed by (step, verdict), not by step alone. A repeated "not yet" must
        # not consume the budget that a genuine "I can't tell" needs - they are
        # different statements and collapsing them is how rule 2 ends up
        # speaking a guess. See CLAUDE.md invariant 2.
        self.refusals: dict[tuple[int, str], list[float]] = defaultdict(list)
        self.corrections: dict[int, list[float]] = defaultdict(list)

    def note_gate_passed(self) -> None:
        self.gate_passed_at = time.time()

    def note_refusal(self, step: int, kind: str = "wait") -> None:
        self.refusals[(step, kind)].append(time.time())

    def note_correction(self, step: int) -> None:
        self.corrections[step].append(time.time())

    @staticmethod
    def _within(stamps: list[float], window: float) -> int:
        cutoff = time.time() - window
        return sum(1 for t in stamps if t >= cutoff)

    # --- the four rules ---

    def may_advance(self) -> PolicyDecision:
        # Rule 4 first: three corrections on this step means the threshold is
        # wrong, not the cook, so stop blocking. Checked here rather than in
        # advance_step because all three enforcement layers read the ledger -
        # Strands steering cancels the call before the tool body ever runs, so
        # an override inside advance_step would be dead code. Invariant 5.
        if self.should_stop_gating(self.step).allowed:
            return PolicyDecision(
                True, "give_up_gracefully",
                "corrected three times on this step - it's your call now",
            )
        if self.gate_passed_at is None:
            return PolicyDecision(False, "advance_requires_gate", "no gate has passed this session")
        age = time.time() - self.gate_passed_at
        if age > GATE_OBSERVATION_TTL:
            return PolicyDecision(
                False, "advance_requires_gate",
                f"the last passing observation was {int(age)}s ago, older than the {int(GATE_OBSERVATION_TTL)}s window",
            )
        return PolicyDecision(True, "advance_requires_gate", f"gate passed {int(age)}s ago")

    def may_speak_refusal(self, step: int, kind: str = "wait") -> PolicyDecision:
        n = self._within(self.refusals[(step, kind)], REFUSAL_COOLDOWN)
        if n >= 1:
            return PolicyDecision(
                False, "refusal_cooldown",
                f"already said '{kind}' for this step within the last two minutes; "
                "the panel keeps showing it",
            )
        return PolicyDecision(
            True, "refusal_cooldown", f"first '{kind}' for this step in the window"
        )

    @staticmethod
    def may_speak_abort() -> PolicyDecision:
        return PolicyDecision(True, "danger_never_rate_limited", "danger overrides every other rule")

    def should_stop_gating(self, step: int) -> PolicyDecision:
        n = self._within(self.corrections[step], CORRECTION_WINDOW)
        if n >= CORRECTION_GIVE_UP:
            return PolicyDecision(
                True, "give_up_gracefully",
                f"corrected {n} times on this step - the threshold is wrong, not the cook",
            )
        return PolicyDecision(False, "give_up_gracefully", f"{n} correction(s) so far")


LEDGER = SessionLedger()


def remote_policy_available() -> bool:
    """True when AgentCore Policy is configured. Kept separate so the demo can
    show the same decision arriving from either evaluator."""
    return bool(os.getenv("MISE_POLICY_ARN"))
