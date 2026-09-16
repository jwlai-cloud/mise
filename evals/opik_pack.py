"""Opik wrapper around evals/abstention.py. Optional, additive, zero-credential.

WHAT THIS IS NOT
----------------
It is not a second metric. Every number Opik displays is computed by
`evals.abstention`, which is the unit-tested source of truth. This file only
moves rows into an Opik Dataset, runs one model profile over them as an
Experiment, and hands the resulting ratios back. If the two ever disagree it is
a bug in this file, not a difference of opinion.

WHY OPIK AND NOT JUST THE HARNESS
---------------------------------
`abstention.py` answers "what are the numbers for this run". ADR-0004 needs
"which of two model profiles is better over the SAME corpus", which is a
comparison across runs, and a stdout report cannot hold one. That is the whole
job: experiment tracking for the au/us decision. See the division of labour with
AgentCore Evaluations at the bottom of this docstring.

WHERE THE RATIOS LIVE
---------------------
Coverage, selective risk and abstention precision are corpus-level ratios, not
means of per-row scores. Opik averages per-row metrics, so putting them there
would silently produce the wrong number (mean of per-row "was this abstention
justified" is not abstention precision). They go in `experiment_scoring_functions`
instead, which is handed every TestResult at once - exactly the shape
`abstention.evaluate(rows)` already takes.

The per-row metric therefore emits only the BUCKET (correct / wrong /
justified_abstention / unnecessary_abstention), so a judge can click a red row
and see the frame that caused it.

DIVISION OF LABOUR WITH AGENTCORE EVALUATIONS
---------------------------------------------
  Opik               offline, one labelled corpus, the PERCEPTION layer.
                     Question: does this model read this pan to +/-0.15, and
                     does it decline when it can't? Runs with no AWS account.
  AgentCore Evals    online, sampled production traces, the AGENT TRAJECTORY.
                     Question: did the graph take a sane path and call the right
                     tools? Requires Runtime and credentials we do not have.
They score different objects. Neither replaces the other.

RUN
---
    python3 evals/opik_pack.py                      # no Opik: prints the harness report
    opik configure --use_local                      # or: export OPIK_URL_OVERRIDE=...
    python3 evals/opik_pack.py push
    python3 evals/opik_pack.py run --profile recorded
    python3 evals/opik_pack.py compare au us        # the ADR-0004 decision
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evals.abstention import (  # noqa: E402
    CREDIBLE_N, TOLERANCE, Scores, always_answer_risk, evaluate, load, report,
    sweep, sweep_report,
)

DATASET = "mise-pan-readiness"
LABELS = ROOT / "evals" / "labels.jsonl"
STEP_INDEX = 1                     # the onions; the 0.8 gate the corpus is written against

# Only these keys may come from the model. Everything else on a row is ground
# truth and a task must not be able to overwrite it.
FROM_MODEL = ("doneness", "confidence", "risk", "evidence")


@dataclass(frozen=True)
class Profile:
    """One thing to compare. ADR-0004 compares two of these over one corpus."""

    name: str
    backend: str                   # "recorded" | "bedrock" | "graph"
    model_id: str | None = None
    region: str | None = None

    def as_config(self) -> dict[str, Any]:
        return {"profile": self.name, "backend": self.backend,
                "model_id": self.model_id, "region": self.region,
                "step_index": STEP_INDEX, "tolerance": TOLERANCE}


# ponytail: the us model id is a placeholder. ADR-0004 records that
# bedrock:ListFoundationModels is denied on this account in both regions, so the
# real frontier id cannot be enumerated yet - override it rather than edit this.
PROFILES = {
    "recorded": Profile("recorded", "recorded"),
    "au": Profile("au", "bedrock",
                  os.getenv("MISE_MODEL_AU", "au.anthropic.claude-haiku-4-5-20251001-v1:0"),
                  os.getenv("MISE_REGION_AU", "ap-southeast-2")),
    "us": Profile("us", "bedrock",
                  os.getenv("MISE_MODEL_US", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
                  os.getenv("MISE_REGION_US", "us-east-1")),
    "graph": Profile("graph", "graph", os.getenv("MISE_MODEL_AU"), os.getenv("AWS_REGION")),
}


def have_opik() -> bool:
    return importlib.util.find_spec("opik") is not None


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------

def merge(item: dict, output: dict) -> dict:
    """Ground truth from the dataset, estimate from the model. One row for
    abstention.evaluate(). The whitelist is load-bearing: a task that could
    write label_doneness would be grading its own homework."""
    row = {k: v for k, v in item.items() if not k.startswith("_")}
    row.update({k: output[k] for k in FROM_MODEL if k in output})
    return row


def bucket(s: Scores) -> tuple[str, float]:
    """Which of the four outcomes a one-row Scores landed in. 1.0 is 'handled
    well' - a justified refusal scores the same as a correct answer, because
    that is the premise of the whole project."""
    if s.correct_answer:
        return "correct", 1.0
    if s.good_abstention:
        return "justified_abstention", 1.0
    if s.wrong_answer:
        return "wrong", 0.0
    return "unnecessary_abstention", 0.0


# --------------------------------------------------------------------------
# metrics - both of these only call into evals.abstention
# --------------------------------------------------------------------------

def build_metric(step_index: int = STEP_INDEX):
    from opik.evaluation.metrics import base_metric, score_result

    class AbstentionOutcome(base_metric.BaseMetric):
        """Per-row bucket, decided by running the tested harness on a corpus of one."""

        def __init__(self) -> None:
            super().__init__(name="abstention_outcome")

        def score(self, doneness: float | None = None, confidence: float | None = None,
                  perception_error: str | None = None,
                  **row: Any) -> "score_result.ScoreResult":
            if perception_error or doneness is None or confidence is None:
                # The model produced no reading. In the live system that writes
                # nothing and the view ages until the gate refuses on its own -
                # there is no per-frame equivalent, so this is reported as a
                # failure rather than folded into the ratios as a free refusal.
                return score_result.ScoreResult(
                    name="abstention_outcome", value=0.0, category_name="no_reading",
                    reason=perception_error or "task returned no doneness/confidence",
                    scoring_failed=True,
                )
            s = evaluate([merge(row, {"doneness": doneness, "confidence": confidence})],
                         step_index)
            name, value = bucket(s)
            return score_result.ScoreResult(
                name="abstention_outcome", value=value, category_name=name,
                reason=(s.misses[0] if s.misses else
                        f"|{doneness} - {row.get('label_doneness')}| vs tolerance {TOLERANCE}"),
                metadata={"degraded": bool(s.degraded), "confidence": confidence},
            )

    return AbstentionOutcome()


def build_corpus_scorer(step_index: int = STEP_INDEX) -> Callable[[list], list]:
    """The headline numbers. Corpus-level, so they go here and nowhere else."""
    from opik.evaluation.metrics import score_result

    def score_corpus(test_results: list) -> list:
        rows, dropped = [], 0
        for r in test_results:
            out = r.test_case.task_output or {}
            if out.get("perception_error") or "doneness" not in out:
                dropped += 1
                continue
            rows.append(merge(r.test_case.dataset_item_content, out))

        n = len(rows) + dropped
        if not rows:
            return [score_result.ScoreResult(
                name="coverage", value=0.0, scoring_failed=True,
                reason=f"all {n} frames failed perception")]

        s = evaluate(rows, step_index)
        base = always_answer_risk(rows, step_index)
        caveat = (f" NOT A RESULT: {s.n} frames < {CREDIBLE_N}." if s.n < CREDIBLE_N else "")
        caveat += f" {dropped} frame(s) produced no reading." if dropped else ""
        safe = [t for t, sc in sweep(rows, step_index) if sc.risk == 0.0]

        return [
            score_result.ScoreResult(
                name="coverage", value=s.coverage,
                reason=f"judged {s.answered}/{s.n} frames.{caveat}"),
            score_result.ScoreResult(
                name="selective_risk", value=s.risk,
                reason=f"{s.wrong_answer} wrong of {s.answered} judged.{caveat}"),
            score_result.ScoreResult(
                name="abstention_precision", value=s.abstention_precision,
                reason=f"{s.good_abstention} of {s.abstained} refusals were "
                       f"estimates off by >{TOLERANCE}.{caveat}"),
            score_result.ScoreResult(
                name="always_answer_risk", value=base,
                reason="what a system that never refused would get wrong"),
            score_result.ScoreResult(
                name="risk_reduction", value=base - s.risk,
                reason="what the refusal contract buys. <= 0 means it buys nothing."),
            score_result.ScoreResult(
                name="safe_confidence_floor", value=min(safe) if safe else 1.0,
                reason="lowest floor with zero selective risk" if safe
                       else "no floor achieves zero risk",
                # The whole risk-coverage sweep, so the threshold argument is
                # settled inside the experiment that made the claim.
                metadata={"sweep": [{"floor": t, "coverage": round(sc.coverage, 3),
                                     "risk": round(sc.risk, 3)}
                                    for t, sc in sweep(rows, step_index)]}),
        ]

    return score_corpus


# --------------------------------------------------------------------------
# task
# --------------------------------------------------------------------------

def build_task(profile: Profile, step_index: int = STEP_INDEX):
    """Turn one dataset item into a reading.

    Two shapes of row, deliberately:
      no `frame`  -> replay the recorded doneness/confidence. Works today, with
                     no credentials, and compares gate configurations only.
      has `frame` -> run the profile's model over the JPEG. This is the ADR-0004
                     comparison, and it needs a corpus with frames, which
                     labels.jsonl does not have yet.
    """
    if profile.backend == "recorded":
        def replay(item: dict) -> dict:
            return {k: item[k] for k in FROM_MODEL if k in item}
        return replay

    from mise.perception import BedrockVision, PerceptionError
    from mise.recipes import SOFFRITTO

    if profile.backend == "graph":
        from mise.agents import GraphVision          # late: pulls in strands
        model = GraphVision()
    else:
        model = BedrockVision(model_id=profile.model_id, region=profile.region)
    goal = SOFFRITTO.step(step_index).goal

    def judge(item: dict) -> dict:
        path = ROOT / item["frame"]
        try:
            reading = model.judge(path.read_bytes(), item.get("goal", goal))
        except (PerceptionError, OSError) as exc:
            return {"perception_error": f"{type(exc).__name__}: {exc}"}
        return reading.as_state_fields()

    return judge


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def push(rows: Iterable[dict], name: str = DATASET) -> Any:
    """One Dataset, versioned by Opik, shared by every profile. Deduplication is
    on, so re-running this after adding rows uploads only the new ones."""
    import opik

    ds = opik.Opik().get_or_create_dataset(
        name, description="Labelled pan frames. label_doneness is what a human "
                          "says the pan actually was; see evals/abstention.py.")
    ds.insert(list(rows))
    return ds


def run(profile: Profile, name: str = DATASET, nb_samples: int | None = None) -> Any:
    import opik
    from opik.evaluation import evaluate as opik_evaluate

    ds = opik.Opik().get_or_create_dataset(name)
    return opik_evaluate(
        dataset=ds,
        task=build_task(profile),
        scoring_metrics=[build_metric()],
        experiment_scoring_functions=[build_corpus_scorer()],
        experiment_name=f"mise-{profile.name}",
        experiment_config=profile.as_config(),
        experiment_tags=["abstention", f"profile:{profile.name}",
                         "not-a-result" if _small() else "sized"],
        nb_samples=nb_samples,
        task_threads=1 if profile.backend != "recorded" else 16,
    )


def _small() -> bool:
    return len(load(LABELS)) < CREDIBLE_N


def compare(names: list[str], dataset: str = DATASET) -> None:
    """The ADR-0004 job: same corpus, same metric, two model profiles, one table."""
    cols = ("selective_risk", "coverage", "abstention_precision")
    results = {n: run(PROFILES[n], dataset) for n in names}
    print(f"\n{'profile':<10} " + " ".join(f"{c:>22}" for c in cols))
    for n, r in results.items():
        agg = {s.name: s.value for s in r.experiment_scores}
        print(f"{n:<10} " + " ".join(f"{agg.get(c, float('nan')):>22.3f}" for c in cols))
    for n, r in results.items():
        print(f"{n:<10} {r.experiment_url}")
    print("\nDecide on selective_risk first; coverage only breaks a tie. A profile "
          "that answers more often and is wrong more often is the worse one, and "
          "ADR-0004 spends the residency claim only if `au` clears the bar.")


def enable_otel_tracing() -> bool:
    """Send Strands spans to Opik over OTLP/HTTP.

    Opik's OTLP endpoint is /api/v1/private/otel and the HTTP exporter is
    mandatory - the gRPC one errors. Set OTEL_EXPORTER_OTLP_ENDPOINT to it.

    The wiring itself lives in mise.agents.enable_tracing, next to the graph
    that emits the spans; this is the thin Opik-side check so there is still one
    place to read about Opik.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from mise.agents import enable_tracing
    except ImportError:              # strands not installed; nothing emits spans
        return False
    enable_tracing()
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", nargs="?", default="report",
                   choices=["report", "push", "run", "compare"])
    p.add_argument("profiles", nargs="*", default=["recorded"])
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--labels", type=Path, default=LABELS)
    p.add_argument("--nb-samples", type=int, default=None)
    a = p.parse_args(argv)

    rows = load(a.labels)
    if a.command == "report" or not have_opik():
        if a.command != "report":
            print("opik is not installed - `pip install -e '.[evals]'` to enable it.\n"
                  "The harness below is the same one Opik would wrap.\n", file=sys.stderr)
        print(report(evaluate(rows), rows))
        print(sweep_report(rows))
        return 0

    if a.command == "push":
        push(rows, a.dataset)
        print(f"pushed {len(rows)} rows to dataset {a.dataset!r}")
    elif a.command == "run":
        for n in a.profiles:
            run(PROFILES[n], a.dataset, a.nb_samples)
    elif a.command == "compare":
        compare(a.profiles or ["au", "us"], a.dataset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
