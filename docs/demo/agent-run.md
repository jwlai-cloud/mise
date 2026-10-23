# The Strands agent graph, run against a real model

Recorded 2026-10-23 by `docs/demo/build_interaction.py` (rehearsal pass), server started with
`MISE_VISION_BACKEND=graph MISE_GRAPH_MODEL=gemini`. Each still in `docs/demo/stills/` was POSTed
to the real `/ingest`; the graph is perceive → critique (conditional) + risk → deterministic
arbiter, with Gemini 2.5 Flash as the model for every agent via Strands' `GeminiModel` provider.

| Still | Agents that ran | Perceive confidence → after arbiter | Risk | Verdict from `check_doneness` |
|---|---|---|---|---|
| `f2_soft` (raw onion, clear) | perceive, risk | 1.00 → 0.95 (view clamp) | none | **wait** — "white and opaque … About 72 seconds" |
| `f3_steam` (steam over lens) | perceive, **critique**, risk | 0.00 → 0.00 | none | **refuse** — "the view isn't clear enough for me to judge that" |
| `f4b_done` (nearly there) | perceive, risk | 1.00 → 0.95 | none | **wait** (spoken short: "Still not yet.") |
| `f5_smoke` (smoke, flame) | perceive, risk | 1.00 → 0.95 | **urgent** | **abort** — "Take it off the heat …" |

The critic ran on exactly one frame: the one where the perception agent could not see. Three
consecutive builds gave the same agent paths and verdicts.

**Not a measurement.** Four AI-generated stills, no camera, no labelled corpus. Before the output
schema described each number, the same graph read the clear raw-onion frame as confidence 0.1
and refused it — the model had put doneness in the confidence field. That is in the friction log.

Reproduce with your own key:

```bash
pip install -e '.[gemini]'
GEMINI_API_KEY=... MISE_VISION_BACKEND=graph MISE_GRAPH_MODEL=gemini \
  PYTHONPATH=src uvicorn mise.app:app --port 8000
curl -s localhost:8000/dev/start?step=1 >/dev/null
curl -s --data-binary @docs/demo/stills/f3_steam.jpg localhost:8000/ingest | python3 -m json.tool
```
