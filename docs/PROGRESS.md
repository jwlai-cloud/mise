# Progress log

Newest first. **Read this first in any new session.**

## 2026-09-16 — session 2 (Claude Code)

### Done this session
- **Grilled the project against the real rubric** (fetched from Devpost, not assumed). Four
  equally-weighted criteria; friction log is a 10% bonus; **Product Feedback is mandatory and
  separate from it, and does not exist yet**. Alexa+ simulated-experience path confirmed permitted
  verbatim. Open Source mini challenge confirmed to need an artefact *alongside* the main repo —
  but "or contribute to an existing public repository" makes one small upstream PR enough.
- **Verified the server for real.** Boots, negotiates protocol **2025-11-25**, 5 tools +
  `ui://mise/panel`, driven end to end by a real MCP client over streamable HTTP.
- **Fixed: `pip install -e .` was broken.** `mcp>=1.27` resolved to mcp 2.2.0, which removed
  `mcp.server.fastmcp`. Pinned `<2`; added a `[aws]` extra so the Strands and AgentCore layers are
  actually installable.
- **Fixed the bug that defeated the thesis.** Rule 2's cooldown was keyed on step, not verdict, and
  the suppressed string was "Still not yet." — so a plain `wait` silenced a genuine `refuse` and the
  voice spoke a readiness claim about a frame it had just declined to read. Cooldowns are now per
  verdict. `tests/test_refusal_contract.py` locks it.
- **Fixed rule 4: it was spoken but never wired.** `should_stop_gating` only ever fed a string —
  the assistant promised to hand control back and then kept blocking. Now enforced in the ledger, so
  all three layers inherit it, with abort excluded at both ends and a `risk != "urgent"` carve-out
  added to the Dogwood rule (`forbid` beats `permit`, so without it rule 4 would have forbidden
  blocking an advance over a burning pan).
- **Fixed calibration drift between voice and screen.** One `_live_step()` resolver now serves
  `check_doneness`, `advance_step` and `panel_state`, and returns a copy — mutating the shared
  `Step` in `REGISTRY` had made correctness depend on which tool ran first.
- **Fixed a real staleness bug.** `STORE.write()` stamped `time.time()`, so once `ingest_frame`
  lands a 2-3s vision call would make `is_stale` measure our latency instead of the age of the view.
  It now takes the frame's own timestamp.
- **Built the demo rig.** `ScenarioSource` replaces `SimulatedSource`: four scripted scenarios, seek
  (`&at=`), reset, and an operator remote at `/dev/control`. **All four verdicts are now reachable
  with no model, no camera and no AWS** — previously `refuse` and `abort` were unreachable on the
  only running code path, and the pan pinned at doneness 1.0 forty-five seconds after boot.
- **Built the camera path.** `POST /ingest` (drops frames rather than queueing) and `/dev/camera`,
  a phone page that posts JPEGs at ~0.3 Hz. `ingest_frame` still raises `NotImplementedError`; the
  route returns 501 and says so rather than looking broken.
- **Captured the MVP verification video** (`docs/demo/mvp-verification.mp4`, 47s) plus five panel
  screenshots including the two that never existed: `panel-refuse.png` and `panel-abort.png`.
- Architecture, sequence and agent-topology diagrams in `docs/diagrams/`; design brief in
  `docs/design-brief.html` (published; kept current — v2 after the merge).
- **Repo public and PR #1 merged** — `github.com/jwlai-cloud/mise`, Apache-2.0 detected by
  GitHub, copyright holder named. Ten commits, all preserved (merge commit, not squash:
  a judge may read `git log`). `master` is the default branch.
- **The abstention metric was rewarding luck.** It judged a refusal by whether a noisy
  estimate happened to land on the right side of the gate, which scored the steamed-lens
  and blocked-pan frames — the product's whole point — as mistakes. Now judged on
  `|doneness − label_doneness| > 0.15`, with an always-answer baseline and a risk-coverage
  sweep. **The sweep reversed the plan:** there is a safe plateau from 0.35 to 0.85 where
  risk is 0% and coverage is identical, so the 0.60 floor was never the problem and the
  "too conservative, tune it down" task is cancelled.
