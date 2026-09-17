# Mise

**The cooking assistant that tells you to wait.**

Built for the Alexa+ track of *Build, Ship, Shape: Amazon Developer Hackathon* (2026).

Every recipe app pushes you forward through steps. Mise holds you back, because it
can see the pan. Ask *"can I add the garlic yet?"* and it answers
**"Not yet — they're still firm at the edges. About ninety seconds."**

---

## Judges start here — 60 seconds, no credentials

No AWS account, no camera, no model, no API key. Four verdicts, four buttons.

```bash
git clone https://github.com/jwlai-cloud/mise.git && cd mise
python3 -m venv .venv && .venv/bin/pip install -e .
PYTHONPATH=src .venv/bin/python -m uvicorn mise.app:app --port 8000
```

Then open **<http://localhost:8000/dev/control>** and press **1 2 3 4**, watching
**<http://localhost:8000/dev/panel>** beside it.

| Key | What the panel does | Why it matters |
|---|---|---|
| **1** | NOT YET climbing to **GO** | the ordinary case |
| **2** | **CAN'T TELL** — steam on the lens | the meter is *past* the gate marker and it still refuses. A guessing system says GO here |
| **3** | **CAN'T TELL** — frames stopped | the panel dims and counts the seconds since it last saw the pan |
| **4** | **OFF THE HEAT** | overrides the cooldown *and* a confidence too low to judge on |

**Button 2 is the whole submission.** The perception is prior art and we say so
([ADR-0002](docs/adr/0002-positioning-against-prior-art.md)); what does not exist
anywhere else is readiness as a *refusable* tool contract.

### If you want to drive it as a real MCP client

The server is streamable HTTP at `http://localhost:8000/mcp`, spec **2025-11-25**.
A browser will return `406` — that is the protocol requiring an `Accept` header, not a
fault.

```bash
npx @modelcontextprotocol/inspector      # then connect to http://localhost:8000/mcp
```

Call `check_doneness` after pressing a button. `advance_step` will refuse unless a
*passing observation* was made in the last twenty seconds.

### What you cannot try, and why

**Talking to a real Echo.** The Alexa+ MCP Toolkit publish path is a US-only private
preview; the rules permit a simulated experience and this is it. Separately, Alexa's only
camera-facing developer API is the Object Detection Sensor API — an Echo Show will not
hand frames to a third-party server, so the camera is your own phone
([ADR-0002](docs/adr/0002-positioning-against-prior-art.md)).

**A live pan.** `perception.py` is built, validated and tested against a call shape
verified in botocore's service model, but has never been invoked — blocked on an
account-level Bedrock entitlement form and an IAM grant. `docs/PRODUCT-FEEDBACK.md` marks
what runs versus what is only designed, tool by tool.

```bash
python3 tests/test_gate.py tests/test_policy.py tests/test_steering.py \
        tests/test_scenarios.py tests/test_refusal_contract.py \
        tests/test_abstention.py tests/test_ingest.py
```

---

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
frames               10
answered             7  (coverage 70%)
  WRONG              0   <- selective risk 0.0%
abstained            3
  justified          3   (estimate was off by >0.15)
  unnecessary        0
abstention precision 100%

a system that never refused would be wrong 20% of the time
this one is wrong 0.0% of the time, on 70% of frames
```

**The harness refuses to call that a result, and so should you** — ten
hand-written seed rows is a smoke test for the metric, not evidence about the
system. `report()` prints `NOT A RESULT` under 100 frames on purpose.

An abstention is judged against whether the **estimate was actually unreliable**
(`|doneness − label_doneness| > 0.15`), not against whether it would have landed
on the right side of the gate. That distinction is the whole metric. Steam
crosses the lens, confidence collapses to 0.31, and the model still emits
`doneness=0.88`; if that noise happens to be correct, side-of-gate scoring
records the refusal as a mistake — **rewarding luck and penalising calibration**,
on exactly the behaviour this project exists to demonstrate. Rows therefore carry
a continuous `label_doneness`; rows with only the older `label_ready` bit still
run and are reported as degraded.

The eval also prints a risk-coverage sweep over the confidence floor, because
"the threshold is too conservative" is a claim you can only check against a
table:

```
  floor   coverage   risk   abstained  justified
  0.30       80%   12.5%          2          2
  0.35       70%    0.0%          3          3
  0.60       70%    0.0%          3          3  <- current
  0.90       50%    0.0%          5          3
```

On the seed corpus there is a **safe plateau from 0.35 to 0.85** where risk is
0% and coverage is identical; below 0.35 risk jumps to 11–12%. So the current
floor is not costing coverage, and the earlier read that it was "too
conservative" was an artefact of the old scoring. Re-run this against real
labelled frames before trusting any of it.

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
python3 tests/test_abstention.py        # the metric rewards calibration, not luck
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
| `evals/abstention.py` | the **pan** eval — abstention quality, not accuracy |
| `evals/trajectory.py` | the **agent** eval — did the graph take a sane path |
| `evals/opik_pack.py` | optional Opik wrapper for comparing model profiles |
| `src/mise/agents.py` | the hot graph — perception, a conditional critic, risk, arbiter |
| `ui/panel.html` | the live panel; works in an MCP host *and* a plain browser |
| `ui/control.html` | demo remote — one button per verdict, never in the shot |
| `ui/camera.html` | the phone: grab a frame, POST the JPEG, forget it |

## Docs

| File | What it is |
|---|---|
| `CLAUDE.md` | Standing context and invariants for coding sessions |
| `docs/PRODUCT.md` | The problem, who it's for, the edge over prior art, and the non-goals |
| `docs/PROGRESS.md` | **Read first.** State, next actions, open questions |
| `docs/ARCHITECTURE.md` | Current-state system snapshot |
| `docs/adr/` | Decisions, immutable once accepted |
| `docs/SPIKE.md` | The three questions that retire the risk |
| `docs/FRICTION.md` | Friction log — the optional 10% judging bonus |
| `docs/PRODUCT-FEEDBACK.md` | **Required** submission element: the five questions, per tool |
| `docs/SUBMISSION.md` | The Devpost writeup, with a pre-submission checklist |
| `infra/SETUP.md` | AWS setup in four ordered steps; `infra/preflight.py` reports what is blocked |
| `docs/LEARNING.md` | Tech breakdown with primary sources |

Copyright 2026 Junwei Lai. Licensed under the Apache License, Version 2.0 — see
[`LICENSE`](LICENSE).
