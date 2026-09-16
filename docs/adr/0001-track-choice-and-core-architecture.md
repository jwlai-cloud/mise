# 0001 — Track choice and core architecture

Status: accepted · 2026-09-15 · Deadline 2026-10-23

## Context

Four tracks. Hardware on hand: one Echo. No Fire TV, no Ring device, no Bee
pendant, no usable Apple Watch (Series 4 is below the practical floor).

Findings that eliminated the alternatives:

- **Bee** — pendants ship US-only with no loaner programme. The Apple Watch is the
  sanctioned alternative but no usable watch is available. *Eliminated on hardware.*
- **Ring** — `ava.v1:read` is the only scope the platform supports, so no writes for
  anyone, ever. The Playground offers one synthetic Doorbell Pro whose only non-null
  sensing capability is `motion_detection`; history starts empty with no seeding or
  backdating; the Sensors API and multi-camera both need real hardware. Separately,
  the Ring Appstore already ships absence detection (Mercury Alert AI), routine-deviation
  detection (Beside Care) and generic anomaly baselining (Memories.ai).
  *Eliminated on originality and on capability ceiling.*
- **Fire TV** — viable, and `IChannelServer` / `epgSyncTask` are genuinely undiscovered.
  But the Virtual Device has an open bug where audio playback fails on Amazon's own
  media samples, and Amazon requires physical-device validation for media apps. The
  `vega-sports-app` microphone privilege is a dead end: the Stick has no microphone,
  and `getUserMedia` is unsupported for third-party apps in Vega WebView.
  *Not eliminated — held as the fallback.*
- **Alexa+** — chosen.

## Decision

Build **Mise** on the **Alexa+** track: a self-hosted MCP server (streamable HTTP,
spec 2025-11-25) with an MCP Apps `ui://` panel, plus a continuous vision loop.

### On the US-only concern

Amazon's MCP Toolkit docs say *"available in the United States"* and require Private
Preview approval. That gates **publishing an add-on to real Echo devices** — not
entering. The organisers' own onboarding email directs Alexa+ entrants to
`modelcontextprotocol.io` and the open standard, and the rules explicitly permit a
simulated Alexa+ experience. The Add-on Local Inspector renders panels in real device
frames locally with no preview access.

*Consequence:* preview approval is a bonus, not a dependency. Decision date **3 Oct** —
if access has not landed, film the Local Inspector and the simulated experience.

## Architecture

**1. The vision model never runs inside a tool call.**
Alexa+ budgets ~500ms per tool round-trip. The vision loop runs on its own clock
(~0.3Hz) and writes `CookState` to an in-process cache; tools only read it. Frames are
dropped rather than queued — a stale answer is worse than none, and `is_stale` handles
the gap honestly rather than silently.

**2. Voice is turn-based; the panel is not.**
Alexa+ has no proactive push and no long-running tools, so voice cannot interrupt the
cook. A `visibility: ["app"]` tool polled on a 2s interval keeps the panel live after
the voice turn ends. Danger surfaces on the screen; voice answers when asked.

**3. The gate is deterministic; only the phrasing is generative.**
"Is doneness ≥ 0.8" is a threshold, not a judgement, and wrapping it in an agent would
be an expensive cron job. The model's job is perception (frame → state) and narration.
Advancement is enforced in code, and will additionally be enforced at the tool-call
boundary by Strands steering and AgentCore Policy.

**4. Refusal is a first-class verdict.**
Stale frames or low confidence return `refuse`, not a guess. This is the
differentiation claim and it must never be optimised away.

## AWS integration (AWS Builder mini challenge)

Deploy to **ap-southeast-2**. AgentCore is GA there with Runtime, Memory, Gateway,
Identity, Policy, Evaluations and Observability. Sydney has no `apac.` Anthropic
profile, so the choice is `au.` cross-region profiles (data residency, 4.5-generation
models) or `global.*` (frontier models, no residency guarantee). **Take `au.`** — for a
consumer product this is defensible on camera and scores under Design and Impact.

- **AgentCore Memory** — long-term strategies, namespaced per cook. Learns that this
  hob runs hot and what *this cook* means by "translucent". The demo moment is a
  behaviour change between session 1 and session 3.
- **AgentCore Policy (Dogwood temporal policies)** — `formerly within` / `since within`
  encode "don't nag twice inside two minutes" as policy rather than if-statements.
- **Strands steering** — `advance_step` cannot execute unless the gate passes.
- **AgentCore Evaluations** — score verdicts across recorded pan footage.
