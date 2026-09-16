"""The real-frame path, tested with no credentials, no network and no model.

Two properties matter more than the happy path:

  1. A frame is timestamped when the SHUTTER fired, not when the model answered.
     A vision call costs seconds; stamping the write would hand the gate a view
     that looks fresher than it is, and staleness is a refusal trigger.
  2. A failed call writes NOTHING. Silence lets the last frame age until the
     gate refuses on its own. Inventing a reading to represent failure would be
     guessing about the pan.
"""
import sys, time
sys.path.insert(0, "src")
from mise.gate import decide
from mise.perception import PerceptionError, Reading, ScriptedVision, validate
from mise.recipes import SOFFRITTO
from mise.state import STORE
import mise.vision as vision

step = SOFFRITTO.step(1)
GOAL = step.goal


def use(readings):
    m = ScriptedVision(readings)
    vision.MODEL = m
    return m


def test_a_good_frame_lands_in_the_cache():
    use([Reading("onions sweating", 0.62, 0.91, "none", "softening at the edges")])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    s = STORE.read()
    assert s.doneness == 0.62 and s.confidence == 0.91, s
    assert decide(s, step).verdict == "wait", s
    print(f"good frame       -> doneness {s.doneness}, verdict wait")


def test_the_frames_age_is_the_shutter_not_the_model():
    """A three-second model call must not reset the clock on a ten-second-old view."""
    use([Reading("onions sweating", 0.9, 0.95, "none", "slumped")])
    shutter = time.time() - 20            # taken 20s ago, model answers now
    vision.ingest_frame(b"jpeg", captured_at=shutter, goal=GOAL)
    s = STORE.read()
    assert s.age_seconds >= 19, f"age {s.age_seconds} — the shutter time was discarded"
    assert s.is_stale, "a 20s-old view must be stale even though we just wrote it"
    assert decide(s, step).verdict == "refuse", decide(s, step)
    print(f"20s-old frame    -> age {s.age_seconds:.0f}s, verdict refuse")


def test_a_failed_call_writes_nothing():
    good = Reading("onions sweating", 0.55, 0.92, "none", "softening")
    use([good])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    before = STORE.read()

    use([PerceptionError("model said something unusable")])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    after = STORE.read()
    assert after.frame_seq == before.frame_seq, "a failed call must not write"
    assert after.doneness == before.doneness
    print(f"failed call      -> frame_seq unchanged at {after.frame_seq}")


def test_a_transport_error_also_writes_nothing():
    """Throttling and auth failures are not PerceptionError, and must not escape
    into the ingest route either."""
    use([ConnectionError("throttled")])
    before = STORE.read().frame_seq
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    assert STORE.read().frame_seq == before
    print("transport error  -> swallowed, nothing written")


def test_silence_after_a_failure_ages_into_a_refusal():
    """The failure path and the staleness path are the same path. That is the
    design: we never write 'I failed', we just stop writing."""
    use([Reading("onions sweating", 0.95, 0.95, "none", "looks ready")])
    vision.ingest_frame(b"jpeg", captured_at=time.time() - 14, goal=GOAL)
    assert decide(STORE.read(), step).verdict == "proceed"

    use([PerceptionError("lens fogged")])           # every later frame fails
    for _ in range(3):
        vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
        use([PerceptionError("lens fogged")])
    s = STORE.read()
    s.updated_at -= 3                                # three seconds of failures
    assert s.is_stale and decide(s, step).verdict == "refuse", (s.age_seconds, s)
    print(f"failures ageing  -> {decide(s, step).verdict} after {s.age_seconds:.0f}s")


def test_danger_survives_a_confidence_too_low_to_judge():
    """Invariant 3, end to end from a real frame."""
    use([Reading("onions sweating", 0.3, 0.11, "urgent", "Smoke at the edge of the pan.")])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    d = decide(STORE.read(), step)
    assert d.verdict == "abort", d
    print(f"urgent @ conf .11-> {d.verdict}")


def test_the_model_is_asked_about_this_step_specifically():
    m = use([Reading("onions sweating", 0.5, 0.9, "none", "softening")])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    assert m.calls and m.calls[0][1] == GOAL, m.calls
    print(f"goal passed      -> {m.calls[0][1]!r}")


def test_malformed_model_output_is_refused_not_clamped():
    for bad in ({"doneness": 1.4, "confidence": 0.9, "evidence": "x"},
                {"doneness": 0.5, "confidence": 0.9, "risk": "medium", "evidence": "x"},
                {"doneness": 0.5, "confidence": 0.9, "evidence": "   "},
                {"confidence": 0.9, "evidence": "x"}):
        try:
            validate(bad)
        except PerceptionError:
            continue
        raise AssertionError(f"accepted malformed reading: {bad}")
    print("malformed output -> all four rejected")


