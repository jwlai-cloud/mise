# Devpost "Additional info" — paste-ready answers

One block per form field, in form order. Fields marked **(yours)** are personal declarations only
the submitter can make; a suggestion is given where one is safe to give.

---

**Upload a File** — `mise-technical-pack.zip` (2 MB): the design brief as PDF, the three
architecture diagrams, ARCHITECTURE, the five ADRs, PRODUCT, PRODUCT-FEEDBACK, FRICTION, SPIKE,
SUBMISSION and README, with a `00-START-HERE.txt` index.

**Submitter Type** (yours) — Individual

**Organization Name** — N/A

**Submitter Country of Residence** (yours) — Australia

**Canada province** — N/A

**Primary Track(s)** — Alexa+

**Code repository URL** — https://github.com/jwlai-cloud/mise
(public, Apache-2.0, detected by GitHub in the About section)

**New or existing prior to August 31, 2026?** — New. First commit 2026-09-16.

---

## AWS Builder Mini Challenge

**Submitting?** — Yes

**Which AWS services did you incorporate and how?**

> **Strands Agents SDK — runs.** The perception loop is a real `strands.multiagent` graph
> (strands-agents 1.61): a perception agent, an adversarial critic on a *conditional edge* that
> fires only when confidence is under 0.75 or doneness is near the gate, a risk node running in
> parallel so danger is never gated on perception confidence, and a deterministic arbiter that is
> the single writer to the state cache. It executes in CI against a scripted model provider, so the
> topology is proven by execution order (a clear frame runs `perceive, risk`; a steamed one runs
> `perceive, risk, critique`), with `strands.telemetry` OpenTelemetry spans per node plus a custom
> `mise.frame` span carrying the domain values a trajectory evaluator needs. A Strands
> `BeforeToolCallEvent` steering hook cancels `advance_step` at the tool boundary unless a passing
> observation exists — one of three places the readiness gate is enforced.
> (`src/mise/agents.py`, `src/mise/steering.py`, ADR-0005)
>
> **Amazon Bedrock — written, not yet invoked.** `BedrockVision` (Converse with grammar-constrained
> structured output, `outputConfig.textFormat` / `json_schema`) and `BedrockModel` for the graph.
> Blocked on the account's Anthropic use-case form and an IAM grant — documented in the friction
> log, with the exact missing actions printed by `infra/preflight.py`.
>
> **Bedrock AgentCore — designed and implemented with local fallbacks, not deployed.**
> *Memory* (`userPreferenceMemoryStrategy`, namespace `cook/{actorId}/hob/`) learns per-cook,
> per-hob calibration from corrections like "that was too early". *Policy* expresses the gate as
> four Dogwood rules using `since within` / `count` over session history, evaluated locally by
> `policy.py` until deployed. *Runtime* is the deployment target; the MCP server already matches
> its `0.0.0.0:8000/mcp`, stateless-HTTP contract. IAM policies for deployer and runtime role are
> in `infra/` with a one-paste CloudShell setup and teardown.
>
> Every service is named with the reason for that primitive in `docs/ARCHITECTURE.md`. We have
> been explicit about what ran versus what was designed against; `docs/PRODUCT-FEEDBACK.md`
> marks the same line per service.

---

## Open Source Mini Challenge

The form accepts "a new repo (with open-source license)" created during the window. Mise is one.
If you'd rather not enter, answer **No** and leave the rest blank.

**Submitting?** — Yes

**Contribution URL** — https://github.com/jwlai-cloud/mise

**Project Repository URL** — https://github.com/jwlai-cloud/mise

**GitHub Username** (yours) — jwlai-cloud

**What you did, how it works, why it matters**

