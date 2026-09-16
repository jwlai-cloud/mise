# Week-one spike — retire the risk before building anything else

Three questions. Nothing else matters until they are answered.

### 1. Does a vision model reliably judge *your* pan? (highest risk)
Not "can it see onions" — can it answer **one** question consistently across lighting,
steam and a moving hand: *are these onions translucent yet?*

- Shoot 3 real cooks on your hob, a frame every 3s, keep the JPEGs.
- Hand-label each frame 0.0–1.0.
- Run the model with structured output matching `CookState`; plot predicted vs labelled.
- **Pass:** monotonic, ±0.15 of your labels, and confidence drops when the view is blocked.
- **Fail:** narrow the question (one dish, one pan, fixed camera position) before widening.

This is also the seed corpus for AgentCore Evaluations. Keep every frame.

### 2. Does the panel render in the Local Inspector?
`npx addon-local-inspector <url>` against `ui://mise/panel`. Confirm it renders in both
device frames, that the 2s poll of `panel_state` works inside the sandbox, and whether
the host returns `structuredContent` or text (the panel handles both — check which).

### 3. Latency budget
Time `check_doneness` end to end under load. It only reads a dict, so it should be
single-digit milliseconds. If it isn't, something is doing work it shouldn't.

## Also this week
- [ ] Apply for Alexa+ MCP Toolkit Private Preview (no published timeline — apply now)
- [ ] Push the repo public with the Apache-2.0 licence already in place
- [ ] Start `docs/FRICTION.md` — worth up to 10% of the score
- [ ] Decide the Open Source mini-challenge artefact (must be **separate** from this repo)