for f in (test_a_good_frame_lands_in_the_cache,
          test_the_frames_age_is_the_shutter_not_the_model,
          test_a_failed_call_writes_nothing,
          test_a_transport_error_also_writes_nothing,
          test_silence_after_a_failure_ages_into_a_refusal,
          test_danger_survives_a_confidence_too_low_to_judge,
          test_the_model_is_asked_about_this_step_specifically,
          test_malformed_model_output_is_refused_not_clamped):
    f()
print("\nall ingest tests passed")


# ---- the clamp: hold the model to what it admitted about the view ----

def test_confidence_is_clamped_down_to_what_the_view_allows():
    from mise.perception import clamp_confidence
    lying = {"view": "obscured", "obstructions": ["steam"], "risk": "none",
             "stage": "onions", "doneness": 0.88, "confidence": 0.93,
             "evidence": "looks translucent"}
    r = validate(clamp_confidence(lying))
    assert r.confidence <= 0.35, r
    assert r.doneness == 0.88, "doneness must stay honest; only trust is clamped"
    assert decide_state(r).verdict == "refuse", decide_state(r)
    print(f"model claims .93 on steam -> clamped {r.confidence}, verdict refuse")


def test_the_clamp_never_raises_confidence():
    from mise.perception import clamp_confidence
    modest = {"view": "clear", "obstructions": [], "risk": "none", "stage": "onions",
              "doneness": 0.5, "confidence": 0.31, "evidence": "hard to call"}
    assert clamp_confidence(modest)["confidence"] == 0.31
    print("modest model on a clear view -> left alone at 0.31")


def test_danger_is_never_clamped():
    from mise.perception import clamp_confidence
    burning = {"view": "obscured", "obstructions": ["steam"], "risk": "urgent",
               "stage": "onions", "doneness": 0.4, "confidence": 0.90,
               "evidence": "Dark smoke off the pan."}
    r = validate(clamp_confidence(burning))
    assert r.risk == "urgent" and r.confidence <= 0.35, r
    assert decide_state(r).verdict == "abort", "invariant 3: danger beats the clamp"
    print(f"urgent at clamped {r.confidence} -> abort")


def test_no_pan_cannot_read_as_partly_done():
    from mise.perception import clamp_confidence
    empty = {"view": "no_pan", "obstructions": ["out_of_frame"], "risk": "none",
             "stage": "nothing in frame", "doneness": 0.7, "confidence": 0.8,
             "evidence": "no pan in shot"}
    r = validate(clamp_confidence(empty))
    assert r.doneness == 0.0 and r.confidence <= 0.10, r
    print(f"no pan -> doneness {r.doneness}, confidence {r.confidence}")


def decide_state(r):
    from mise.state import CookState
    return decide(CookState(**r.as_state_fields()), step)


for f in (test_confidence_is_clamped_down_to_what_the_view_allows,
          test_the_clamp_never_raises_confidence,
          test_danger_is_never_clamped,
          test_no_pan_cannot_read_as_partly_done):
    f()
print("all clamp tests passed")


# ---- one writer at a time ----

def test_the_scripted_pan_stands_down_when_a_real_camera_arrives():
    """Both write to the same STORE. The scenario ticks at 1 Hz, so if it keeps
    running it wins the last write and the panel shows a simulated pan while a
    real one is on the hob — silently, and fatally for the demo."""
    import mise.app as app
    from mise.state import STORE

    app.SOURCE.resume("clean_run", at=80)
    assert app.SOURCE.running and not app._live_camera
    time.sleep(1.2)
    scripted = STORE.read().evidence

    app.stop_scenarios("test")
    assert app._live_camera and not app.SOURCE.running, "scripted pan still writing"

    use([Reading("onions sweating", 0.33, 0.92, "none", "a real pan, barely started")])
    vision.ingest_frame(b"jpeg", captured_at=time.time(), goal=GOAL)
    time.sleep(1.2)                       # a live scenario would have overwritten by now
    s = STORE.read()
    assert s.evidence == "a real pan, barely started", (
        f"scripted pan overwrote the camera: {s.evidence!r} (was {scripted!r})")
    print(f"handover         -> camera holds the store: {s.evidence!r}")

    app._live_camera = False              # operator arms a scenario again
    app.SOURCE.resume("catches", at=44)
    time.sleep(1.2)
    assert STORE.read().risk == "urgent", "operator could not take the rig back"
    print("operator recovery-> scenario has the store again")
    app.SOURCE.stop()


test_the_scripted_pan_stands_down_when_a_real_camera_arrives()
print("all writer-handover tests passed")
