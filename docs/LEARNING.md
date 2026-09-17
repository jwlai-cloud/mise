# Learning notes

For reading slowly after the hackathon, not skimming during it.

## MCP, and what "spec 2025-11-25" buys you

The Model Context Protocol is a JSON-RPC protocol between a host (Alexa+, Claude,
ChatGPT) and a server you run. Three primitives: **tools** (callable functions),
**resources** (addressable content), **prompts**. Transport here is **streamable
HTTP** — a single endpoint that can stream responses, as opposed to the older
SSE pair or stdio for local servers.

- Spec: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Python SDK: https://github.com/modelcontextprotocol/python-sdk (we use `mcp` 2.1, `MCPServer`;
  `FastMCP` was the 1.x name and is a stub in 2.x that raises with a link to the migration guide)

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

---

## Bedrock structured outputs, verified against the service model

Everything here was checked against botocore 1.43.95's `bedrock-runtime/service-2.json`
rather than recalled, because the parameter names are where an evening goes.

```python
outputConfig={"textFormat": {"type": "json_schema", "structure": {
    "jsonSchema": {"name": "pan_reading", "schema": SCHEMA_JSON}}}}
```

- **`schema` is shape `String`, not a Document.** `json.dumps` it. Passing a dict is a
  `ParamValidationError` before anything reaches the wire — and note this differs from
  `toolSpec.inputSchema.json`, which *is* a real dict. Easy to conflate.
- **`OutputFormatType` enum is exactly `['json_schema']`.**
- This is **grammar-constrained decoding**, not a request. Bedrock validates the schema
  against a Draft 2020-12 subset (immediate 400), compiles a grammar, caches it 24h, and
  the model then cannot emit tokens outside it. No fenced-code wrapping, no retry loop,
  no regex salvage. That is the whole reason to prefer it over "please reply in JSON".
- **Unsupported keywords 400 before inference:** `minimum`, `maximum`, `multipleOf`,
  `minLength`, `maxLength`, `maxItems`, `uniqueItems`. So `0..1` bounds cannot live in
  the schema — enforce them in Python. `enum` **is** supported, which is why `risk` is
  genuinely constrained on the wire and `doneness` is not.
- **`botocore>=1.43.0` is a hard floor.** 1.42.9 has no `outputConfig` in its
  bedrock-runtime model at all, so the call fails client-side with a confusing error.

Images:

```python
{"image": {"format": "jpeg", "source": {"bytes": jpeg_bytes}}}
```

- `ImageSource.bytes` is a **blob** — pass raw bytes and the SDK base64s them. Doing it
  yourself sends base64-of-base64 and the model sees noise. The API reference says so
  verbatim: *"If you use an AWS SDK, you don't need to encode the image bytes in base64."*
- `format` enum is `['png','jpeg','gif','webp']` — **`"jpg"` is a ValidationException.**
- `ImageSource` is a union: set `bytes` or `s3Location`, never both.
- Image block **before** the text block; Anthropic documents that ordering.
- `metrics.latencyMs` comes back on every response. Measure, don't estimate.
- `stopReason` includes `malformed_model_output`. Anything other than `end_turn` or
  `stop_sequence` is a refusal, not a result.

Model note: `au.anthropic.claude-haiku-4-5-20251001-v1:0` is a real Geo profile with
ap-southeast-2 as a source region (destinations Sydney and Melbourne), vision-capable,
structured outputs supported. It has **no bare-model-id on-demand path** — calling the
bare id is a `ResourceNotFoundException`. Service tier **Priority is not available** for
it, so the string passes client validation and fails on the wire.

- https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html
- https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

## Calibrated abstention, and why the obvious metric is wrong

The selective-prediction framing: a system may answer or abstain, so accuracy is the
wrong headline and a **risk-coverage pair** is the right one — of the frames it chose to
judge, how often was it wrong, and what fraction did it judge.

The trap took two passes to see. Asking *"if it had answered, would it have landed on the
right side of the gate?"* is answerable with independent labels — but it scores a **lucky
noisy estimate** as evidence the refusal was unnecessary. Steam collapses confidence to
0.31 and the model still emits `doneness=0.88`; if the pan happens to be ready, that
scores the refusal as a mistake. The metric then points threshold tuning in exactly the
wrong direction.

The fix needs a *continuous* ground-truth label, not a ready/not-ready bit:

```
justified abstention  ⇔  |doneness − label_doneness| > TOLERANCE
```

Two lessons worth keeping beyond this project:

1. **A counterfactual built from the system's own degraded output measures luck.** When
   you abstain because a signal is unreliable, you cannot then use that signal to score
   the abstention.
2. **"Too conservative" is a claim about a curve, not a number.** Sweeping the confidence
   floor revealed a safe plateau (0.35–0.85) where risk is 0% and coverage identical. The
   single headline figure had implied a tuning job that the curve showed was unnecessary.

- "When Robots Should Say 'I Don't Know': Benchmarking Abstention in Embodied QA",
  arXiv 2512.04597 — the framing this borrows.

## Making a model's confidence mean something

The gate thresholds `confidence`, so it is not decoration — it is the trigger for the
differentiating verdict. A model that cheerfully reports 0.9 through steam destroys the
contract silently, and no downstream code can recover from it.

What we landed on, in increasing order of how much it can be trusted:

1. **Schema order.** `view` and `obstructions` come first, so the model commits to what it
   can *see* before it is asked how sure it is, and judges danger before it has told
   itself a story about readiness. *Caveat: JSON Schema `properties` is formally an
   unordered map and AWS documents nothing about emission order. This is an assumption.*
2. **A ceiling table rather than an instruction.** "Be careful when the view is bad" is
   unfalsifiable; `steam → 0.35` is a lookup a model can follow.
3. **The same table re-applied in Python.** Confidence can only ever fall. This is the
   only one that is a guarantee — the same argument `steering.py` makes about intercepting
   at the tool boundary rather than asking nicely in a prompt.

The honest limit: the clamp's input is the model's *own claim* about whether it can see.
It catches a model that reports the view honestly and over-claims the number. It cannot
catch a model that misreports the view — and that is the case that puts a cook in front of
a ruined pan. Only a labelled corpus and the risk-coverage sweep will find it.

## Concurrency lessons that only appear when you run it

- **Two writers to one cache is a silent bug, not a loud one.** The scripted pan and the
  camera both wrote to `STORE`; the scripted one ticked at 1 Hz and simply won the last
  write. Nothing errored. The panel just showed the wrong pan. Any last-write-wins cache
  with more than one producer needs an explicit owner.
- **Check a lock *after* reading the request body, not before.** Checking first lets a
  second request pass the test and then queue on the lock — the backlog you were trying
  to avoid, arriving late instead of being dropped.
- **A merge-write turns a partial failure into a lie.** `STORE.write()` merges, so writing
  only `confidence=0` to signal failure keeps the previous `risk` and refreshes the
  timestamp. A stale `urgent` would then abort forever, under a fresh clock. Write
  everything or write nothing.
- **Timestamp the observation, not the write.** A 2–3 s model call stamped at write time
  makes staleness measure your own latency instead of the age of the view.
