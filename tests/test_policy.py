import sys, time; sys.path.insert(0, "src")
from mise.policy import SessionLedger, GATE_OBSERVATION_TTL

L = SessionLedger()
d = L.may_advance(); assert not d.allowed; print("no gate yet      ->", d.explanation)
L.note_gate_passed()
d = L.may_advance(); assert d.allowed; print("fresh gate       ->", d.explanation)
L.gate_passed_at -= (GATE_OBSERVATION_TTL + 5)
d = L.may_advance(); assert not d.allowed; print("stale gate       ->", d.explanation)

d = L.may_speak_refusal(1); assert d.allowed; print("first refusal    ->", d.explanation)
L.note_refusal(1)
d = L.may_speak_refusal(1); assert not d.allowed; print("second refusal   ->", d.explanation)

assert L.may_speak_abort().allowed; print("abort            -> always allowed")

for _ in range(3): L.note_correction(2)
d = L.should_stop_gating(2); assert d.allowed; print("3 corrections    ->", d.explanation)
print("\nall policy tests passed")
