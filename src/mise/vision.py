"""The slow loop. Runs on its own clock, never inside a tool call.

Two sources:
  SimulatedSource - deterministic ramp, so the panel and the demo work today
  ModelSource     - real frames -> a vision model -> CookState  (week 1 spike)

Keep the contract narrow: whatever the source, it writes CookState fields
into STORE and nothing else.
"""
from __future__ import annotations

import threading
import time

from .state import STORE

STAGES = ["oil warming", "onions going in", "onions sweating", "onions translucent"]


class SimulatedSource:
    """A pan that behaves itself, for development and for a demo fallback."""

    def __init__(self, seconds_to_done: float = 45.0) -> None:
        self.seconds_to_done = seconds_to_done
        self._stop = threading.Event()
        self._t0 = time.time()

    def _tick(self) -> None:
        elapsed = time.time() - self._t0
        d = min(1.0, elapsed / self.seconds_to_done)
        stage = STAGES[min(len(STAGES) - 1, int(d * len(STAGES)))]
        evidence = "edges still firm" if d < 0.8 else "fully slumped, no colour on the edges"
        STORE.write(stage=stage, doneness=round(d, 3), confidence=0.88,
                    risk="none", evidence=evidence)

    def run(self, hz: float = 1.0) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(1.0 / hz)

    def start(self) -> "SimulatedSource":
        threading.Thread(target=self.run, daemon=True).start()
        return self

    def stop(self) -> None:
        self._stop.set()


def ingest_frame(jpeg_bytes: bytes) -> None:
    """Week-1 spike lives here.

    Send the frame to a vision model with a structured-output schema matching
    CookState, then STORE.write(**result). Throttle to roughly one call every
    2-3 seconds; drop frames rather than queue them, because a stale answer is
    worse than no answer - state.is_stale already handles the gap honestly.
    """
    raise NotImplementedError("Week 1: wire a vision model here.")
