# Mise — project context

Hackathon entry for **Build, Ship, Shape: Amazon Developer Hackathon**, Alexa+ track.
Deadline **2026-10-23 12:00 PDT**. Solo build, evenings, from Perth (UTC+8).

**Read `docs/PROGRESS.md` before doing anything.** It is the resume point.

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
  a platform wastes your time. Six entries are already banked.

## Run and test

```bash
pip install -e .
PYTHONPATH=src uvicorn mise.app:app --port 8000
# MCP:   http://localhost:8000/mcp
# panel: http://localhost:8000/dev/panel
# start: curl "localhost:8000/dev/start?slug=soffritto&step=1"

python3 tests/test_gate.py tests/test_policy.py tests/test_steering.py
python3 evals/abstention.py
```

## Already verified — do not re-research

- Alexa+ MCP Toolkit publish path is **US-only private preview**. Entering the track
  does not require it: the rules permit a simulated experience, the organisers point
  at `modelcontextprotocol.io`, and the Local Inspector runs locally.
- **Echo Show will not hand camera frames to a third-party server.** Alexa's only
  camera-facing developer API is the Object Detection Sensor API (person/pet/package/
  vehicle). Use your own camera.
- AgentCore is GA in **ap-southeast-2** for Runtime, Memory, Gateway, Identity,
  Policy, Evaluations, Observability. No `apac.` Anthropic profile — use **`au.`**
  (residency, 4.5-gen) rather than `global.*` (frontier, no residency). Residency was
  a deliberate choice and is part of the pitch.
- `mcp` 1.27 `FastMCP` API: `@mcp.tool(meta=...)`, `@mcp.resource(uri, mime_type=...)`,
  `mcp.streamable_http_app()`. `meta` populates `_meta`, which is how MCP Apps links
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
2. **The abstention metric.** 33% abstention precision is currently bad. Is the
   metric right, or is it measuring the wrong thing?
3. **Demo failure.** If the vision model misjudges live in front of a judge, what
   happens? Is there a pre-recorded fallback, and does using one undermine the pitch?
4. **The multi-dish claim.** It's the strongest remaining differentiator and it is not
   built. Does it fit in the time left, or should it be cut from the pitch?
5. **Rubric fit, line by line.** Tech Implementation / Design / Potential Impact /
   Quality of the Idea are equally weighted. Design is 25% and the only design asset
   is one panel — is that enough?
6. **Scope.** What gets cut if there are three weeks left instead of five?
