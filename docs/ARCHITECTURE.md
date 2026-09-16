# Architecture — current state

Snapshot of what exists now. Replace, don't append.
Last updated 2026-09-15.

## System

```
 phone / webcam ──frames──▶ vision loop ──▶ CookState cache ──▶ MCP tools ──▶ Alexa+ (voice)
  ~0.3 Hz, own clock         (slow, async)     state.py          <500ms
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
| Vision loop | `src/mise/vision.py` | `SimulatedSource` today. `ingest_frame()` is the one unimplemented function. |
| Memory | `src/mise/memory.py` | AgentCore Memory (user-preference strategy, namespace `cook/{actorId}/hob/`). Local JSON fallback. |
| Policy | `src/mise/policy.py` | Local mirror of the four Dogwood rules; session ledger of gate observations, refusals, corrections. |
| Steering | `src/mise/steering.py` | Strands `BeforeToolCallEvent` handler guarding `advance_step`. |
| ASGI app | `src/mise/app.py` | `/mcp` + `/dev/state` + `/dev/panel` + `/dev/start`. |

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
- **Echo Show will not give a third-party server camera frames.** Alexa's only camera-facing developer API is the Object Detection Sensor API (person/pet/package/vehicle). Own camera required.
- **MCP Toolkit publish path is US-only private preview.** Build and demo are unaffected; see ADR-0001.
