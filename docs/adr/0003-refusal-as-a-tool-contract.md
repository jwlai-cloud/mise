# 0003 — Refusal as a tool contract, enforced in three places

Status: accepted · 2026-09-15

## Context

ADR-0002 established that the perception layer is prior art and the
differentiation is the *contract*. A contract that exists only as a prompt
instruction ("don't advance unless the pan is ready") is not a contract — the
model can be argued out of it, and a judge will ask exactly that.

## Decision

Enforce the gate at three independent layers, deliberately redundant:

1. **`gate.py`** — deterministic, unit-tested. Returns one of four verdicts;
   `refuse` when frames are stale or confidence is below the step's floor.
2. **Strands steering** (`steering.py`) — a `BeforeToolCallEvent` handler that
   cancels `advance_step` with corrective feedback. The model never reaches the
   tool body.
3. **AgentCore Policy / Dogwood** (`policies/mise.dogwood`) — temporal policies
   conditioned on the agent's own action history within the session.

Redundancy is the point: a judge asking "what stops the model advancing anyway"
gets three answers, one of which is a protocol-level guarantee.

## Consequences

- The local evaluator in `policy.py` mirrors the Dogwood semantics so the rules
  are testable without AWS. **When AgentCore Policy is configured the remote
  decision wins** — the local path is a fallback, not a second opinion.
- Rule 2 (no repeated refusal inside two minutes) changes what the *voice* says
  but not what the *panel* shows. Suppression must never hide a danger state —
  rule 3 exempts `abort` from all rate limiting.
- The abstention threshold is currently too conservative: `evals/abstention.py`
  reports 33% abstention precision on seed labels. Tuning it is measurable work,
  not a bug.

## Rejected

- **Prompt-only enforcement.** AWS's own steering benchmark reports 82.5% for
  prompt-only vs 100% with steering over 600 runs (their six-scenario eval, not
  external). Even discounting the number, a prompt is not a guarantee.
- **Enforcing only in `gate.py`.** Works, but gives no protocol-level story, and
  the protocol-level story *is* the differentiation.
