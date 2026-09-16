# Mise

**The cooking assistant that tells you to wait.**

Built for the Alexa+ track of *Build, Ship, Shape: Amazon Developer Hackathon* (2026).

Every recipe app pushes you forward through steps. Mise holds you back, because it
can see the pan. Ask *"can I add the garlic yet?"* and it answers
**"Not yet — they're still firm at the edges. About ninety seconds."**

## How it works

```
  phone camera ──frames──▶ vision loop ──▶ CookState cache ──▶ MCP tools ──▶ Alexa+
   (own clock, ~0.3Hz)      (slow, async)     (state.py)        (<500ms)      (voice)
                                                   │
                                                   └──▶ ui:// panel (polls 2s, stays live)
```

The single load-bearing decision: **no tool call ever waits on a vision model.**
Alexa+ allows roughly 500ms per tool round-trip. A vision model does not fit in
that budget and never will — so the model runs continuously on its own clock and
writes to a cache, and tools only ever read the cache.

The second: **voice is turn-based, the panel is not.** Alexa+ cannot interrupt you
to say "that's catching." But an MCP App panel marked `visibility: ["app"]` can be
polled on an interval and keeps rendering after the voice turn ends — so the screen
can shout while your hands are covered in flour.

## Four verdicts, and the third one is the product

| Verdict | Meaning |
|---|---|
| `proceed` | the gate is met |
| `wait` | not met — with the evidence, and roughly how long |
| **`refuse`** | **frames are stale or confidence is low, so it will not guess** |
| `abort` | something is catching; overrides everything, never gated on confidence |

## AgentCore — where the differentiation lives

The vision loop is not the innovation; camera-gated cooking is published work
(Fullerton, IEEE IRI 2025) and shipping marketing copy. **What does not exist
anywhere is readiness as a refusable tool contract.** That contract is enforced
in three places, on purpose:

| Layer | File | What it guarantees |
|---|---|---|
| **AgentCore Policy** (Dogwood temporal) | `policies/mise.dogwood` | Decisions conditioned on the agent's own action history this session — `formerly within`, `count … since within` |
| **Strands steering** | `src/mise/steering.py` | `advance_step` is cancelled at the tool boundary, so the model cannot talk its way past the gate |
| **The gate itself** | `src/mise/gate.py` | Deterministic, unit-tested, and willing to return `refuse` |

**AgentCore Memory** (`src/mise/memory.py`) does the other half: it learns what
*you* mean by translucent on *your* hob, from you saying "that was too early."
Samsung and GE calibrate to the appliance they sold you; nobody calibrates to
your pan. Falls back to a local JSON file when AWS isn't configured, so the
project runs with no credentials.

**AgentCore Evaluations** (`evals/abstention.py`) measures the thing that
actually matters — not accuracy, but whether it declines *exactly* when its
perception is unreliable:

```
frames              10
answered             7  (coverage 70%)
  WRONG              0   <- risk 0.0%
abstained            3
  justified          1
  unnecessary        2
abstention precision 33%
```

That 33% is honest and useful: the abstention threshold is currently too
conservative. Tuning it against real labelled frames is measurable progress, and
it's the research-grade part — calibrated abstention under degraded perception
is an open problem with no consumer implementations.

## The four policy rules

1. **Advancing requires a passing gate observed in the last 20 seconds** — not the model's belief, an actual recent observation.
2. **No repeating the same refusal inside two minutes** — every incumbent nags; a muted coach can't warn you when it matters. The voice shortens to "Still not yet."; the panel keeps the detail.
3. **Danger is never rate-limited and never gated on confidence.**
4. **Three corrections on one step means the threshold is wrong, not the cook** — stop gating and hand control back.

## Run it

```bash
pip install -e .
PYTHONPATH=src uvicorn mise.app:app --port 8000
```

- MCP endpoint: `http://localhost:8000/mcp` (streamable HTTP, spec 2025-11-25)
- Panel in a plain browser: `http://localhost:8000/dev/panel`
- Start a recipe: `curl "localhost:8000/dev/start?slug=soffritto&step=1"`

A simulated pan drives the state until the vision model is wired, so the panel and
the demo work today.

```bash
python3 tests/test_gate.py       # the decision logic
python3 tests/test_policy.py     # the four policy rules
python3 tests/test_steering.py   # the tool-boundary gate
python3 evals/abstention.py      # abstention quality over labelled frames
```

## Layout

| Path | What it is |
|---|---|
| `src/mise/state.py` | the cache — the boundary between the slow and fast worlds |
| `src/mise/recipes.py` | a recipe is a list of **gates**, not steps |
| `src/mise/gate.py` | the judgement, including the refusal path |
| `src/mise/server.py` | MCP server: tools + the `ui://mise/panel` resource |
| `src/mise/vision.py` | the slow loop (simulated today, model in week 1) |
| `src/mise/app.py` | ASGI: `/mcp` plus dev routes |
| `src/mise/memory.py` | AgentCore Memory — per-cook, per-hob calibration |
| `src/mise/policy.py` | the refusal contract, locally evaluable |
| `src/mise/steering.py` | Strands steering at the tool boundary |
| `policies/mise.dogwood` | the Dogwood temporal policy source |
| `evals/abstention.py` | abstention quality, not accuracy |
| `ui/panel.html` | the live panel; works in an MCP host *and* a plain browser |

## Docs

| File | What it is |
|---|---|
| `CLAUDE.md` | Standing context and invariants for coding sessions |
| `docs/PROGRESS.md` | **Read first.** State, next actions, open questions |
| `docs/ARCHITECTURE.md` | Current-state system snapshot |
| `docs/adr/` | Decisions, immutable once accepted |
| `docs/SPIKE.md` | The three questions that retire the risk |
| `docs/FRICTION.md` | Friction log — worth up to 10% of the score |
| `docs/LEARNING.md` | Tech breakdown with primary sources |

Licensed Apache-2.0.
