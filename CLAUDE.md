# Mise — project context

Hackathon entry for **Build, Ship, Shape: Amazon Developer Hackathon**, Alexa+ track.
Deadline **2026-10-23 12:00 PDT**. Solo build, evenings, from Perth (UTC+8).

**Read `docs/PROGRESS.md` before doing anything.** It is the resume point.
`docs/PRODUCT.md` is the other half: the problem, the persona, the edge over prior art,
and the non-goals. Check a new feature against its non-goals before building it.

## What this is, in one sentence

A self-hosted MCP server plus a camera watching a pan, where *readiness is a
refusable tool contract* — the assistant tells the cook to **wait**, and can
decline to judge at all when it can't see properly.

## Invariants — do not break these without a new ADR

1. **No model call inside an MCP tool.** Alexa+ budgets ~500ms per tool round-trip.
   The vision loop runs on its own clock and writes to `state.STORE`; tools only read.
2. **`refuse` is a first-class verdict.** Stale frames or low confidence must never
   be resolved by guessing. This is the differentiation; it is not an edge case to
   optimise away.
3. **Danger is never rate-limited or confidence-gated.** `abort` overrides every
   other rule, including the refusal cooldown.
4. **Suppressing the voice must never suppress the panel.** Rule 2 shortens what is
   spoken; the screen always carries the detail.
5. **The gate is enforced in three places** (gate.py, Strands steering, Dogwood
   policy) on purpose. Don't "simplify" by removing a layer — see ADR-0003.
6. **When AgentCore Policy is configured, the remote decision wins.** `policy.py` is
   a fallback and a test harness, not a second opinion.

## Conventions

- Python 3.11+, `src/` layout, run with `PYTHONPATH=src`.
- Everything degrades gracefully without AWS credentials — the project must run on a
  laptop with no config. Check `CALIBRATION.backend` to see which path is live.
- Small commits with messages that read well in `git log`; a judge may read history.
- Update the living docs in the **same session** as the code that made them stale:
  `docs/ARCHITECTURE.md` (current state), `docs/adr/` (immutable decisions),
  `docs/PROGRESS.md` (every session), `docs/LEARNING.md`, `docs/FRICTION.md`.
- `docs/FRICTION.md` is worth up to **10% of the judging score**. Add to it whenever
  a platform wastes your time. Nine entries are banked.
- **Two evals, two objects, not alternatives.** `evals/abstention.py` scores the
  *pan* (one labelled corpus, offline, no AWS). `evals/trajectory.py` scores the
  *agent* (real OTEL traces). AgentCore Evaluations does the second and cannot do
  the first — `StartBatchEvaluation` takes CloudWatch log groups, never a corpus.
- Strands emits only `gen_ai.*` mechanics. The domain values a trajectory
  evaluator needs come from the `mise.frame` span in `agents.py`.
- `docs/SUBMISSION.md` is the Devpost writeup. Sections marked **[SPIKE]** are
  placeholders for perception numbers that do not exist yet — fill or cut them, never
  ship an unearned claim. It ends in a pre-submission checklist.
- `docs/PRODUCT-FEEDBACK.md` is a **required** submission element and a different
  artefact: five named questions per tool, API or SDK actually used. Keep it honest
  about what was run versus only designed against — overstating depth is easier for
  a judge to puncture than admitting a gap.

## Run and test

```bash
pip install -e .          # mcp 2.1.x; the <2.2 ceiling comes from strands-agents 1.56
PYTHONPATH=src uvicorn mise.app:app --port 8000
# MCP:     http://localhost:8000/mcp
# panel:   http://localhost:8000/dev/panel
# control: http://localhost:8000/dev/control   <- four buttons, one per verdict
# camera:  http://localhost:8000/dev/camera    <- needs HTTPS; use a tunnel
# arm:     curl "localhost:8000/dev/scenario?name=steam&at=40"
# reset:   curl "localhost:8000/dev/reset"     <- clears learned calibration

# python runs only the FIRST path it is given — loop, one invocation per suite.
for t in tests/test_*.py; do PYTHONPATH=src python3 "$t" >/dev/null && echo "PASS $t" || echo "FAIL $t"; done
python3 evals/abstention.py
python3 infra/preflight.py   # what is still blocking AWS, by exact IAM action
```

