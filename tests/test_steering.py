import sys; sys.path.insert(0, "src")
from mise.policy import LEDGER, GATE_OBSERVATION_TTL
from mise.steering import guarded_advance, MiseSteering

class FakeToolUse:
    def __init__(self, name): self.name = name
class FakeEvent:
    def __init__(self, name): self.tool_use = FakeToolUse(name); self.cancel = None

s = MiseSteering()

e = FakeEvent("advance_step"); s._before_tool(e)
assert e.cancel, "should have been blocked with no gate"
print("no gate      -> BLOCKED:", e.cancel[:72], "...")

LEDGER.note_gate_passed()
e = FakeEvent("advance_step"); s._before_tool(e)
assert e.cancel is None
print("fresh gate   -> allowed")

LEDGER.gate_passed_at -= (GATE_OBSERVATION_TTL + 5)
e = FakeEvent("advance_step"); s._before_tool(e)
assert e.cancel
print("stale gate   -> BLOCKED:", e.cancel[:72], "...")

e = FakeEvent("check_doneness"); s._before_tool(e)
assert e.cancel is None
print("other tool   -> untouched")
print("\nall steering tests passed")
