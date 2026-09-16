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
anywhere is readiness as a refusable tool contract.** That contract is designed
to be enforced in three places, on purpose — but be clear about which of the
three run today:

| Layer | File | What it guarantees | Status |
|---|---|---|---|
| **The gate itself** | `src/mise/gate.py` | Deterministic, unit-tested, and willing to return `refuse` | **runs** |
| **Session policy** | `src/mise/policy.py` | The four rules, evaluated locally against the agent's own action history | **runs** |
| **Strands steering** | `src/mise/steering.py` | `advance_step` cancelled at the tool boundary, so the model cannot talk its way past the gate | needs `pip install -e '.[aws]'` |
| **AgentCore Policy** (Dogwood temporal) | `policies/mise.dogwood` | The same four rules as deployable policy — `formerly within`, `count … since within` | **expressed, not yet deployed** |

`policy.py` mirrors the Dogwood semantics so the contract holds, and is testable,
with or without AWS reachable. When AgentCore Policy is configured the remote
decision wins; the local evaluator is the fallback, not a second opinion.

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

**Read that honestly: it is a smoke test, not a result.** The inputs are ten
hand-written rows, so the abstention denominator is three and one row moves the
figure by 33 points. The headline worth quoting today is the other one — **risk
0% at 70% coverage**: over those frames it never gave a wrong readiness answer,
and it was still willing to answer seven times in ten.

The metric also needs fixing, not just more rows. It currently decides whether
an abstention was justified by asking what `doneness` would have said — the very
number the system had just declared untrustworthy. The corpus needs an
independent `label_doneness` before any of this counts as evidence. Calibrated
abstention under degraded perception is an open problem with no consumer
implementations, and that is the research-grade part.

## The four policy rules

1. **Advancing requires a passing gate observed in the last 20 seconds** — not the model's belief, an actual recent observation.
2. **No repeating the same refusal inside two minutes** — every incumbent nags; a muted coach can't warn you when it matters. Cooldowns are keyed per verdict, so a repeated "Still not yet." never spends the budget a genuine "I still can't tell." needs. The panel always keeps the detail.
3. **Danger is never rate-limited and never gated on confidence.**
4. **Three corrections on one step means the threshold is wrong, not the cook** — stop blocking and hand control back. It stops *blocking*; it never starts claiming. The voice still says "not yet" or "I can't tell", with "but it's your call on this step" appended. Danger still overrides it.

## Run it

```bash
pip install -e .
PYTHONPATH=src uvicorn mise.app:app --port 8000
```

- MCP endpoint: `http://localhost:8000/mcp` (streamable HTTP, spec 2025-11-25)
- Panel: `http://localhost:8000/dev/panel`
- **Demo control: `http://localhost:8000/dev/control`** — four buttons, one per verdict
- Phone camera: `http://localhost:8000/dev/camera` (needs HTTPS — see below)

### Driving the demo

A scripted pan drives the state until the vision model is wired, so **all four
verdicts are reachable today with no model, no camera and no AWS**:

```bash
curl "localhost:8000/dev/scenario?name=clean_run"   # NOT YET -> GO
curl "localhost:8000/dev/scenario?name=steam"       # CAN'T TELL: past the gate, lens steamed
curl "localhost:8000/dev/scenario?name=blocked"     # CAN'T TELL: frames stopped
curl "localhost:8000/dev/scenario?name=catches"     # OFF THE HEAT
curl "localhost:8000/dev/scenario?name=steam&at=40" # seek straight to the interesting beat
curl "localhost:8000/dev/reset"                     # clear learned calibration between takes
```

The camera page is a phone browser posting JPEGs to `/ingest` at ~0.3 Hz. It needs
a secure context — a LAN address is refused outright, so tunnel it:
`cloudflared tunnel --url http://localhost:8000`.

```bash
python3 tests/test_gate.py              # the decision logic
python3 tests/test_policy.py            # the four policy rules
python3 tests/test_steering.py          # the tool-boundary gate
python3 tests/test_scenarios.py         # all four verdicts are reachable
python3 tests/test_refusal_contract.py  # a refusal is never spoken as a wait
python3 evals/abstention.py             # abstention quality over labelled frames
```

## Layout

| Path | What it is |
|---|---|
| `src/mise/state.py` | the cache — the boundary between the slow and fast worlds |
| `src/mise/recipes.py` | a recipe is a list of **gates**, not steps |
| `src/mise/gate.py` | the judgement, including the refusal path |
| `src/mise/server.py` | MCP server: tools + the `ui://mise/panel` resource |
| `src/mise/vision.py` | the slow loop — scripted scenarios today, model in week 1 |
| `src/mise/app.py` | ASGI: `/mcp` plus dev routes |
| `src/mise/memory.py` | AgentCore Memory — per-cook, per-hob calibration |
| `src/mise/policy.py` | the refusal contract, locally evaluable |
| `src/mise/steering.py` | Strands steering at the tool boundary |
| `policies/mise.dogwood` | the Dogwood temporal policy source |
| `evals/abstention.py` | abstention quality, not accuracy |
| `ui/panel.html` | the live panel; works in an MCP host *and* a plain browser |
| `ui/control.html` | demo remote — one button per verdict, never in the shot |
| `ui/camera.html` | the phone: grab a frame, POST the JPEG, forget it |

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
