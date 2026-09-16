"""Strands steering: the gate enforced at the tool-call boundary.

A prompt asking the model not to advance is a request. A steering handler that
intercepts BeforeToolCallEvent and cancels the call is a guarantee. AWS's own
benchmark puts steering at 100% vs 82.5% for prompt-only across 600 runs - their
six-scenario eval, not an external benchmark, so quote it as theirs.

Two entry points, one decision:
  MiseSteering  - a Strands HookProvider, for when an Agent is driving
  guarded_advance() - the same check as a plain function, testable with no model
"""
from __future__ import annotations

import logging
from typing import Any

from .policy import LEDGER, PolicyDecision

log = logging.getLogger(__name__)

GUARDED_TOOLS = {"advance_step"}


def guarded_advance() -> PolicyDecision:
    """May the recipe advance right now? The single source of truth."""
    return LEDGER.may_advance()


class MiseSteering:
    """Strands HookProvider. Cancels advance_step when the gate has not passed.

    Registered with:  Agent(..., hooks=[MiseSteering()])
    """

    def register_hooks(self, registry: Any, **_: Any) -> None:
        try:
            from strands.hooks import BeforeToolCallEvent
        except ImportError:  # strands not installed - steering simply absent
            log.warning("strands not available; tool-boundary steering disabled")
            return
        registry.add_callback(BeforeToolCallEvent, self._before_tool)

    def _before_tool(self, event: Any) -> None:
        name = getattr(getattr(event, "tool_use", None), "name", None) or getattr(event, "tool_name", "")
        if name not in GUARDED_TOOLS:
            return
        decision = guarded_advance()
        if decision.allowed:
            return
        feedback = (
            f"Blocked by policy rule '{decision.rule}': {decision.explanation}. "
            "Call check_doneness and tell the cook what it returns. Do not advance."
        )
        log.info("steering blocked %s: %s", name, decision.explanation)
        # Strands exposes cancellation differently across versions; try each.
        for attr, value in (("cancel", feedback), ("cancelled", True), ("abort_reason", feedback)):
            if hasattr(event, attr):
                try:
                    setattr(event, attr, value)
                    return
                except Exception:
                    continue
        raise PermissionError(feedback)
