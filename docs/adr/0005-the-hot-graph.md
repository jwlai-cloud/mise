# 0005 — The hot graph: a multi-agent loop on the slow plane

Status: accepted · 2026-09-16

## Context

ADR-0001 fixed the shape: no model call inside an MCP tool, because Alexa+
budgets ~500ms per tool round-trip. That decision is what makes a genuinely
agentic design *possible* rather than impossible — the agent runs on its own
clock and writes a cache; the tools read it.

But for several sessions the agent existed only as a diagram. The stated reason
was that the account has no Bedrock access. That reason did not survive
inspection: `ScriptedVision` already let the perception path be tested with no
credentials, and the same idea had simply not been applied to the agent. "There
is nothing to trace" was circular — nothing emitted traces because the thing
that emits them was unbuilt.

## Decision

Build the hot graph with `strands.multiagent.GraphBuilder`, and make it runnable
offline so its structure is executed by tests rather than asserted about.

```
frame ──▶ perceive ──┬──▶ critique ──┐
                     │  (conditional) │
                     └──▶ risk ───────┼──▶ arbitrate ──▶ STORE
                        (every tick)  │   (deterministic)
```

### Each node earns its place

A node is justified by a distinct **trigger**, **model tier**, or **failure
domain**. Anything else is a function wearing a costume, and a judge will say so.

- **`perceive`** — every frame; the only node that must call a vision model.
- **`critique`** — a **conditional edge**, traversed only when confidence is
  below 0.75 or doneness is within 0.1 of the gate. It is asked to *refute*, not
  to agree, and its dissent may only lower confidence. This is the node that
  earns the multi-agent claim: a second opinion everywhere would be cost with no
  information, and a second opinion nowhere is the contract unenforced.
- **`risk`** — every frame, **parallel** to the critic rather than downstream of
  it. Danger must never be gated on a confidence the perception agent chose
  (invariant 3). Downstream placement would have made it exactly that.
- **`arbitrate`** — deliberately **not an agent**. A deterministic merge and the
  single writer, so the write path stays unit-testable with no model in it.

### Offline by construction

A Strands `Agent` runs against a scripted `Model` provider with no network. The
catch, found by spiking rather than reading: `structured_output_model` forces a
**tool call**, so the fake must emit a `toolUse` block — a text block is rejected
as a failure to comply.

That makes the topology, the conditional edge and the arbiter genuinely
executable in CI. `GraphVision` then wears the existing `VisionModel` interface,
so `MISE_VISION_BACKEND=graph` substitutes the whole graph for one model call and
nothing downstream changes — validation, shutter timestamping and
drop-on-failure are already tested.

## Consequences

- **The failure rule is unchanged and now covers more.** Any failure writes
  *nothing*: the last frame ages until the gate refuses on its own. A partial
  write would carry the previous `risk` forward under a fresh timestamp.
- **Cost scales with the conditional edge, not with frames.** A clear mid-step
  frame pays for two calls; only frames near the decision boundary pay for three.
- **Tracing became real, and then exposed a gap.** Strands emits OpenTelemetry
  for graph nodes, but only `gen_ai.*` mechanics — tokens, tool names, agent
  names. None of the domain values. A trajectory evaluator could see the *shape*
  of a run and none of its *meaning*, so the graph emits one `mise.frame` span
  carrying doneness, both confidences, risk and whether it wrote. See ADR-0006
  territory if that span ever needs a schema.
- **The critic's trigger thresholds are guesses.** 0.75 and 0.1 were chosen
  against the 0.6 step floor, not measured. They are calibration knobs for the
  spike, like the ceiling table in `perception.py`.
- **`strands-agents` caps `mcp<2.2`**, which is why the project sits on mcp 2.1
  rather than 2.2.

## Rejected

- **A Swarm instead of a Graph.** Autonomous handoff makes cost and latency
  unpredictable on a loop that runs every few seconds. `GraphBuilder` gives
  deterministic order with conditional traversal, which is exactly and only what
  the critic needs.
- **Making the arbiter an agent.** Tempting for symmetry. It would put a model in
  the one place whose correctness the whole contract rests on, and make the write
  path untestable without a model.
- **Faking Strands' `Model` protocol as the production path.** `ScriptedModel` is
  a test double. It is also the honest demo fallback, because it is the *same*
  code path — but it is never a way to claim the agent ran when it did not.
- **Building the graph only once AWS unblocks.** This was the actual prior
  decision, by default rather than deliberately, and it was wrong: it made the
  central claim of the project unverifiable for weeks at no benefit.
