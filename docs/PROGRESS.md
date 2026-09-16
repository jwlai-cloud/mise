# Progress log

Newest first. **Read this first in any new session.**

## 2026-09-15 — session 1 (Cowork; handed over to Claude Code)

### Done this session
- Track locked: **Alexa+**. Bee, Ring and Fire TV eliminated with evidence (ADR-0001).
- Originality audit run; vision loop confirmed as prior art; positioning moved to the contract (ADR-0002).
- Scaffold built and verified end to end: state cache, gated recipes, four-verdict gate, FastMCP streamable-HTTP server (5 tools + `ui://` resource), dual-transport panel, simulated vision source.
- AgentCore layer wired: Memory calibration with local fallback, four Dogwood temporal policies + local evaluator, Strands steering on `advance_step`, abstention eval harness (ADR-0003).
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
