"""The boundary between the slow world and the fast world.

The vision loop WRITES here, continuously, on its own clock.
MCP tools READ here, and only here, so a tool call never waits on a model.

This is the single most important design decision in the project:
Alexa+ tools have a ~500ms round-trip budget. A vision model call does not
fit in that budget and never will. So the model never runs inside a tool call.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

Risk = Literal["none", "watch", "urgent"]


@dataclass
class CookState:
    """What the camera currently believes about the pan."""

    stage: str = "idle"              # human-readable: "sweating onions"
    doneness: float = 0.0            # 0.0 -> 1.0 toward the current step's goal
    confidence: float = 0.0          # how much the vision model trusts itself
    risk: Risk = "none"              # "urgent" == something is catching
    evidence: str = ""               # one sentence a human can check: "edges still firm"
    frame_seq: int = 0
    updated_at: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.updated_at

    @property
    def is_stale(self) -> bool:
        """No fresh frame == we must not pretend to know. See the refusal path."""
        return self.age_seconds > 15.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["age_seconds"] = round(self.age_seconds, 2)
        d["is_stale"] = self.is_stale
        return d


class StateStore:
    """Thread-safe last-known-good state. Deliberately tiny."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = CookState()

    def read(self) -> CookState:
        with self._lock:
            return CookState(**{k: v for k, v in asdict(self._state).items()})

    def write(self, updated_at: float | None = None, **changes: Any) -> CookState:
        """Record what the camera believes.

        `updated_at` is when the FRAME WAS TAKEN, not when we got round to
        storing it. Defaulting it to now is only correct for a source with no
        latency. A vision call takes two or three seconds, so stamping the
        write would make is_stale measure our own latency instead of the age of
        the view - a ~20% error on the input to the refusal path.
        """
        with self._lock:
            cur = asdict(self._state)
            cur.update(changes)
            cur["updated_at"] = time.time() if updated_at is None else updated_at
            cur["frame_seq"] = self._state.frame_seq + 1
            self._state = CookState(**cur)
            return self._state


STORE = StateStore()
