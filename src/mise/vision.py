"""The slow loop. Runs on its own clock, never inside a tool call.

Two sources, one seam. Whatever the source, it writes CookState fields into
STORE and nothing else:

  ScenarioSource - a scripted pan. Deterministic, restartable, and able to
                   reach ALL FOUR verdicts with no model and no credentials.
  ingest_frame() - real frames from the phone -> a vision model -> CookState.

The scenarios exist because the demo has to show `refuse` and `abort`, and
those are the two verdicts a well-behaved pan never produces. A camera that
always works cannot demonstrate a system whose selling point is admitting when
the camera doesn't.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .state import STORE, Risk


@dataclass(frozen=True)
class Frame:
    """One keyframe on a scenario's timeline.

    `silent` writes nothing at all. That is how staleness is produced: STORE
    stops being written, age_seconds grows past 15, and the gate refuses. There
    is no "set stale" flag anywhere, because in the real system there isn't one
    either - frames just stop arriving.
    """

    at: float                  # seconds from scenario start
    doneness: float = 0.0
    confidence: float = 0.90
    risk: Risk = "none"
    stage: str = ""
    evidence: str = ""
    age: float = 0.0           # how old the FRAME is when written, in seconds
    silent: bool = False


# Four scenarios, one per verdict. Each runs in about ninety seconds so it fits
# inside a three-minute demo video with room to talk over it.
SCENARIOS: dict[str, list[Frame]] = {
    # proceed - the pan behaves. NOT YET -> GO.
    "clean_run": [
        Frame(0,  0.15, stage="oil warming",       evidence="barely warmed"),
        Frame(10, 0.28, stage="onions going in",   evidence="just hitting the oil"),
        Frame(20, 0.42, stage="onions going in",   evidence="edges still firm"),
        Frame(45, 0.68, stage="onions sweating",   evidence="softening, still opaque"),
        Frame(70, 0.86, stage="onions translucent", evidence="slumped, no colour on the edges"),
        Frame(85, 0.94, stage="onions translucent", evidence="fully translucent"),
    ],
    # refuse via low confidence - the dangerous case. Doneness reads PAST the
    # gate while the view is unreadable, so a guessing system would say GO.
    "steam": [
        Frame(0,  0.20, stage="oil warming",     evidence="barely warmed"),
        Frame(12, 0.36, stage="onions going in", evidence="just hitting the oil"),
        Frame(25, 0.55, stage="onions sweating", evidence="edges still firm"),
        Frame(40, 0.88, stage="onions sweating", confidence=0.22,
              evidence="steam across the lens"),
        Frame(70, 0.79, stage="onions sweating", confidence=0.91,
              evidence="clearing - not quite there"),
        Frame(85, 0.91, stage="onions translucent", confidence=0.93,
              evidence="fully translucent"),
    ],
    # refuse via staleness - the camera stops. NOT YET -> CAN'T TELL, and the
    # whole panel dims because is_stale is true.
    #
    # The `age` on the hand-over frame is what makes this filmable: without it
    # the operator waits out the full 15s staleness threshold in real time,
    # which is fifteen seconds of a motionless screen in a three-minute video.
    # One backdated frame lands the verdict in a single tick, and the silence
    # that follows keeps the counter climbing honestly.
    "blocked": [
        Frame(0,  0.22, stage="oil warming",     evidence="barely warmed"),
        Frame(20, 0.58, stage="onions sweating", evidence="softening"),
        Frame(35, 0.58, stage="onions sweating", evidence="hand across the pan", age=18),
        Frame(37, 0.0,  silent=True),
    ],
    # abort - overrides everything, including a confidence too low to judge on.
    "catches": [
        Frame(0,  0.25, stage="oil warming",     evidence="barely warmed"),
        Frame(20, 0.61, stage="onions sweating", evidence="softening nicely"),
        Frame(42, 0.74, stage="onions sweating", confidence=0.40, risk="urgent",
              evidence="Smoke at the edge of the pan."),
    ],
}

DEFAULT_SCENARIO = "clean_run"


def _sample(scenario: list[Frame], t: float) -> dict | None:
    """The pan's state at time t, or None to write nothing.

    Doneness is interpolated between keyframes so the panel meter moves
    smoothly; every other field steps at its keyframe.
    """
    cur, nxt = scenario[0], None
    for i, f in enumerate(scenario):
        if f.at > t:
            break
        cur, nxt = f, (scenario[i + 1] if i + 1 < len(scenario) else None)

    if cur.silent:
        return None

    doneness = cur.doneness
    if nxt is not None and not nxt.silent and nxt.at > cur.at:
        span = min(1.0, (t - cur.at) / (nxt.at - cur.at))
        doneness += (nxt.doneness - cur.doneness) * span

    return {
        "stage": cur.stage,
        "doneness": round(doneness, 3),
        "confidence": cur.confidence,
        "risk": cur.risk,
        "evidence": cur.evidence,
        "age": cur.age,
    }


class ScenarioSource:
    """A scripted pan. Deterministic, restartable, no model required.

    Restartable is the point: a demo you cannot replay is a demo you get one
    take of. `restart()` resets the clock, so the operator can jump between
    verdicts on camera without bouncing the server.
    """

    def __init__(self, name: str = DEFAULT_SCENARIO, hz: float = 1.0) -> None:
        self.hz = hz
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.restart(name)

    # ---------- control ----------

    def restart(self, name: str | None = None, at: float = 0.0) -> str:
        """Jump to a scenario (or replay the current one), seeking to `at`.

        Seeking matters on a shoot: the interesting beat in `steam` is at t=40,
        and waiting forty seconds of real time for every take is the difference
        between a morning and an afternoon.
        """
        with self._lock:
            if name is not None:
                if name not in SCENARIOS:
                    raise KeyError(name)
                self._name = name
            self._t0 = time.time() - max(0.0, at)
        self._seed()
        return self._name

    def _seed(self) -> None:
        """Write the new scenario's state immediately, before the next tick.

        Silence writes nothing, so switching into - or seeking past - a silent
        stretch would otherwise leave the PREVIOUS scenario's frame in STORE,
        quietly ageing. On camera that is the panel showing OFF THE HEAT from
        the demo you just finished while you talk about a blocked lens.

        Staleness must come from this scenario's own last real frame having
        aged, never from another scenario's leftovers.
        """
        with self._lock:
            scenario, t = SCENARIOS[self._name], time.time() - self._t0
        last = None
        for f in scenario:
            if f.at > t:
                break
            if not f.silent:
                last = f
        if last is None:                      # seeked before the first real frame
            last = next((f for f in scenario if not f.silent), None)
        if last is None:
            return
        fields = _sample(scenario, min(t, last.at))
        if fields is None:
            return
        age = fields.pop("age", 0.0) + max(0.0, t - last.at)
        STORE.write(updated_at=time.time() - age, **fields)

    @property
    def name(self) -> str:
        return self._name

    @property
    def elapsed(self) -> float:
        return time.time() - self._t0

    # ---------- the loop ----------

    def _tick(self) -> None:
        with self._lock:
            scenario, t = SCENARIOS[self._name], time.time() - self._t0
        fields = _sample(scenario, t)
        if fields is not None:
            age = fields.pop("age", 0.0)
            STORE.write(updated_at=time.time() - age, **fields)

    def run(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(1.0 / self.hz)

    def start(self) -> "ScenarioSource":
        if self._thread is None:
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()


def ingest_frame(jpeg_bytes: bytes) -> None:
    """Real frames land here. Week-1 spike.

    Send the frame to a vision model with a structured-output schema matching
    CookState, then STORE.write(**result). Throttle to roughly one call every
    2-3 seconds; drop frames rather than queue them, because a stale answer is
    worse than no answer - state.is_stale already handles the gap honestly.

    The caller (app.py::ingest) already drops frames while one is in flight, so
    this function may block. It must never be called from an MCP tool.
    """
    raise NotImplementedError("Week 1: wire a vision model here.")


if __name__ == "__main__":  # smallest check that the scenarios do what they claim
    from .gate import decide
    from .recipes import REGISTRY

    step = REGISTRY["soffritto"].step(1)
    expected = {"clean_run": "proceed", "steam": "refuse",
                "blocked": "refuse", "catches": "abort"}

    for name, want in expected.items():
        seen, last_write, age = set(), 0, 0.0
        for t in range(0, 100):
            fields = _sample(SCENARIOS[name], float(t))
            if fields is not None:
                age = fields.pop("age", 0.0)
                STORE.write(updated_at=time.time() - age, **fields)
                last_write = t
            # Silence means no write; the view keeps getting older.
            state = STORE.read()
            state.updated_at = time.time() - age - (t - last_write)
            seen.add(decide(state, step).verdict)
        assert want in seen, f"{name}: expected {want}, saw {sorted(seen)}"
        print(f"{name:11s} -> {sorted(seen)}")

    print("\nall four verdicts reachable")
