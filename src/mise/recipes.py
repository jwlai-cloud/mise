"""A recipe is not a list of steps. It is a list of GATES.

Each step declares what must be true of the pan before you may leave it.
The gate is what makes this project different from every recipe app:
the assistant can refuse to advance.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    index: int
    instruction: str          # what you are doing now
    goal: str                 # what "done" looks like, in plain words
    gate_doneness: float      # doneness required before the NEXT step
    min_confidence: float = 0.6   # below this we refuse to judge at all
    typical_seconds: int = 120    # for the "about 90 seconds" estimate


@dataclass
class Recipe:
    slug: str
    title: str
    steps: list[Step] = field(default_factory=list)

    def step(self, i: int) -> Step:
        return self.steps[max(0, min(i, len(self.steps) - 1))]


SOFFRITTO = Recipe(
    slug="soffritto",
    title="Soffritto base",
    steps=[
        Step(0, "Warm the oil over medium heat.", "oil shimmers, no smoke", 0.7, typical_seconds=90),
        Step(1, "Add the diced onion.", "translucent and slumped, no colour on the edges", 0.8, typical_seconds=420),
        Step(2, "Add the garlic.", "fragrant, pale gold, not browned", 0.75, typical_seconds=60),
        Step(3, "Add the tomato paste.", "darkened from red to brick", 0.7, typical_seconds=150),
    ],
)

# The same gates on a compressed clock, so the spoken estimate matches what the
# demo scenarios actually do. Without this the panel fills in ninety seconds
# while the voice says "about 168 seconds" - true of a real soffritto, visibly
# wrong on camera.
# ponytail: a scale factor, not a second recipe format. If a third timeline is
# ever needed, make typical_seconds a property of the run rather than the step.
SOFFRITTO_DEMO = Recipe(
    slug="soffritto-demo",
    title="Soffritto base",
    steps=[
        Step(s.index, s.instruction, s.goal, s.gate_doneness, s.min_confidence,
             typical_seconds=max(10, round(s.typical_seconds * 90 / 420)))
        for s in SOFFRITTO.steps
    ],
)

REGISTRY = {r.slug: r for r in (SOFFRITTO, SOFFRITTO_DEMO)}
