# Friction log

Format: task → steps → expected vs actual → severity → workaround → suggestion.
Worth up to a 10% judging bonus. Fill in as you hit things; these are already banked.

## 1. Ring Partner API returns JSON:API with no mention of it in the docs
**Severity:** medium · **Expected:** a REST object per the reference examples ·
**Actual:** a JSON:API envelope — `data[]` with `type`/`id`/`attributes`/`relationships`,
and `?include=` populating a sibling `included[]` that must be joined by id.
**Workaround:** write a resource-linkage resolver. **Suggestion:** state the media type
at the top of the API reference and show one full response.

## 2. A Doorbell Pro with no doorbell-press capability
**Severity:** medium · `GET /v1/devices/{id}/capabilities` on the Playground device
returns `motion_detection` as the only non-null sensing capability — no button press.
**Suggestion:** document which capabilities the synthetic device carries.

## 3. The Developers Playground is unlinked from every docs page
**Severity:** low · Announced in the 2026-05-28 release notes; not linked from the API
reference, the get-started page, or the hackathon resources page.

## 4. Vega Virtual Device cannot play audio
**Severity:** high · Open report: `MEDIA_ERR_SRC_NOT_SUPPORTED`, with both official
media samples failing on VVD. Combined with "validate on physical hardware before
submission", the emulator is not sufficient for media apps — which is not stated up front.

## 5. "Agent Skill" means two different things
**Severity:** medium · The hackathon's Alexa+ track links "Agent Skills" to the open MCP
standard's SKILL.md concept. Amazon's own Alexa+ docs never use the term; its surface is
"add-ons". Easy to spend an afternoon reading the wrong documentation.

## 6. MCP Toolkit is US-only while Alexa+ is live in Australia
**Severity:** high · Alexa+ launched to AU consumers on 2026-08-06; the developer
toolkit still reads "available in the United States", with Private Preview approval
required and no published eligibility criteria or timeline.

## 7. Bedrock reports an unsubmitted use-case form as `ResourceNotFoundException`
**Severity:** high · **Task:** first `bedrock-runtime converse` call on a new account ·
**Expected:** an error naming the missing prerequisite, or an `AccessDenied`-class code ·
**Actual:** `ResourceNotFoundException: Model use case details have not been submitted for this
account. Fill out the Anthropic use case details form before using the model. If you have already
filled out the form, try again in 15 minutes.`

The message text is genuinely helpful. The **error code is not**, and code is what callers branch
on: `ResourceNotFoundException` means "your model id is wrong" to anyone who has used the API, so
the first hour goes on checking the inference profile id and the region. `ValidationException`, or
a dedicated code, would point straight at the form.
**Workaround:** read the message, not the code. **Suggestion:** use a distinct error code for
account-level entitlement gaps, and surface the form's status in the Bedrock console's model list
rather than only on invocation failure.

## 8. AgentCore needs two IAM principals and the quickstart only implies one
**Severity:** medium · **Task:** planning permissions for `agentcore deploy` ·
**Expected:** one policy on the deploying identity · **Actual:** two distinct things are needed —
the deployer's own permissions (`bedrock-agentcore:*`, plus `iam:PassRole`), and a separate
**runtime execution role** that the service assumes, with its own trust policy naming
`bedrock-agentcore.amazonaws.com`.

The runtime MCP walkthrough covers Cognito and `agentcore deploy` in detail but never states the
execution role's required actions, so you discover the second principal from a deploy failure
rather than from the prerequisites. There is also no published minimum policy for the deployer: the
action names have to be reverse-engineered from `AccessDenied` messages one call at a time, which
pushes people to `"Action": "bedrock-agentcore:*"` — the opposite of least privilege.
**Workaround:** wildcard the service action scoped by `aws:RequestedRegion`, then tighten from
CloudTrail after the first successful deploy. **Suggestion:** publish a minimum deployer policy and
an execution-role template in the prerequisites section, the way the Cognito setup already is.

## 9. `bedrock:ListFoundationModels` is denied separately from `InvokeModel`
**Severity:** low · **Task:** checking which models an account can actually reach ·
**Actual:** an identity can hold `bedrock:InvokeModel` and still be unable to call
`ListFoundationModels` or `ListInferenceProfiles`, so there is no way to discover the valid model
ids from the API — you must already know the id to test whether you can use it.
**Suggestion:** treat model discovery as part of invoke access, or document the pairing, so
`InvokeModel` grants are not handed out without the read action that makes them usable.

