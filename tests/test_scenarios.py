"""The demo rig's only job: make all four verdicts reachable without a model.

If this file fails, there is no demo - two of the four verdicts are the product
and a well-behaved simulated pan produces neither.
"""
import sys, time
sys.path.insert(0, "src")
from mise.gate import decide
from mise.recipes import REGISTRY
from mise.state import CookState
from mise.vision import SCENARIOS, _sample

step = REGISTRY["soffritto-demo"].step(1)  # the onions: gate 0.8, min_confidence 0.6


def verdicts(name, horizon=100):
    """Every verdict the gate produces while this scenario plays out."""
    seen, last_write, age = set(), 0.0, 0.0
    snapshot = {"doneness": 0.0, "confidence": 0.0}
    for t in range(horizon):
        fields = _sample(SCENARIOS[name], float(t))
        if fields is not None:                     # mirrors ScenarioSource._tick
            snapshot = dict(fields)
            age = snapshot.pop("age", 0.0)
            last_write = t
        state = CookState(**snapshot)
        # A frame's age is its own age plus however long since it was written.
        state.updated_at = time.time() - age - (t - last_write)
        seen.add(decide(state, step).verdict)
    return seen


def test_clean_run_reaches_go():
    v = verdicts("clean_run")
    assert "wait" in v and "proceed" in v, v
    assert "refuse" not in v and "abort" not in v, v
    print("clean_run ->", sorted(v))


def test_steam_refuses_while_past_the_gate():
    v = verdicts("steam")
    assert "refuse" in v, v
    # The point of this scenario: doneness is PAST the gate while unreadable,
    # so a system that guessed would have said proceed.
    f = _sample(SCENARIOS["steam"], 45.0)
    assert f["doneness"] >= step.gate_doneness and f["confidence"] < step.min_confidence, f
    print("steam     ->", sorted(v), "| at t=45:", f["doneness"], "conf", f["confidence"])


def test_blocked_goes_stale():
    """Backdated frame lands the verdict in one tick, silence keeps it there."""
    v = verdicts("blocked")
    assert "refuse" in v, v
    assert _sample(SCENARIOS["blocked"], 60.0) is None, "should be writing nothing by now"
    print("blocked   ->", sorted(v))


def test_catches_aborts_despite_low_confidence():
    v = verdicts("catches")
    assert "abort" in v, v
    f = _sample(SCENARIOS["catches"], 50.0)
    assert f["risk"] == "urgent" and f["confidence"] < step.min_confidence, f
    # Invariant 3: danger is never gated on confidence.
    d = decide(CookState(**{k: v for k, v in f.items() if k != "age"}), step)
    assert d.verdict == "abort", d
    print("catches   ->", sorted(v), "| aborts at confidence", f["confidence"])


def test_every_verdict_is_reachable_somewhere():
    union = set().union(*(verdicts(n) for n in SCENARIOS))
    assert union == {"proceed", "wait", "refuse", "abort"}, union
    print("union     ->", sorted(union))


for f in (test_clean_run_reaches_go, test_steam_refuses_while_past_the_gate,
          test_blocked_goes_stale, test_catches_aborts_despite_low_confidence,
          test_every_verdict_is_reachable_somewhere):
    f()
print("\nall scenario tests passed")


def test_arming_a_scenario_never_leaves_the_previous_verdict_on_screen():
    """The panel must never show a verdict from a demo that already finished.

    Seeking into a silent stretch writes nothing, so without seeding, STORE
    keeps the last scenario's frame and merely ages it — an operator arms
    'blocked' on camera and the screen still reads OFF THE HEAT.
    """
    from mise.state import STORE
    from mise.vision import ScenarioSource

    src = ScenarioSource("catches")           # not started: no thread, seed only
    src.restart("catches", at=46)
    assert decide(STORE.read(), step).verdict == "abort", "setup"

    src.restart("blocked", at=38)             # lands past the silent frame
    s = STORE.read()
    d = decide(s, step)
    assert "Smoke" not in s.evidence, f"previous scenario leaked: {s.evidence!r}"
    assert d.verdict == "refuse" and s.is_stale, (d.verdict, s.is_stale, s.evidence)
    print(f"arm blocked@38   -> {d.verdict!r} stale={s.is_stale} evidence={s.evidence!r}")


test_arming_a_scenario_never_leaves_the_previous_verdict_on_screen()
print("scenario-switch test passed")