- **The real-frame path is built behind a seam.** `perception.py` is the only place a model
  runs; nothing else imports boto3, and the whole ingest path is testable with no
  credentials. Confidence is clamped in code to what the model admitted it could see and
  can only ever fall. A failed call writes nothing — silence is how the system refuses.
  The Bedrock call shape is verified against botocore's own service model (see LEARNING.md).
- **Caught a bug I had introduced hours earlier:** `ScenarioSource` ticks at 1 Hz and was
  started unconditionally, so a real frame would be overwritten within a second — point a
  phone at a real pan and the panel shows the scripted one. Silent, and fatal to the demo.
  First accepted frame now stands the scenario down; arming a scenario takes it back.
- Also fixed from the same review: the `_ingesting` lock was checked before the body read,
  so a second frame queued instead of being dropped.
- Seven test suites green. Clean-venv `pip install -e .` installs and imports.
- `docs/PRODUCT-FEEDBACK.md` written — a **required** submission element that did not exist,
  distinct from the friction log. Friction log now at nine entries; 7-9 are the first about
  tools this project actually uses.
- ADR-0004: region is `AWS_REGION`, not architecture. Develop in the US, decide residency
  from the spike's numbers.

### In progress (not done)
- Nothing half-built. `ingest_frame` remains the one deliberate stub.

### Next (priority order)
0. **Two AWS blockers, both with the account owner, both gating everything else.** The
   Anthropic use-case form (surfaces as `ResourceNotFoundException`, not an auth error;
   no IAM policy works around it) and attaching `infra/deployer-policy.json` plus creating
   the `mise-runtime` execution role (the CLI user cannot self-grant).
1. **`BedrockVision.judge` is written but has never executed** — one `MISE_VISION_BACKEND=bedrock`
   away once the above clears.
2. **The SPIKE** — 3 evenings, hard cap. Narrow to one dish and a fixed
   camera the moment it wobbles. Buy a gooseneck phone mount first; camera shake, not model error,
   is how this fails.
3. **Re-label the abstention corpus** with an independent `label_doneness`. The current metric
   decides whether an abstention was justified by asking the very number it declared untrustworthy,
   and it scores the steam and blocked-lens frames — the product's whole point — as mistakes.
4. **Deploy AgentCore Memory** in ap-southeast-2 and film the session-1-vs-session-3 change. One
   service really deployed beats six planned.
5. **Write the mandatory Product Feedback artefact.** Five named questions per tool used. Distinct
   from `docs/FRICTION.md`, and four of those six entries are about Ring and Vega — tracks not used.
6. The hot Strands graph (perception / critic / risk / arbiter), then video and submission.

### Open questions / blocked on
- **Frame-source design.** A parallel review argued for JSONL scene files over in-Python keyframes,
  sharing a parser with `evals/abstention.py`. Adopted its two substantive wins (the `age`
  passthrough, and seeding on scenario switch); kept keyframes because the eval-corpus-as-demo-tape
  coupling is one the same review then rejected as unsafe. Revisit only if scenarios start
  multiplying.
- Everything still open from session 1: camera source finally decided as **phone browser behind a
  tunnel**; MCP Toolkit Private Preview decision date **3 Oct**; project name undecided.

### Known gaps, recorded rather than hidden
- `risk="watch"` is inert: `gate.py` has no branch for it and the panel never shows it, so
  ambiguous haze routes into a band that does nothing. Either surface it or drop it.
- The confidence clamp cannot catch a model that **misreports** the view. A clear-looking
  frame of a genuinely ambiguous pan carries a 0.95 ceiling, and that is where every wrong
  `proceed` will come from. Only a real labelled corpus will find it.
