# 0004 — Develop in the US, decide residency after the spike

Status: accepted · 2026-09-16 · Amends the region choice in ADR-0001

## Context

ADR-0001 chose **ap-southeast-2** with `au.` cross-region inference profiles, on
two grounds: AgentCore is GA in Sydney, and `au.` gives data residency, which it
called "a deliberate choice and part of the pitch."

The first ground does not survive scrutiny — AgentCore is GA in the US regions
too, so it never distinguished Sydney. The second is real, but it has a cost
ADR-0001 did not state: **`au.` profiles are 4.5-generation only.** Frontier
models are reachable through `global.*` or `us.*` and not through `au.*`.

Probing the account on 2026-09-16 changed the picture again:

- `bedrock:InvokeModel` in **us-east-1 is permitted** — a `Converse` call got past
  IAM and failed on the Anthropic use-case form instead.
- The same call in **ap-southeast-2 is denied at IAM**, as is every
  `bedrock-agentcore:*` action in that region.
- `bedrock:ListFoundationModels` is denied in both, so the available model list
  could not be enumerated at all.

So the region that the architecture targets is the region with strictly less
access, and the residency pitch is currently being paid for with model capability
on the one component whose accuracy is entirely unvalidated. `vision.py::ingest_frame`
has never run against any model.

## Decision

**Develop and run the week-one spike in a US region against the best available
model. Choose the deployment region afterwards, from the spike's evidence.**

Region is already configuration, not architecture — `memory.py` reads
`os.getenv("AWS_REGION", "ap-southeast-2")` and nothing else hardcodes it — so
the switching cost is an environment variable, not a refactor.

The spike answers *"can a vision model judge this pan to ±0.15?"* That is not a
region question, and answering it must not be blocked on an IAM grant and a
residency preference.

- **If `au.` 4.5-generation models clear the SPIKE.md bar**, deploy to
  ap-southeast-2 and keep the residency claim — now supported by measurement
  rather than assertion.
- **If they do not**, deploy where the perception works, and drop the residency
  line from the pitch rather than the accuracy from the product.

## Consequences

- The `au.` vs `global.*` trade in ADR-0001 stands as analysis but is no longer a
  precondition. Its conclusion is deferred, not reversed.
- Residency remains a genuinely good consumer argument for a camera in someone's
  kitchen, and ADR-0002 notes the impact story is otherwise thin. It is worth
  keeping **if earned**. It is not worth losing the project over.
- The spike must record which model and region produced its numbers, or the
  comparison that decides this cannot be made.
- Two blockers are unaffected by any region choice and both sit with the account
  owner: the Anthropic use-case form (no IAM policy works around it) and the
  deployer/runtime IAM roles in `infra/`.
- Nothing about the demo changes. All four verdicts are reachable with no
  credentials in any region, via the scripted scenarios in `vision.py`.

## Rejected

- **Staying in ap-southeast-2 regardless.** Defensible only if residency is a
  requirement. It is a pitch line, and a pitch line should not pick the model
  tier for an unvalidated perception layer.
- **Moving to the US permanently, now.** Premature in the other direction. If the
  4.5-generation models are good enough, residency is free differentiation on a
  rubric where Potential Impact is 25% and the current impact story is thin.
- **Running the spike against a non-AWS vision API to dodge the blockers.**
  Faster, and it would answer the perception question — but the AWS Builder mini
  challenge wants documented AWS integrations, and a spike whose numbers came
  from elsewhere cannot be quoted for the model actually shipped.
