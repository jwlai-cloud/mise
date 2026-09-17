# Product feedback

A **required** submission element, and distinct from `docs/FRICTION.md` — the friction log is the
optional 10% bonus and records specific incidents; this answers the five questions the rules ask
about every tool, API and SDK used.

Each section says what we actually did with the thing. Where we designed against something but
never ran it, it says so. A submission that overstates its depth is easier to puncture than one
that is precise about it.

---

## MCP Python SDK — `mcp` 2.1 (`MCPServer`)

**What we used it for.** The whole server surface: five tools, a `ui://` resource, streamable
HTTP, `stateless_http=True`, `json_response=True`. This is the project's required technology and
the only SDK that runs in every code path we ship.

**What worked well.** Genuinely excellent. Decorator-per-tool with Pydantic return models meant the
tool schema and the Python signature could not drift. `mcp.streamable_http_app()` returns a plain
Starlette app, so mounting our own routes beside `/mcp` was three lines rather than a fight. We
verified a real client round-trip end to end and the server negotiated protocol **2025-11-25**
first try.

**What needs work.**

- **The 1.x → 2.x break is silent until import.** `mcp>=1.27` in a manifest resolves to 2.x,
  where `mcp.server.fastmcp` no longer exists (`FastMCP` became `MCPServer`). Our own README
  instructions failed on a clean clone until we noticed. We capped, then migrated: the project
  now runs `MCPServer` on 2.1, with `stateless_http` and `json_response` moved off the
  constructor onto `streamable_http_app()`, and `host="0.0.0.0"` newly load-bearing because 2.x
  defaults to 127.0.0.1 and AgentCore Runtime expects 0.0.0.0:8000. The `<2.2` ceiling is
  imposed by strands-agents 1.56, not by us. The runtime error is
  clear and links the migration guide, which is good — but every tutorial, and AWS's own AgentCore
  MCP walkthrough, still shows the 1.x import, so new projects will keep resolving to a version
  their copied code cannot run. **A deprecation shim, or a louder note on the 1.x docs, would save
  a lot of first hours.**
- **`LATEST_PROTOCOL_VERSION` is `2025-11-25` but `DEFAULT_NEGOTIATED_VERSION` is `2025-03-26`.**
  Defensible, and negotiation does reach the newer version — but when a hackathon track requires a
  minimum spec version, the safe-default constant reads like a failure until you test it.

**Onboarding.** An hour from nothing to a working streamable-HTTP server. The best of the stack.

**Would we build with it again.** Yes, without reservation.

---

## MCP Apps — `ui://` resources (SEP-1865)

**What we used it for.** The live panel. A `ui://mise/panel` resource with mime
`text/html;profile=mcp-app`, linked from each tool via `_meta.ui.resourceUri`, plus a
`panel_state` tool marked `_meta.ui.visibility: ["app"]` that the page polls every two seconds.

**What worked well.** `visibility: ["app"]` is the most valuable single feature we found anywhere
in this stack, and it solved a problem we thought was unsolvable. Alexa+ is turn-based and cannot
interrupt the cook, so a warning that arrives after the voice turn has nowhere to go. An app-only
tool plus `setInterval` gives the screen its own clock while keeping that tool invisible to the
model. Being able to write a real HTML page rather than fill in a card format meant the panel could
be designed rather than configured.

**What needs work.** The extension is young and it shows in the places you find late: CSP is
deny-by-default, so `_meta.ui.csp.connectDomains` has to be declared or the page silently gets
`default-src 'none'` with no error explaining why. We also could not determine from the docs whether
a given host returns `structuredContent` or a text block from `tools/call`, so our panel handles
both defensively — a stated contract would remove that guesswork.

**Onboarding.** Good reference material, thin on worked examples for the app-visibility pattern
specifically, which deserves a tutorial of its own given how much it unlocks.

**Would we build with it again.** Yes. This is the part of the submission we would keep first.

---

## Alexa+ add-ons / MCP Toolkit

**What we used it for.** Designed against, not deployed — the publish path is a US-only private
preview and we are in Australia. Its documented constraints drove the entire architecture, so the
influence is real even though nothing shipped through it.