> **What:** Mise, a new Apache-2.0 project created during the hackathon window: a self-hosted MCP
> server (MCP Python SDK 2.1, protocol 2025-11-25) where readiness is a *refusable tool contract*.
> A camera watches a pan; an assistant asks `check_doneness` and gets one of four verdicts —
> proceed, wait, refuse ("I can't tell"), or abort ("off the heat").
>
> **How:** two planes joined by one cache. Perception runs on its own clock (a Strands multi-agent
> graph, or a single vision call) and writes a validated `CookState`; the model's own report of
> what obstructs the view caps its confidence in code, so confidence can only fall. MCP tools only
> read the cache and apply a deterministic gate in milliseconds — no model call inside a tool,
> ever. `advance_step` is refused without a recent passing observation, enforced in three places.
> An MCP Apps `ui://` panel polls an app-only tool so the screen keeps the detail after the voice
> turn ends.
>
> **Why it matters:** most assistant integrations answer anyway when they can't see. This is a
> reusable pattern for any MCP tool backed by uncertain perception — refusal as a first-class,
> testable verdict rather than an error path. It runs on a laptop with no credentials (11 test
> suites, a 4-button demo rig), so anyone can fork the contract for a different sensor.

---

**[Optional] Feature Requests**

> 1. **Critical — Alexa+ MCP Toolkit outside the US.** Alexa+ is live to Australian consumers, but
>    the publish path is US-only private preview with no eligibility criteria. We had to simulate
>    the Alexa side.
> 2. **Important — a distinct error code for the unsubmitted Bedrock Anthropic use-case form.** It
>    surfaces as `ResourceNotFoundException`, which reads as a wrong model id and costs an hour.
> 3. **Important — published minimum IAM templates for AgentCore** (deployer and runtime execution
>    role). Today actions are reverse-engineered from AccessDenied one at a time, which pushes
>    everyone to `bedrock-agentcore:*`.
> 4. **Important — a documented, versioned cancellation contract for Strands
>    `BeforeToolCallEvent`.** Our hook tries three attribute names because it differs by version.
> 5. **Nice-to-have — Builder Tools MCP should negotiate protocol 2025-11-25** (the version the
>    Alexa+ track requires) and advertise the Alexa+ docs it already indexes.

**[Optional] Friction Log** — https://github.com/jwlai-cloud/mise/blob/master/docs/FRICTION.md

**[Optional] Project Testing Link** — https://github.com/jwlai-cloud/mise#judges-start-here--60-seconds-no-credentials

**Testing instructions**

> No credentials needed.
> `git clone https://github.com/jwlai-cloud/mise.git && cd mise && python3 -m venv .venv && .venv/bin/pip install -e .`
> `PYTHONPATH=src .venv/bin/python -m uvicorn mise.app:app --port 8000`
> Open http://localhost:8000/dev/control and press 1–4 (one per verdict) while watching
> http://localhost:8000/dev/panel. Press 2: the meter is past the gate but the verdict reads CAN'T
> TELL — a system that guessed would say GO. Real MCP client: `npx @modelcontextprotocol/inspector`
> against http://localhost:8000/mcp (streamable HTTP, spec 2025-11-25).

---

## Feedback questions

**Q1 — Which developer tools, APIs, and SDKs did you use and for what?**

> - **MCP Python SDK 2.1** — the whole server: five tools, streamable HTTP, protocol 2025-11-25.
> - **MCP Apps (`ui://`, SEP-1865)** — the live Echo Show panel; `panel_state` is app-only and polled.
> - **Alexa+ add-ons / MCP Toolkit** — designed against (500 ms tool budget, turn-based); not
>   deployed (US-only preview). The demo simulates the Alexa side and labels it.
> - **Strands Agents SDK** — runs: multi-agent perception graph with a conditional critic, OTEL
>   telemetry; plus a steering hook guarding `advance_step`.
> - **Amazon Bedrock** — written as the perception model; not yet invoked (account entitlement + IAM).
> - **Bedrock AgentCore Memory / Policy / Runtime** — implemented with local fallbacks; not deployed.
> - **AWS CLI / IAM / CloudShell** — capability probing, setup and teardown scripts.
> - **Amazon Devices Builder Tools MCP** — documentation search from a coding agent.
> - Supporting, non-Amazon: Gemini 2.5 Flash (demo perception), Gemini image + TTS (demo assets),
>   Playwright + ffmpeg (recording the demo from the running system), Claude Code (development).

**Q2 — What worked well?**

