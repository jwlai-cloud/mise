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

REGISTRY = {r.slug: r for r in (SOFFRITTO,)}
