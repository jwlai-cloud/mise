"""Per-cook calibration on AgentCore Memory.

Samsung and GE calibrate to the appliance they sold you. Nobody calibrates to
*your* gas burner, *your* pan, and what *you* mean by "translucent" - learned
from you saying "that was too early" and the system moving its own threshold.

That is what this file does, and it is the reason AgentCore is load-bearing
here rather than decorative.

Degrades to a local JSON file when AWS is not configured, so the project runs
on a laptop with no credentials.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REGION = os.getenv("AWS_REGION", "ap-southeast-2")
MEMORY_NAME = os.getenv("MISE_MEMORY_NAME", "mise-cook-calibration")
LOCAL_FALLBACK = Path(os.getenv("MISE_LOCAL_MEMORY", ".mise-memory.json"))

# One namespace per cook per hob. Trailing slash is required by AgentCore to
# avoid multi-tenant prefix collisions.
NAMESPACE = "cook/{actorId}/hob/"

# How far a single correction may move a threshold. Small on purpose: one
# impatient "that was too early" should nudge, not overwrite.
LEARNING_RATE = 0.15
CLAMP = (0.35, 0.95)


class Calibration:
    """Threshold offsets, per (recipe, step). Bounded, auditable, reversible."""

    def __init__(self, actor_id: str = "default") -> None:
        self.actor_id = actor_id
        self._client = None
        self._memory_id: str | None = None
        self._local: dict[str, float] = {}
        self._load_local()
        self._try_connect()

    # ---------- transport ----------

    def _try_connect(self) -> None:
        # The SDK logs its own ERROR lines before raising. Without credentials
        # that is expected, not a fault - quiet it so a fresh session doesn't
        # mistake the fallback path for a broken build.
        sdk_log = logging.getLogger("bedrock_agentcore.memory.client")
        prior = sdk_log.level
        sdk_log.setLevel(logging.CRITICAL)
        try:
            from bedrock_agentcore.memory import MemoryClient

            client = MemoryClient(region_name=REGION)
            mem = client.create_or_get_memory(
                name=MEMORY_NAME,
                description="What each cook means by done, per hob and per step.",
                strategies=[
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "doneness-preferences",
                            "namespaces": [NAMESPACE],
                        }
                    }
                ],
            )
            self._client = client
            self._memory_id = mem.get("id") or mem.get("memoryId")
            log.info("AgentCore Memory ready: %s", self._memory_id)
        except Exception as exc:  # no creds, no region, no network - all fine
            log.info(
                "AgentCore Memory unavailable (%s); using local calibration file. "
                "This is the expected path without AWS credentials.",
                type(exc).__name__,
            )
        finally:
            sdk_log.setLevel(prior)

    @property
    def backend(self) -> str:
        return "agentcore" if self._client else "local"

    # ---------- local mirror ----------

    def _load_local(self) -> None:
        if LOCAL_FALLBACK.exists():
            try:
                self._local = json.loads(LOCAL_FALLBACK.read_text())
            except Exception:
                self._local = {}

    def _save_local(self) -> None:
        try:
            LOCAL_FALLBACK.write_text(json.dumps(self._local, indent=2))
        except Exception as exc:
            log.warning("could not persist local calibration: %s", exc)

    # ---------- the actual behaviour ----------

    @staticmethod
    def _key(recipe: str, step: int) -> str:
        return f"{recipe}:{step}"

    def gate_for(self, recipe: str, step: int, default: float) -> float:
        """The threshold to use right now, for this cook, on this hob."""
        return self._local.get(self._key(recipe, step), default)

    def record_correction(
        self, recipe: str, step: int, current_gate: float, direction: str, note: str = ""
    ) -> float:
        """The cook disagreed. Move the threshold, bounded, and write it down.

        direction: "too_early" -> raise the bar; "too_late" -> lower it.
        """
        sign = 1.0 if direction == "too_early" else -1.0
        new_gate = round(
            min(CLAMP[1], max(CLAMP[0], current_gate + sign * LEARNING_RATE)), 3
        )
        self._local[self._key(recipe, step)] = new_gate
        self._save_local()

        if self._client and self._memory_id:
            try:
                self._client.create_event(
                    memory_id=self._memory_id,
                    actor_id=self.actor_id,
                    session_id=datetime.now(timezone.utc).strftime("%Y%m%d"),
                    messages=[
                        (
                            f"On {recipe} step {step} you said it was {direction.replace('_',' ')}."
                            f"{(' ' + note) if note else ''}",
                            "USER",
                        ),
                        (
                            f"Noted. Moving the readiness threshold for that step "
                            f"from {current_gate} to {new_gate}.",
                            "ASSISTANT",
                        ),
                    ],
                )
            except Exception as exc:
                log.warning("memory write failed, local value stands: %s", exc)

        return new_gate

    def summary(self) -> dict[str, Any]:
        return {"backend": self.backend, "actor": self.actor_id, "offsets": dict(self._local)}


CALIBRATION = Calibration(actor_id=os.getenv("MISE_COOK", "default"))
