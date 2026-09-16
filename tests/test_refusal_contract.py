"""Regression test for the bug that defeated the whole thesis.

Rule 2 shortens a repeated refusal so the assistant doesn't nag. The cooldown
used to be keyed on step alone, and the suppressed string was "Still not yet."
So a plain `wait` at t=0 consumed the budget, and thirty seconds later a
genuine `refuse` - steam across the lens, confidence 0.22 - came out of the
speaker as "Still not yet.": a confident readiness claim about a frame the
system had just decided it could not read.

CLAUDE.md invariant 2 says refuse must never be resolved by guessing.
This file exists so that never regresses.
"""
import sys
sys.path.insert(0, "src")
from mise.memory import CALIBRATION
from mise.policy import LEDGER
from mise.server import SHORT_FORM, check_doneness, _session
from mise.state import STORE

WAIT_WORDS = ("not yet", "still not yet")


def fresh(step=1):
    LEDGER.gate_passed_at = None
    LEDGER.refusals.clear()
    LEDGER.corrections.clear()
    # Calibration persists to .mise-memory.json by design. Without clearing it
    # here the suite moves its own thresholds and the second run disagrees with
    # the first.
    CALIBRATION._local.clear()
    _session.update({"recipe": "soffritto-demo", "step_index": step})


def test_a_wait_does_not_consume_the_refusal_budget():
    fresh()
    STORE.write(doneness=0.40, confidence=0.90, risk="none", evidence="edges still firm")
    first = check_doneness()
    assert first.verdict == "wait", first

    # Steam. Past the gate, but unreadable.
    STORE.write(doneness=0.88, confidence=0.20, risk="none", evidence="steam across the lens")
    second = check_doneness()
    assert second.verdict == "refuse", second
    assert second.say.lower().strip(".") not in WAIT_WORDS, (
        f"a refusal was spoken as a wait: {second.say!r}"
    )
    print(f"wait then refuse -> {second.say!r}")


def test_a_repeated_refusal_shortens_but_stays_a_refusal():
    fresh()
    STORE.write(doneness=0.88, confidence=0.20, risk="none", evidence="steam across the lens")
    first = check_doneness()
    second = check_doneness()
    assert first.verdict == second.verdict == "refuse"
    assert second.say == SHORT_FORM["refuse"], second.say
    assert second.say.lower().strip(".") not in WAIT_WORDS, second.say
    print(f"refuse twice     -> {first.say!r} then {second.say!r}")


def test_a_repeated_wait_still_shortens():
    fresh()
    STORE.write(doneness=0.40, confidence=0.90, risk="none", evidence="edges still firm")
    check_doneness()
    assert check_doneness().say == SHORT_FORM["wait"]
    print(f"wait twice       -> {SHORT_FORM['wait']!r}")


def test_danger_is_never_shortened_or_confidence_gated():
    fresh()
    # Burn the budget on both verdict kinds first.
    STORE.write(doneness=0.40, confidence=0.90, evidence="edges still firm")
    check_doneness(); check_doneness()
    STORE.write(doneness=0.88, confidence=0.20, evidence="steam")
    check_doneness(); check_doneness()

    # Confidence far below the step floor: abort must still win. Invariant 3.
    STORE.write(doneness=0.10, confidence=0.05, risk="urgent",
                evidence="Smoke at the edge of the pan.")
    d = check_doneness()
    assert d.verdict == "abort", d
    assert d.say.startswith("Take it off the heat"), d.say
    assert "Smoke" in d.say, d.say
    print(f"abort under load -> {d.say!r}")


def test_the_panel_never_shortens():
    """Invariant 4: suppressing the voice must never suppress the panel."""
    from mise.server import panel_state
    fresh()
    STORE.write(doneness=0.88, confidence=0.20, risk="none", evidence="steam across the lens")
    check_doneness()
    check_doneness()                      # now suppressed on the voice
    p = panel_state()
    assert p["verdict"] == "refuse", p
    assert p["reason"] and p["reason"] != SHORT_FORM["refuse"], p["reason"]
    print(f"panel while muted-> {p['verdict']!r}: {p['reason']!r}")


for f in (test_a_wait_does_not_consume_the_refusal_budget,
          test_a_repeated_refusal_shortens_but_stays_a_refusal,
          test_a_repeated_wait_still_shortens,
          test_danger_is_never_shortened_or_confidence_gated,
          test_the_panel_never_shortens):
    f()
print("\nall refusal-contract tests passed")


# ---- rule 4: the hand-back. Spoken as a promise before this was wired. ----

def test_rule_four_actually_stops_blocking():
    fresh()
    from mise.server import advance_step, record_correction
    STORE.write(doneness=0.10, confidence=0.95, risk="none", evidence="barely warmed")
    assert advance_step()["advanced"] is False, "should block before any correction"
    for _ in range(3):
        record_correction("too_late")
    out = advance_step()
    assert out["advanced"] is True, f"rule 4 promised a hand-back and did not deliver: {out}"
    print(f"3 corrections    -> advanced={out['advanced']} (gate never passed)")


def test_the_hand_back_never_claims_readiness():
    fresh()
    from mise.server import record_correction
    STORE.write(doneness=0.10, confidence=0.95, risk="none", evidence="barely warmed")
    for _ in range(3):
        record_correction("too_late")
    d = check_doneness()
    assert d.verdict in ("wait", "refuse"), d          # never flipped to proceed
    assert "your call" in d.say.lower(), d.say
    assert not d.say.lower().startswith("go ahead"), d.say
    print(f"handed back      -> {d.verdict!r}: {d.say!r}")


def test_danger_outranks_the_hand_back():
    fresh()
    from mise.server import advance_step, record_correction
    STORE.write(doneness=0.95, confidence=0.95, risk="none", evidence="looks done")
    for _ in range(3):
        record_correction("too_late")
    STORE.write(doneness=0.95, confidence=0.95, risk="urgent",
                evidence="Smoke at the edge of the pan.")
    out = advance_step()
    assert out["advanced"] is False, f"abort must block even after a hand-back: {out}"
    assert out["verdict"] == "abort", out
    print(f"hand-back + fire -> advanced={out['advanced']} verdict={out['verdict']!r}")


def test_the_panel_shows_the_calibrated_gate_immediately():
    """A correction the screen doesn't reflect is a screen telling a different
    story from the voice. Invariant 4."""
    fresh()
    from mise.server import panel_state, record_correction
    STORE.write(doneness=0.50, confidence=0.95, risk="none", evidence="softening")
    before = panel_state()["gate"]
    record_correction("too_early")
    after = panel_state()["gate"]
    assert after != before, f"panel still shows the old gate {before}"
    print(f"correction       -> panel gate {before} -> {after}")


for f in (test_rule_four_actually_stops_blocking,
          test_the_hand_back_never_claims_readiness,
          test_danger_outranks_the_hand_back,
          test_the_panel_shows_the_calibrated_gate_immediately):
    f()
print("all rule-4 and calibration tests passed")
