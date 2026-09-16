# Learning notes

For reading slowly after the hackathon, not skimming during it.

## MCP, and what "spec 2025-11-25" buys you

The Model Context Protocol is a JSON-RPC protocol between a host (Alexa+, Claude,
ChatGPT) and a server you run. Three primitives: **tools** (callable functions),
**resources** (addressable content), **prompts**. Transport here is **streamable
HTTP** — a single endpoint that can stream responses, as opposed to the older
SSE pair or stdio for local servers.

- Spec: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Python SDK: https://github.com/modelcontextprotocol/python-sdk (we use `mcp` 1.27, `FastMCP`)

`stateless_http=True` + `json_response=True` means every request is independent —
simpler to scale, and the right default when the real state lives in a cache
outside the protocol, as ours does.

## MCP Apps (`ui://` resources)

An extension (SEP-1865, `io.modelcontextprotocol/ui`) letting a tool return an
**interactive HTML page** rendered in a sandboxed iframe by the host. Not a card
format — official examples include Three.js scenes and ShaderToy shaders.

Key mechanics we rely on:
- A resource at a `ui://` URI with mime `text/html;profile=mcp-app`.
- A tool links to it via `_meta.ui.resourceUri`.
- The view talks back over **JSON-RPC on `postMessage`** — `tools/call`, `resources/read`, and UI-specific methods like `ui/update-model-context`.
- **`_meta.ui.visibility: ["app"]`** makes a tool callable by the panel but invisible to the model. That plus a `setInterval` is how the panel keeps updating after the voice turn ends — the single most important capability in this project.
- CSP is deny-by-default: `_meta.ui.csp.connectDomains` etc. must be declared or the page gets `default-src 'none'`.

Docs: https://apps.extensions.modelcontextprotocol.io/api/

## Alexa+ add-ons

Amazon's surface is **add-ons**, in three flavours: MCP Toolkit (bring your own
server), Category SDK (fixed verticals — reservations, food delivery, rides,
home services, local booking, ticketing), and the Smart Home AI Toolkit. Ours is
MCP Toolkit.

Constraints that shaped the architecture, all documented:
- **<500ms round-trip**, certification expects search results within 3s.
- Turn-based; **no long-running tools, no proactive notifications**.
- Tool discovery happens at **deploy time** — schema changes need a redeploy.
- OAuth 2.1 with PKCE, but **no Dynamic Client Registration and no `WWW-Authenticate`**, so a spec-pure MCP server needs Alexa-specific changes.
- Max **5 spoken options**; voice responses under 30s.

Docs: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html

## AgentCore

Operational infrastructure for agents — framework- and model-agnostic. Not
"Bedrock with tools": Bedrock `InvokeModel` gives you a model call, AgentCore
gives you the envelope around it.

- **Memory** — short-term events plus long-term strategies (semantic, user preference, summary, episodic). Namespaces are hierarchical and **must end in a trailing slash**. `IngestData` (shipped 2026-09-08) writes arbitrary JSON straight to long-term memory; note the tight limit — 100KB per item *and* per request, much tighter than `CreateEvent`'s 10MB.
- **Policy / Dogwood** — Dogwood is a strict superset of Cedar adding `formerly within`, `since within`, `count`, `sum`. Temporal policies condition on the agent's action history within a session, scoped by `x-amzn-bedrock-agentcore-policy-session-id`.
- **Evaluations** — batch evaluation with custom evaluators; where `evals/abstention.py` eventually lands.
- Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/

Region note: Sydney (ap-southeast-2) has all of the above but **no `apac.` Anthropic profile** — the Australian geo prefix is `au.`, routing Sydney↔Melbourne, on 4.5-generation models. Frontier models are `global.*` only, with no residency guarantee.

## Strands Agents

AWS's open-source model-driven agent SDK (`strands-agents`, Python and TS).
What we use:
- **Hooks** — `BeforeToolCallEvent` / `AfterToolCallEvent`.
- **Steering** — intercepts tool calls *before* execution, returning Proceed / Guide (cancel with corrective feedback) / Interrupt (human in the loop). Steering-as-plugins is **Python-only**; TypeScript uses a separate interventions framework.
- AWS reports 100% vs 82.5% prompt-only over 600 runs — **their own six-scenario eval**, not τ-bench. Quote it as theirs.
- Docs: https://strandsagents.com/docs/user-guide/concepts/plugins/steering/

## Prior art worth reading

- Fullerton, IEEE IRI 2025 — camera-based smart cooking assistant, hob-mounted, YOLO11S, six cooking states, mAP@0.5 0.96.
- OSCAR (arXiv 2503.05962, 2507.03330) — LLM+VLM recipe-progress tracking from egocentric video; 40–66.7% in real kitchens. Tracks, doesn't gate.
- "Rethinking Cooking State Recognition with Vision Transformers" (arXiv 2212.08586).
- "When Robots Should Say 'I Don't Know': Benchmarking Abstention in Embodied QA" (arXiv 2512.04597) — the framing for `evals/abstention.py`.