**What worked well.** The constraints are published clearly and they are honest: **~500 ms per tool
round-trip**, turn-based with no proactive push and no long-running tools, tool discovery at deploy
time, max five spoken options. That 500 ms number is the single most useful line of documentation we
read all project — it is why no model call happens inside a tool, why the vision loop writes a cache
on its own clock, and why the whole system is split into a fast plane and a slow one. Constraints
stated up front are worth more than capabilities discovered late.

**What needs work.**

- **The toolkit is US-only while Alexa+ is live to Australian consumers** (from 2026-08-06), with
  Private Preview approval required and no published eligibility criteria or timeline. Entering the
  track does not require it, and the rules explicitly permit a simulated experience — but that took
  reading the rules carefully to establish, and the docs do not say it.
- **OAuth 2.1 with PKCE but no Dynamic Client Registration and no `WWW-Authenticate`.** A spec-pure
  MCP server therefore needs Alexa-specific changes. Worth a prominent callout, since "implements
  MCP" reasonably implies "works with an MCP host".
- **"Agent Skill" means two different things.** The track materials link the term to the open MCP
  standard's `SKILL.md`; Amazon's own Alexa+ docs never use it and call the surface "add-ons". Easy
  to lose an afternoon in the wrong documentation set.
- **No camera access for third parties.** The only camera-facing developer API is the Object
  Detection Sensor API, whose taxonomy is fixed (person/pet/package/vehicle), so an Echo Show cannot
  hand frames to a third-party server. Entirely reasonable as a privacy position — but for a device
  with a camera it is the first question a developer asks, and it is not answered anywhere
  prominent. We found it by elimination.

**Onboarding.** The hardest part of the project to get oriented in, mostly because of the
terminology collision and the US-only gate.

**Would we build with it again.** Yes, if the toolkit opens outside the US. The platform constraints
produced a better architecture than we would have designed without them.

---

## Amazon Bedrock (`bedrock-runtime`)

**What we used it for.** Intended as the perception model behind `ingest_frame`, on `au.*`
cross-region inference profiles for Australian data residency. **Not yet invoked** — blocked on the
two items below.

**What needs work.**

- **An unsubmitted Anthropic use-case form surfaces as `ResourceNotFoundException`.** The message
  text is helpful and names the form; the error *code* is not, and code is what callers branch on.
  `ResourceNotFoundException` reads as "your model id is wrong", so the first hour goes on
  re-checking the profile id and region. A distinct code, or the form's status shown in the console
  model list, would point straight at it.
- **Model discovery is gated separately from invocation.** An identity can hold
  `bedrock:InvokeModel` and still be denied `ListFoundationModels` and `ListInferenceProfiles` — so
  there is no API path to discover which model ids are valid. You must already know the id to test
  whether you may use it.
- **`au.` profiles are 4.5-generation only.** A clear, defensible trade — residency against frontier
  capability — but it is a significant architectural decision and we had to assemble it from several
  pages. A single table of geo prefix against available model generations would make it a five-minute
  decision instead of an hour's research.

**Onboarding.** The account-level entitlement step is the main obstacle, and it is invisible until a
call fails.

**Would we build with it again.** Yes — the residency story is a real product argument for a camera
in someone's kitchen, which is exactly why the model-generation trade needs to be easier to find.

---

## Amazon Bedrock AgentCore — Memory, Runtime, Policy

**What we used it for.** Memory is implemented and running against its local fallback: per-cook,
per-hob calibration under a `userPreferenceMemoryStrategy`, namespace `cook/{actorId}/hob/`, moving
a readiness threshold when the cook says "that was too early". Runtime is the deployment target, and
the MCP server already matches its contract exactly. Policy is expressed as four Dogwood rules.
**Nothing is deployed** — see the IAM note below.

**What worked well.**

- **Runtime hosting MCP natively is the right primitive.** It expects the container at
  `0.0.0.0:8000/mcp`, which is the default for the official SDKs, so our existing server needed no
  changes at all to be Runtime-shaped. Auto-injecting `Mcp-Session-Id` for clients that omit it is a
  thoughtful touch.
- **Dogwood is the reason our gate is a contract rather than a suggestion.** `formerly within`,
  `since within` and `count` let a decision condition on what the agent has already done this
  session, scoped by a session header. Being a strict superset of Cedar means existing Cedar
  knowledge transfers directly. We know of no other way to express "advancing requires a passing
  observation in the last 20 seconds" as policy rather than as an if-statement.
