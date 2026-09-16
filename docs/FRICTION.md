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