## 10. Amazon's MCP server for this hackathon speaks an older MCP than the track requires
**Severity:** medium · **Task:** use Amazon Devices Builder Tools (listed under "Start Here (All
Tracks)" on the hackathon resources page) to search Alexa+ documentation from a coding agent ·
**Tool:** `@amazon-devices/amazon-devices-buildertools-mcp` 1.0.17, driven over stdio with raw
JSON-RPC.

What we hit, in order:

- **Protocol version.** We sent `initialize` with `protocolVersion: "2025-11-25"`; it answered
  **`2025-03-26`**. The Alexa+ track's minimum acceptable MCP version is 2025-11-25, so Amazon's own
  MCP server for the event is two spec revisions behind the floor it sets for entrants.
- **Framed as Fire TV only.** `--help` says it serves "apps for Amazon Vega OS"; the docs say Vega OS
  full support, Fire OS limited, and never mention Alexa. Yet it is the first item under "All
  Tracks". An Alexa+ entrant has every reason to conclude it is not for them.
- **But its index does cover Alexa+.** `search_documentation` returned Alexa+ add-on pages — including
  the web-simulator page, which we had not found any other way. It is more useful for this track
  than it says it is.
- **The platform filter is required and does not filter.** `target_platform.device_os` is mandatory
  and documents only `vega_os` / `fire_os`. A `vega_os` filter still returned Alexa+ pages, and an
  undocumented `["alexa"]` was accepted silently and returned a 2020 APL blog post.
- **Every tool is gated on `set_project_context`,** including doc search, and the refusal arrives as
  a successful tool result containing an error string rather than as a JSON-RPC error.
- **Install noise.** `npx` printed nine deprecation warnings, two of them (`tar@6`, `glob@7`) citing
  publicised security vulnerabilities.

**Workaround:** run it over stdio rather than `init-context` (which writes into the agent's MCP
config and drops a steering document into the workspace), call `set_project_context({config:{}})`
first, and pass any `device_os`. **Suggestion:** negotiate 2025-11-25; describe the Alexa+ doc
coverage the index already has; validate or drop the `device_os` filter; return the context gate as a
protocol error.

## 11. A Strands graph that passes every scripted test can still be blind to a real model

**Task:** run the existing Strands multi-agent graph (perceive → conditional critic + risk →
arbiter) against a real model for the first time, Gemini 2.5 Flash through `strands.models.gemini`.
**Severity:** high — each failure either dropped every frame or produced a confident wrong verdict,
and all three were invisible to a test suite that passed.

**Expected:** swap `ScriptedModel` for `GeminiModel`, get readings. **Actual, in order:**

1. **The frame never reached the agents.** `judge()` received the JPEG and invoked the graph with
   the text prompt only. A scripted model ignores its input, so eight tests passed while a real
   model was asked to judge a pan it could not see. *Fix:* pass `[{"text":…},{"image":…}]` as the
   task — Strands forwards the original task blocks to downstream nodes, so the critic and risk
   agents get the pixels too. Regression test: `test_every_agent_is_shown_the_frame`.
2. **Second frame: `RuntimeError: Event loop is closed`.** `asyncio.run()` per frame creates a new
   loop; the `genai.Client` inside `GeminiModel` stays bound to the first. *Fix:* one loop for the
   life of the graph.
3. **Structured output fields were read as suggestions.** `evidence: str = ""` was optional to the
   model, Gemini skipped it, and `validate()` rightly dropped the frame. With no field descriptions,
   it then put the doneness of a clear raw-onion frame (0.1) into `confidence`, and the system
   refused to judge a pan it could see perfectly. *Fix:* `evidence` required with `min_length=1`;
   every numeric field described ("NOT how cooked the food is").

**Workaround:** the fixes above. **Suggestion:** the structured-output docs should say plainly that
Pydantic field descriptions are the prompt and that defaulted fields are optional to the model;
the Gemini provider docs should note the client binds to the first event loop. For our own
process: a scripted model proves topology, never perception — run one real call end to end in
week one.