- The Python SDK's `create_or_get_memory` is correctly idempotent, which makes local development
  pleasant.

**What needs work.**

- **Two IAM principals are required and the quickstart implies one.** The deployer needs
  `bedrock-agentcore:*` plus `iam:PassRole`; separately, a **runtime execution role** must exist with
  its own trust policy naming `bedrock-agentcore.amazonaws.com`. The MCP walkthrough covers Cognito
  setup in detail but never states the execution role's actions, so you meet the second principal via
  a deploy failure. **There is also no published minimum deployer policy** — action names have to be
  reverse-engineered from `AccessDenied` messages one call at a time, which pushes everyone toward
  `"Action": "bedrock-agentcore:*"`, the opposite of least privilege. Publishing both templates in
  the prerequisites, as the Cognito setup already is, would fix this entirely.
- **Namespaces must end in a trailing slash** or you get multi-tenant prefix collisions. This is a
  footnote and deserves to be a validation error.
- **`IngestData` caps at 100 KB per item *and* per request**, against `CreateEvent`'s 10 MB. Both
  limits are documented but far apart, and the asymmetry is surprising enough to design around.
- The SDK logs its own `ERROR` lines before raising on a missing-credentials path. For a project
  that deliberately degrades to a local fallback, that makes a healthy run look broken; we suppress
  that logger during connection so a fresh clone is not misread as a failure.

**Onboarding.** Conceptually excellent — "the envelope around a model call, not the model call" is
the right framing and the docs land it. Operationally rough, almost entirely on IAM.

**Would we build with it again.** Yes, specifically for Memory and Policy. Those two are doing work
we could not do ourselves, which is the only real test of a managed service.

---

## Strands Agents SDK

**What we used it for.** A `BeforeToolCallEvent` steering hook that cancels `advance_step` at the
tool boundary, so the model cannot talk its way past the gate. Written and unit-tested against a
stub; **not yet run against the real SDK**, which is why it is declared as an optional `[aws]` extra
and degrades to absent rather than failing.

**What worked well.** Steering is the right abstraction for our problem and we adopted it on the
strength of the concept alone. The distinction between Proceed / Guide / Interrupt maps cleanly onto
"allow / cancel with corrective feedback / ask a human". `GraphBuilder` with conditional edge
traversal is exactly what our planned perception graph needs — a critic model that runs only near
the decision boundary, so cost stays flat.

**What needs work.**

- **The cancellation API is not stable across versions.** Our handler tries `cancel`, then
  `cancelled`, then `abort_reason`, and finally raises. That defensive ladder should not be
  necessary and is a sign the extension point needs a documented, versioned contract.
- **Steering-as-plugins is Python-only**; TypeScript uses a separate interventions framework. Fine,
  but the docs present steering as a general SDK feature and the language split is easy to miss.
- **The 100% vs 82.5% steering benchmark is AWS's own six-scenario eval, not an external
  benchmark.** It is cited prominently and the provenance is easy to overlook — we quote it as AWS's
  own figure for exactly that reason. Labelling it clearly in the docs would protect its credibility.

**Onboarding.** Good conceptual docs, thin on what a hook receives — we could not determine the
event object's shape without reading source.

**Would we build with it again.** Yes, for steering. The concept is worth the API churn.

---

## AWS CLI and IAM

**What we used it for.** Identity checks and capability probing across two regions.

**What needs work.** With no `iam:List*` permissions, an identity cannot enumerate its own policies,
so establishing what you can do means probing service calls one at a time and reading denial
messages. Those messages are excellent — they name the exact missing action and the resource ARN,
which is how we assembled a working policy at all. **The denial messages are the best diagnostic
tool in the stack**, and they only exist because someone chose to be specific rather than generic.
More services should copy this.

**Would we build with it again.** Yes.

---

## Playwright and ffmpeg (supporting, non-Amazon)

**What we used them for.** Capturing the panel's five states as screenshots, and recording the
47-second MVP verification video that walks all four verdicts. Both worked first time. Noted here
only for completeness, since they produced submission artefacts rather than product behaviour.