- The Strands hot graph (perception / critic / risk / arbiter) is designed and diagrammed,
  not built. The seam it would sit behind exists.

### Changed since last entry
- Session 1's "verified end to end" claim corrected in place — see above.

## 2026-09-15 — session 1 (Cowork; handed over to Claude Code)

### Done this session
- Track locked: **Alexa+**. Bee, Ring and Fire TV eliminated with evidence (ADR-0001).
- Originality audit run; vision loop confirmed as prior art; positioning moved to the contract (ADR-0002).
- Scaffold built: state cache, gated recipes, four-verdict gate, FastMCP streamable-HTTP server (5 tools + `ui://` resource), dual-transport panel, simulated vision source.
  *(Corrected 2026-09-16: this entry originally read "verified end to end". It was not. `mcp` was never installed in this tree, so the server had never been booted; `pyproject` also resolved to mcp 2.x, which cannot import it. Verified for real on 16 Sep — see session 2.)*
- AgentCore layer **written, not wired**: Memory calibration with local fallback, four Dogwood temporal policies + local evaluator, Strands steering on `advance_step`, abstention eval harness (ADR-0003). Neither `strands` nor `bedrock_agentcore` was installed or declared, so both degraded silently to local paths.
- Tests passing: `test_gate.py`, `test_policy.py`, `test_steering.py`, `evals/abstention.py`.
- Panel screenshots captured at 768×480 in both states.
- AWS hackathon credits received.

### In progress (not done)
- Nothing is half-built. The scaffold is complete *as a scaffold*; the vision loop is deliberately stubbed.

### Next (priority order)
1. **`vision.py::ingest_frame` — the only unimplemented function.** Everything else is plumbing that already works. Do the SPIKE.md experiment first: 3 real cooks, frame every 3s, hand-label, check the model tracks labels within ±0.15. If it doesn't, narrow to one dish and a fixed camera before widening. *First because the whole project is worthless if perception doesn't hold on a real hob.*
2. **Push the repo public** with the Apache-2.0 licence already in place. Required by the rules; also unblocks the Open Source mini challenge planning.
3. **Tune the abstention threshold** against the labelled frames from step 1. Current seed run: coverage 70%, risk 0%, abstention precision **33%** — too conservative. This is the research-grade contribution, so make it measurable.
4. **Stand up AgentCore Memory for real** in ap-southeast-2 and confirm `backend == "agentcore"`. Then record the session-1-vs-session-3 behaviour change for the video.
5. **Local Inspector check** — `npx addon-local-inspector` against `ui://mise/panel`. Confirm it renders in both device frames and that the 2s poll works inside the sandbox, and note whether the host returns `structuredContent` or text.
6. **Multi-dish choreography** — backwards scheduling so two pans land together. Genuine differentiator (nothing on the market does it), but strictly after 1–3.
7. Demo video (use the `hackathon-demo-video` skill) and submission writeup (`hackathon-submission` skill).

### Open questions / blocked on
- **Camera source not finally decided.** Phone browser is the week-1 choice. Echo Show's own camera via `_meta.ui.permissions` is unverified on Echo Show silicon and probably a dead end — treat phone as the answer unless someone proves otherwise.
- **Alexa+ MCP Toolkit Private Preview — applied? No published timeline.** Decision date **3 Oct**: if access hasn't landed, film the Local Inspector and the simulated web experience. No code changes either way.
- **Open Source mini-challenge artefact undecided.** The rules say "alongside your primary-track submission", so the main repo probably does *not* count on its own. Candidates: extract the gate/abstention logic as a standalone library (it generalises to any event stream), or a PR to an upstream repo.
- **Project name undecided.** Repo is `mise` (from *mise en place*). Alternative: **Not Yet**, which is literally the pitch and more memorable to a judge who doesn't cook. Rename is two minutes; decide before submission.
- **$150 AWS credit form closes 21 October** — two days before the deadline. Credits already received, but confirm nothing further is needed.

### Changed since last entry
- First entry.
