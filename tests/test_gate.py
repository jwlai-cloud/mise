import sys, time
sys.path.insert(0, "src")
from mise.gate import decide
from mise.recipes import SOFFRITTO
from mise.state import CookState

step = SOFFRITTO.step(1)  # onions

def test_wait_when_under_gate():
    d = decide(CookState(doneness=0.4, confidence=0.9, evidence="edges still firm"), step)
    assert d.verdict == "wait" and d.seconds_remaining > 0
    print("WAIT  ->", d.spoken())

def test_proceed_when_gate_met():
    d = decide(CookState(doneness=0.85, confidence=0.9, evidence="fully slumped, no colour"), step)
    assert d.verdict == "proceed"
    print("GO    ->", d.spoken())

def test_refuse_when_stale():
    s = CookState(doneness=0.9, confidence=0.9); s.updated_at = time.time() - 60
    d = decide(s, step)
    assert d.verdict == "refuse"
    print("REFUSE->", d.spoken())

def test_abort_beats_everything():
    d = decide(CookState(doneness=0.1, confidence=0.1, risk="urgent", evidence="Smoke at the edge of the pan."), step)
    assert d.verdict == "abort"
    print("ABORT ->", d.spoken())

for f in (test_wait_when_under_gate, test_proceed_when_gate_met, test_refuse_when_stale, test_abort_beats_everything):
    f()
print("\nall gate tests passed")
