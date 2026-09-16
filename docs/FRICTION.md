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