> - **MCP SDK:** excellent. Pydantic return models keep schema and signature in sync;
>   `streamable_http_app()` is plain Starlette so custom routes mount in three lines; negotiated
>   2025-11-25 first try.
> - **MCP Apps:** `_meta.ui.visibility: ["app"]` is the single most valuable feature in the stack —
>   it gives the screen its own clock on a turn-based voice platform.
> - **Alexa+ docs:** the published 500 ms tool budget shaped the whole architecture — constraints
>   stated up front beat capabilities discovered late.
> - **Strands:** `GraphBuilder` conditional edges are exactly right for a critic that only runs near
>   the decision boundary; an `Agent` drives from a scripted `Model`, so the graph runs in CI.
> - **AgentCore:** Runtime hosting MCP natively at `0.0.0.0:8000/mcp` needed zero server changes;
>   Dogwood's `since within` / `count` is the only way we know to express "advance requires a passing
>   observation in the last 20 s" as policy.
> - **IAM:** denial messages that name the exact action and ARN are the best diagnostic in the stack.

**Q3 — What needs work?**

> - **MCP SDK:** the 1.x→2.x break is silent until import (`mcp>=1.27` resolves to 2.x, where
>   `fastmcp` is gone) and AWS's own AgentCore walkthrough still shows 1.x.
> - **MCP Apps:** CSP is deny-by-default with no error when `connectDomains` is missing; unclear
>   whether hosts return `structuredContent` or text.
> - **Alexa+:** toolkit US-only; OAuth 2.1 without Dynamic Client Registration means spec-pure MCP
>   servers need changes; "Agent Skill" vs "add-on" terminology collision; no camera access for
>   third parties, documented nowhere prominent.
> - **Bedrock:** unsubmitted use-case form surfaces as `ResourceNotFoundException`; model discovery
>   is permissioned separately from invocation; `au.` profiles are 4.5-gen only, documented across
>   several pages.
> - **AgentCore:** two IAM principals needed, quickstart implies one; no minimum deployer policy;
>   namespace trailing-slash rule is a footnote, not a validation error.
> - **Strands:** cancellation attribute differs across versions; hook event shape undocumented.
> - **Builder Tools MCP:** negotiates 2025-03-26 (track requires 2025-11-25); describes itself as
>   Fire TV only; `device_os` filter doesn't filter; refusals return as successful results.

**Q4 — Onboarding (zero to hello world)?**

> - **MCP SDK:** about an hour to a working streamable-HTTP server. Best of the stack.
> - **MCP Apps:** good reference, thin on worked examples for the app-visibility pattern.
> - **Alexa+:** hardest to orient in — terminology collision and the US-only gate.
> - **Strands:** good concepts, thin on what a hook receives; we read source to find the event shape.
> - **Bedrock / AgentCore:** conceptually excellent, operationally blocked — the entitlement form is
>   invisible until a call fails, and IAM actions had to be reverse-engineered.
> - **Builder Tools MCP:** one `npx` command, but nine deprecation warnings, two citing known
>   vulnerabilities in pinned dependencies.

**Q5 — Would you build with these again?**

> Yes. MCP and MCP Apps without reservation — the app-only tool solved a problem we thought was
> unsolvable on a turn-based voice platform. Strands, yes, for the graph and steering; the concept
> is worth the API churn. AgentCore, yes, specifically Memory and Policy, because they do work we
> could not do ourselves. Alexa+, yes — its constraints produced a better architecture than we
> would have designed without them — and immediately if the MCP Toolkit opens outside the US.

---

**Eligibility checkboxes** (yours) — age of majority; eligible jurisdiction; not an employee,
representative or agent of the promotion entities. Only you can attest to these.

**Which AI tools have you leveraged?**

> Claude Code (Claude Opus) for development, code review and documentation. Gemini 2.5 Flash on
> Vertex AI as the perception model for the demo video; Gemini 2.5 Flash Image to generate the demo's
> pan stills (labelled as AI-generated on screen); Gemini-TTS for the demo's voices.

**Level of learning** (yours) — suggested: Significant

**AI value you can use in your career?** (yours) — suggested: Yes
