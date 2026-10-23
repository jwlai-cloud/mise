# The Strands agent graph, run against a real model

Recorded 2026-10-23 by `docs/demo/build_interaction.py` (rehearsal pass), server started with
`MISE_VISION_BACKEND=graph MISE_GRAPH_MODEL=gemini`. Each still in `docs/demo/stills/` was POSTed
to the real `/ingest`; the graph is perceive → critique (conditional) + risk → deterministic
arbiter, with Gemini 2.5 Flash as the model for every agent via Strands' `GeminiModel` provider.
Each frame is judged by a fresh graph against the goal of the step the recipe is on.

| Still | Step goal | Agents that ran | Confidence | Risk | `check_doneness` / `advance_step` |
|---|---|---|---|---|---|
| `f2_soft` | onion: translucent, slumped (gate 0.80) | perceive, risk | 1.00 → 0.95 | none | **wait** — "white and opaque … About 72 seconds" |
| `f3_steam` | onion | perceive, **critique**, risk | 0.00 | none | **refuse**; `advance_step` refused too |
| `f6_onion_done` | onion | perceive, risk | 1.00 → 0.95, doneness 1.00 | none | **proceed**; `advance_step` → step 2, "Add the garlic." |
| *(no new frame yet)* | garlic: pale gold, not browned (0.75) | — | — | — | **refuse** — "I haven't looked at the pan since we moved on." |
| `f7_garlic_in` | garlic | perceive, risk | 1.00 → 0.95, doneness 0.50 | none | **wait** — "a pile of minced garlic in the center … About 10 seconds" |
| `f8_garlic_burn` | garlic | perceive, risk | 1.00 → 0.95 | **urgent** | **abort** — "Take it off the heat …" |

The critic ran on one frame of five: the one where the perception agent could not see. Agent
paths and verdicts were the same across consecutive builds.

**Not a measurement.** Five AI-generated stills, no camera, no labelled corpus. Some generated
stills were rejected because the agents, correctly, would not pass them — a "golden garlic" the
critic said was not golden, onions the generator never actually made translucent. Those were
dropped rather than argued with. Running for real also found four bugs the scripted tests hid;
see FRICTION #11.

Reproduce with your own key:

```bash
pip install -e '.[gemini]'
GEMINI_API_KEY=... MISE_VISION_BACKEND=graph MISE_GRAPH_MODEL=gemini \
  PYTHONPATH=src uvicorn mise.app:app --port 8000
curl -s "localhost:8000/dev/start?step=1" >/dev/null
curl -s --data-binary @docs/demo/stills/f3_steam.jpg localhost:8000/ingest | python3 -m json.tool
```
