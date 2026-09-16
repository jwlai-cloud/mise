# Architecture — current state

Snapshot of what exists now. Replace, don't append.
Last updated 2026-09-16 (session 2, after the hot graph).

## System

```
 phone / webcam ──frames──▶ HOT GRAPH ──▶ CookState cache ──▶ MCP tools ──▶ Alexa+ (voice)
  ~0.3 Hz, own clock        (agents.py)      state.py          <500ms

        the hot graph, on the slow plane only:

          perceive ──┬──▶ critique ──┐      critique runs ONLY near the gate
                     │  (conditional) │     or under low confidence
                     └──▶ risk ───────┼──▶ arbitrate ──▶ STORE
                        (every frame) │     (deterministic, sole writer)
                                                   │
                                                   ├──▶ ui://mise/panel  (polls panel_state every 2s)
                                                   │
  cook's corrections ──▶ AgentCore Memory ──▶ per-step gate thresholds
                                                   │
  session action history ──▶ Dogwood policies ──▶ may_advance / may_speak_refusal
```

## Components

| Component | File | Responsibility |
|---|---|---|
| State cache | `src/mise/state.py` | Thread-safe last-known-good `CookState`. The boundary between the slow world (vision) and the fast world (tools). Exposes `is_stale`. |
| Recipes | `src/mise/recipes.py` | A recipe is a list of **gates**, not steps. Each step declares `gate_doneness`, `min_confidence`, `typical_seconds`. |
| Gate | `src/mise/gate.py` | Deterministic decision → `proceed` / `wait` / `refuse` / `abort`. No model involved. |
| MCP server | `src/mise/server.py` | FastMCP, streamable HTTP, stateless, JSON responses. Five tools + the `ui://` resource. |
| Panel | `ui/panel.html` | Dual transport: JSON-RPC over `postMessage` in an MCP host, plain fetch in a browser. |
| Vision loop | `src/mise/vision.py` | `ScenarioSource` (scripted keyframes, all four verdicts, no model) and `ingest_frame()` (real frames). Exactly one of them owns `STORE` at a time. |
| Hot graph | `src/mise/agents.py` | The Strands multi-agent loop: perception, a conditional critic that may only lower confidence, a parallel risk node, and a deterministic arbiter that is the single writer. Runs offline against `ScriptedModel`. Emits the `mise.frame` span. See ADR-0005. |
| Perception | `src/mise/perception.py` | The only place a model runs. `ScriptedVision` for offline tests, `BedrockVision` for real frames. Validates every reading and clamps confidence to what the model admitted it could see. |
| Memory | `src/mise/memory.py` | AgentCore Memory (user-preference strategy, namespace `cook/{actorId}/hob/`). Local JSON fallback. |
| Policy | `src/mise/policy.py` | Local mirror of the four Dogwood rules; session ledger of gate observations, refusals, corrections. |
| Steering | `src/mise/steering.py` | Strands `BeforeToolCallEvent` handler guarding `advance_step`. |
| ASGI app | `src/mise/app.py` | `/mcp`, `/ingest`, and the demo rig: `/dev/{state,start,scenario,scenarios,reset,panel,control,camera}`. |
| Demo remote | `ui/control.html` | One button per verdict. Arms a scenario and puts the recipe on the step it is written for. |
| Phone camera | `ui/camera.html` | `getUserMedia` → canvas → JPEG → `POST /ingest` at ~0.3 Hz. No inference on device. |

## MCP surface

| Tool | Visibility | Notes |
|---|---|---|
| `start_recipe` | model | Must be called before `check_doneness`. |
| `check_doneness` | model | The primary tool. Applies the cook's calibrated gate; feeds the policy ledger. |
| `advance_step` | model | Guarded by `guarded_advance()` **and** Strands steering. |
| `record_correction` | model | "too_early" / "too_late" → moves the threshold via Memory. |
| `panel_state` | **app only** (`visibility: ["app"]`) | Polled by the panel every 2s. Invisible to the model. |

Resource: `ui://mise/panel`, mime `text/html;profile=mcp-app`.

## Deployment (planned, not yet done)

- Region **ap-southeast-2**. AgentCore GA there for Runtime, Memory, Gateway, Identity, Policy, Evaluations, Observability.
- Bedrock models: **`au.` cross-region profiles** (Sydney↔Melbourne, data residency, 4.5-generation). `global.*` would give frontier models but no residency guarantee — residency was chosen deliberately and is part of the pitch.
- Runtime hosts the MCP server; Gateway not yet needed (no external APIs to federate).

## Constraints that shaped this

- **Alexa+ tool round-trip ≈ 500ms.** No model call inside a tool, ever.
- **Alexa+ is turn-based.** No proactive push, no long-running tools. Voice cannot interrupt; the panel can.
- **One writer to `STORE` at a time.** The scripted pan ticks at 1 Hz, so leaving it
  running while a camera feeds `/ingest` means the script wins the last write and the
  panel shows a simulated pan with a real one on the hob. The first accepted frame
  stops it; arming a scenario takes it back.
- **A failed model call writes nothing.** Not a low-confidence placeholder, nothing.
  Silence lets the last frame age until the gate refuses on its own, so the failure
  path and the staleness path are the same path. A partial write would carry the
  previous `risk` forward under a fresh timestamp.
- **Confidence can only fall after the model speaks.** `view` and `obstructions` set a
  ceiling that is re-applied in code, because a prompt asking for care is a request and
  a lookup table is a guarantee. It cannot catch a model that misreports the view —
  that is the residual risk, and it is where a wrong `proceed` will come from.
- **Two evals, two objects.** `evals/abstention.py` scores the *pan* over a labelled
  corpus, offline. `evals/trajectory.py` scores the *agent* over real OTEL traces.
  AgentCore Evaluations does the second and cannot do the first — its
  `StartBatchEvaluation` takes CloudWatch log groups, never a corpus.
- **Strands traces mechanics, not meaning.** Its spans carry `gen_ai.*` tokens and
  tool names and none of the domain values, so the graph emits one `mise.frame`
  span with doneness, both confidences, risk and whether it wrote. Without it a
  trajectory evaluator sees the shape of a run and nothing about what it decided.
- **A frame's timestamp is when it was taken, not when it was stored.** `STORE.write()`
  takes `updated_at` so `is_stale` measures the age of the *view*. Stamping the write
  would make a 2-3s vision call look like 2-3s of freshness it never had.
- **Camera frames need a secure context.** `getUserMedia` refuses a LAN address
  outright, so local development runs behind a tunnel; AgentCore Runtime provides
  HTTPS in deployment and the code path is identical.
- **Echo Show will not give a third-party server camera frames.** Alexa's only camera-facing developer API is the Object Detection Sensor API (person/pet/package/vehicle). Own camera required.
- **MCP Toolkit publish path is US-only private preview.** Build and demo are unaffected; see ADR-0001.
