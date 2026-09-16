# Week-one spike — retire the risk before building anything else

Three questions. Nothing else matters until they are answered.

### 1. Does a vision model reliably judge *your* pan? (highest risk)
Not "can it see onions" — can it answer **one** question consistently across lighting,
steam and a moving hand: *are these onions translucent yet?*

- Shoot 3 real cooks on your hob, a frame every 3s, keep the JPEGs. **Fixed camera
  position** — a gooseneck clamp. Camera shake is a variable you cannot separate
  from model error when the labels disagree, and you only get three evenings.
- Hand-label each frame 0.0–1.0. **That number is `label_doneness`**, and it is
  the whole point: `evals/abstention.py` judges an abstention by whether the
  estimate was genuinely unreliable (`|doneness − label_doneness| > 0.15`), not
  by whether a noisy guess happened to land on the right side of the gate. A
  ready/not-ready bit is not enough — the harness runs on it but reports it as
  degraded.
- Deliberately shoot the degraded frames too: steam across the lens, a hand in
  the way, the phone knocked. Those are the rows the contract is judged on, and
  a corpus of clean frames cannot measure abstention at all.
- Run the model with structured output matching `CookState`; plot predicted vs labelled.
- **Pass:** monotonic, ±0.15 of your labels, and confidence drops when the view is blocked.
- **Fail:** narrow the question (one dish, one pan, fixed camera position) before widening.

Append each frame to `evals/labels.jsonl` as
`{"doneness":…,"confidence":…,"age":…,"label_doneness":…,"evidence":"…","source":"cook-1"}`
and re-run the eval. Its risk-coverage sweep picks the confidence floor from the
data rather than by feel. Keep every JPEG — it is also the corpus for AgentCore
Evaluations, and ~100 labelled frames is where the percentages stop being a
smoke test.

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
- [ ] Decide the Open Source mini-challenge artefact (must be **separate** from this
      repo — but "contribute to an existing public repository" qualifies, so one
      small upstream PR is enough)
- [ ] Submit the Anthropic use-case form in the Bedrock console. No IAM policy
      works around it, and it gates every model call in every region.
- [ ] Attach `infra/deployer-policy.json` and create the `mise-runtime` execution
      role. The CLI user cannot self-grant.