## Already verified — do not re-research

- Alexa+ MCP Toolkit publish path is **US-only private preview**. Entering the track
  does not require it: the rules permit a simulated experience, the organisers point
  at `modelcontextprotocol.io`, and the Local Inspector runs locally.
- **Echo Show will not hand camera frames to a third-party server.** Alexa's only
  camera-facing developer API is the Object Detection Sensor API (person/pet/package/
  vehicle). Use your own camera.
- AgentCore is GA in **ap-southeast-2** for Runtime, Memory, Gateway, Identity,
  Policy, Evaluations, Observability — but it is GA in the US regions too, so Sydney
  was never distinguished by that. No `apac.` Anthropic profile: **`au.`** gives
  residency on 4.5-gen models, `global.*`/`us.*` give frontier without it.
  **Superseded by ADR-0004:** develop in the US, decide residency from the spike's
  numbers. Region is `AWS_REGION`, not architecture.
- **AWS is blocked on two things, neither of them code.** The Anthropic use-case form
  is unsubmitted (surfaces as `ResourceNotFoundException`, not an auth error), and the
  account has no `bedrock-agentcore:*` and no Sydney Bedrock permissions. Policies are
  written and ready in `infra/`; attaching them needs an admin principal.
- `mcp` 2.1 `MCPServer` API: `@mcp.tool(meta=...)`, `@mcp.resource(uri, mime_type=...)`,
  `mcp.streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")`.
  The 1.x name for it does not exist in 2.x — the module is a stub that raises. `meta` populates `_meta`, which is how MCP Apps links
  a tool to its `ui://` panel.
- Both mini challenges are in scope: **AWS Builder** (needs *documented* integrations
  — ARCHITECTURE.md must name each service and why that primitive) and **Open Source**
  (likely needs an artefact *separate* from the main repo).

## Do not rebuild / do not claim

- The vision loop is **prior art** — Fullerton IEEE IRI 2025, CamCook, GE Kitchen Hub,
  Samsung AI Vision. Cite it openly; position on the contract. See ADR-0002.
- Never use the phrase "are those onions translucent enough" — it is CamCook's
  marketing copy almost verbatim.
- Don't claim the system stops anyone from cooking unsafely, and **don't make health
  claims** — Ring's content policy precedent suggests Amazon rejects those outright.

## Grill agenda — what to attack in Claude Code

Use the `hackathon-brainstorm` skill's grill mode (say "grill me"). Start here:

1. **The coding-agent comparison.** What does this do that a generic VLM loop with a
   prompt couldn't? If the answer is only "the contract", is the contract *visible*
   to a judge in three minutes, or does it need explaining?
2. **The abstention metric.** *Answered — the metric was measuring the wrong thing.*
   It scored a lucky estimate as a reason the refusal was unnecessary, marking the
   steamed-lens and blocked-pan frames as mistakes. Now judged on
   `|doneness − label_doneness| > 0.15`. The live question is different: every
   threshold in the system is an unmeasured guess, and only labelled frames move
   them. See `docs/SPIKE.md`.
3. **Demo failure.** If the vision model misjudges live in front of a judge, what
   happens? Is there a pre-recorded fallback, and does using one undermine the pitch?
4. **The multi-dish claim.** It's the strongest remaining differentiator and it is not
   built. Does it fit in the time left, or should it be cut from the pitch?
5. **Rubric fit, line by line.** Tech Implementation / Design / Potential Impact /
   Quality of the Idea are equally weighted. Design is 25% and the only design asset
   is one panel — is that enough?
6. **Scope.** What gets cut if there are three weeks left instead of five?
