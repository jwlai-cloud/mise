# Devpost submission — Mise

**Status: draft, 2026-09-16.** Accurate against commit `c20b1b8`. Every number here was
produced by running something; nothing is projected. Sections marked **[SPIKE]** are
placeholders for the week-one perception numbers and must be filled or cut before
submitting — do not ship a claim the corpus has not earned.

Track: **Alexa+** · Mini challenges: **AWS Builder**, **Open Source**
Deadline: 2026-10-23 12:00 PDT

---

## Inspiration

Every recipe app in existence pushes you forward. Step 1, step 2, step 3, a timer, a
"Next" button. None of them can see your pan, so every one of them assumes the onions
took the seven minutes the recipe said they would.

They didn't. Your hob runs hotter than the recipe author's. Your pan is thinner. You
diced coarser. The number on the screen was never about your kitchen.

So the timer is a guess dressed as an instruction, and the cook — who can see perfectly
well that the onions are still firm — is the one who has to overrule it. That is exactly
backwards. The thing with the camera should be the thing that says *not yet*.

And the person this hurts most is specific: **someone cooking a dish they have not made
before.** They are not short of instructions — they are short of *judgement*, and judgement
is the only part a recipe cannot hand over. "Until translucent" assumes you already know what
translucent looks like. If you did, you would not be reading the recipe.

The second half of the idea came from the failure case rather than the happy one. A
kitchen is a bad place to see: steam crosses the lens, a hand reaches in, a lid goes on.
Every shipping product we found handles this by answering anyway. Samsung's own footnote
admits its burn detection fails on dark or covered food — and then it still gives you an
answer. We wanted the opposite: a system whose response to *I can't see* is to say so.

## What it does

**Mise is a self-hosted MCP server where readiness is a refusable tool contract.** A
camera watches the pan; the assistant tells the cook to wait — and will decline to judge
at all when it cannot see properly. The refusal is not an error path. It is the product.

Ask *"can I add the garlic yet?"* and you get one of four verdicts:

| | |
|---|---|
| **GO** | the gate is met |
| **NOT YET** | with the evidence, and roughly how long |
| **CAN'T TELL** | frames are stale or the view is unreadable, so it will not guess |
| **OFF THE HEAT** | something is catching; overrides every other rule |

The loop, concretely:

1. A phone browser posts a JPEG to `/ingest` about every three seconds. No inference on
   the device — it grabs a frame, posts it, forgets it.
2. A vision model turns that frame into a `CookState`: how far along, how well it can
   *see*, whether anything is dangerous, and one sentence of evidence a human can check.
3. Before that reading is trusted, the model's own report of what is obstructing the view
   sets a **ceiling on its confidence**, re-applied in code. Confidence can only ever
   fall.
4. The reading lands in an in-process cache. This is the seam between the slow world and
   the fast one.
5. Alexa+ calls `check_doneness`. The tool reads the cache and applies a **deterministic**
   threshold — no model runs inside a tool call, ever. It answers in single-digit
   milliseconds against a ~500 ms budget.
6. `advance_step` is refused unless a *passing observation* was made in the last twenty
   seconds. Not the model's belief — an actual recent observation.
7. A `ui://` panel polls an app-only tool every two seconds, so the screen keeps carrying
   the detail after the voice turn has ended.

Two things follow from that shape, and they are the submission:

**A failed model call writes nothing at all.** Not a low-confidence placeholder — nothing.
The last frame simply ages until the gate refuses on its own. The failure path and the
staleness path are the same path, which means the system cannot be made to guess by
breaking it.

**Suppressing the voice never suppresses the screen.** A repeated "not yet" shortens, so
the assistant does not nag. A refusal shortens to *"I still can't tell."* — never to a
wait phrasing. The panel always carries the full reason.

## How we built it

**The load-bearing constraint.** Alexa+ budgets roughly 500 ms per tool round-trip and is
turn-based — it cannot interrupt you. A vision model does not fit in that budget and never
will. So the system is two planes joined by one cache: perception runs continuously on its
own clock and writes; MCP tools only ever read.

That constraint is also what makes a genuinely agentic design possible rather than
impossible. The agent is real and it is complex — it simply does not sit in the request
path. Putting it there would not make the product more agentic; it would make it time out.

**The stack, precisely:**

- **MCP Python SDK 1.30** (`FastMCP`), streamable HTTP, `stateless_http=True`. Verified
  negotiating protocol **2025-11-25** with a real MCP client. Five tools plus a `ui://`
  resource.
- **MCP Apps** (SEP-1865). The panel is a `ui://mise/panel` resource; `panel_state` is
  marked `_meta.ui.visibility: ["app"]`, which makes it callable by the page and invisible
  to the model. That plus a `setInterval` is how the screen stays alive after the voice
  turn ends — the single most valuable capability we found anywhere in this stack.
- **Amazon Bedrock**, `au.` cross-region inference profiles for Australian data residency,
  via Converse with **grammar-constrained structured output** (`outputConfig.textFormat`,
  `type: json_schema`) so the reading conforms to a schema rather than being asked to.
- **AgentCore Memory**, `userPreferenceMemoryStrategy`, namespace `cook/{actorId}/hob/`.
  It learns what *you* mean by translucent on *your* hob from you saying "that was too
  early". Samsung and GE calibrate to the appliance they sold you; nobody calibrates to
  your pan.
- **AgentCore Policy (Dogwood)** — a strict superset of Cedar adding `formerly within`,
  `since within` and `count`, so a decision can condition on what the agent has already
  done this session. This is why the gate is a contract and not a suggestion: a model
  cannot talk its way past a policy that reasons over its own action history.
- **AgentCore Runtime** as the deployment target. Its MCP contract expects the container
  at `0.0.0.0:8000/mcp` with `stateless_http=True`, which our server already matched
  exactly.
- **Strands Agents** — a `BeforeToolCallEvent` steering hook that cancels `advance_step`
  at the tool boundary.
- Python 3.11+, no framework. The gate is 60 lines and has no model in it.

**What actually runs today, stated plainly:** the gate, the session policy, the full MCP
surface, the panel, the scripted perception source, and the whole ingest path including
validation and the confidence clamp. Seven test suites pass on a clean clone with no AWS
credentials at all. **Not yet executed:** the Bedrock call itself, and anything deployed
to AWS. The call shape is verified against botocore's own service model rather than
recalled, but it has never been invoked — we are blocked on an account-level entitlement
form and an IAM grant, neither of which is code.

We would rather say that than imply otherwise. `docs/PRODUCT-FEEDBACK.md` marks the same
distinction tool by tool.

## Challenges we ran into

**The metric was rewarding luck.** Our abstention eval asked: when the system refused,
would it have landed on the right side of the gate anyway? That question is answerable —
the labels are independent — but it is the wrong one. Steam collapses confidence to 0.31
and the model still emits `doneness=0.88`; that number is noise. When the noise happened
to be correct, the metric scored the refusal as *unnecessary* — marking the system down
for the exact behaviour it exists to demonstrate. Two of three abstentions in our corpus
were the steamed lens and the blocked pan.

The fix needed a continuous ground-truth label, not a ready/not-ready bit: an abstention
is justified when `|doneness − label_doneness| > 0.15`. Then we added the risk-coverage
sweep we should have had from the start — and **it reversed a planned decision.** The old
single number implied "too conservative, tune the threshold down." The curve showed a safe
plateau from 0.35 to 0.85 where risk is 0% and coverage identical, with risk jumping to
11–12% below 0.35. The threshold was never the problem. We had been about to spend an
evening making the system worse.

**The demo could not show the product.** The simulated pan hardcoded `confidence=0.88` and
`risk="none"` and wrote every second, so `refuse` and `abort` were literally unreachable on
the only running code path. We had screenshots of the two verdicts every recipe app already
has and neither of the two that differentiate us. A camera that always works cannot
demonstrate a system whose selling point is admitting when it can't see.

**Rule 2 was speaking a refusal as a wait.** The anti-nag cooldown was keyed on *step*
rather than *verdict*, and its suppressed string was `"Still not yet."` So a plain wait at
t=0 spent the budget, and a genuine refusal thirty seconds later came out of the speaker as
a confident readiness claim about a frame the system had just declined to read. Our own
thesis, failing inside our primary tool. Cooldowns are now per verdict.

**Rule 4 promised something it never did.** After three corrections the assistant said it
would stop gating and hand control back — and then kept blocking. The consumer of
`should_stop_gating` was a string and nothing else. Wiring it revealed a second problem: in
Cedar and Dogwood `forbid` beats `permit`, so the rule as written would have forbidden
blocking an advance over a *burning pan*. It needed an explicit `risk != "urgent"` guard.

**Two writers to one cache is a silent bug.** After wiring the real-frame path we found the
scripted pan still ticking at 1 Hz beside it, simply winning the last write. Nothing
errored. Point a phone at a real hob and the panel would have shown the simulated one. Any
last-write-wins cache with more than one producer needs an explicit owner.

**`pip install -e .` was broken.** `mcp>=1.27` now resolves to 2.x, where
`mcp.server.fastmcp` no longer exists. Our own README failed on a clean clone.

Each of those five has a regression test. `tests/test_refusal_contract.py` exists
specifically so the first one can never come back.

## Accomplishments that we're proud of

- **All four verdicts run with no model, no camera and no AWS credentials.** Each is
  reachable in about two seconds via a scripted scenario. Verified live over HTTP and
  through a real MCP client at protocol `2025-11-25`.
- **Seven test suites, green on a clean clone.** Including one whose only job is to prove
  a refusal is never spoken as a wait, and one that takes a single model output
  (`doneness=0.88, confidence=0.31`) and flips only the ground truth — `0.86` → the
  abstention was unnecessary, `0.55` → it was justified. Same output, opposite verdict.
- **Risk 0% at 70% coverage**, and a system that always answered would have been wrong 20%
  of the time on the same frames. *Ten hand-written seed rows — the harness prints
  `NOT A RESULT` under 100 frames on purpose. This is a smoke test for the metric, not
  evidence about the system.*
- **Five contract bugs found and fixed**, each with a regression test, three of them found
  by adversarial review of our own work rather than by tests failing.
- **Nine friction-log entries**, three from this week's AWS work — including a Bedrock
  entitlement gap that surfaces as `ResourceNotFoundException` rather than an auth error,
  which costs an hour of checking the wrong thing.
- **The panel's refuse state is the whole pitch in one frame**: the progress meter is
  visibly *past* the gate marker while the verdict reads CAN'T TELL, with
  `confidence 0.22 / 0.60 needed` underneath. A judge gets it without narration.
- **[SPIKE]** perception accuracy against hand-labelled frames — target: monotonic and
  within ±0.15, with confidence dropping when the view is blocked.

**What we deliberately did not build**, so that cut-by-choice reads differently from
didn't-finish: this is not a safety device and makes no health claims; it is not a recipe
database (seven MCP servers already are); it never touches the hob; and multi-dish
choreography — the strongest remaining differentiator, which nothing on the market does — was
cut on time rather than on merit. `docs/PRODUCT.md` records each with its reason.

## What we learned

**A counterfactual built from a system's own degraded output measures luck, not
correctness.** If you abstain because a signal is unreliable, you cannot then use that
signal to score the abstention. This sounds obvious written down; it survived two passes of
review in our eval harness because the labels involved really were independent, so nothing
looked circular. It was only visible once we asked *which specific rows is this penalising?*
and the answer came back: the steamed lens and the blocked pan.

**"Too conservative" is a claim about a curve, not a number.** A single abstention figure
told us to tune a threshold. The risk-coverage sweep showed a wide plateau where the
threshold cost nothing at all. One number can point you confidently in the wrong direction.

**Constraints published up front are worth more than capabilities discovered late.** The
Alexa+ 500 ms round-trip is the single most useful line of documentation we read all
project. It is why nothing calls a model inside a tool, why perception has its own clock,
and why the architecture splits the way it does. A platform that tells you what it will not
do produces better designs than one that lets you find out.

**Prompting a model to be careful is a request; a table re-applied in code is a
guarantee.** We ask the model to report what is obstructing the view, then clamp confidence
to a ceiling derived from its own answer. Confidence can only fall. And we wrote down the
limit rather than glossing it: the clamp cannot catch a model that *misreports* the view,
and that is precisely where a wrong "proceed" will come from.

## What's next

- **Run the week-one spike.** Three real cooks, fixed camera, a frame every three seconds,
  labelled with a continuous `label_doneness` — and deliberately including the degraded
  frames, because a corpus of clean ones cannot measure abstention at all. Then re-run the
  sweep and set the confidence floor from data instead of judgement.
- **Surface `risk="watch"` or delete it.** It is currently inert: the gate has no branch for
  it and the panel never shows it, so ambiguous haze routes into a band that does nothing.
  A safety story the code does not tell is worse than no story.
- **The hot Strands graph** — perception, an adversarial critic on a conditional edge that
  fires only near the decision boundary, and a risk node in its own failure domain, joined
  by a deterministic arbiter. Designed and diagrammed; the seam it sits behind is built.
- **Multi-dish choreography** — backwards-scheduling two pans to land together. Nothing on
  the market does it. It needs per-dish state throughout and a perception layer that can
  attribute state to two pans, so it is honestly a next-version feature rather than a
  claim we are making now.
- **Hysteresis on the refusal path.** A moving hand on a busy step puts an obstruction in a
  large share of frames, and at one call every few seconds that becomes a refusal storm.
  Requiring two consecutive low-confidence frames would fix it — and must never apply to
  danger.

## Built with

`python` · `model-context-protocol` · `mcp-apps` · `alexa` · `amazon-bedrock` ·
`bedrock-agentcore` · `agentcore-memory` · `agentcore-policy` · `agentcore-runtime` ·
`strands-agents` · `cedar` · `starlette` · `uvicorn` · `pydantic` · `aws`

## Try it out

- **Repository:** https://github.com/jwlai-cloud/mise (Apache-2.0)
- **Demo video:** [SPIKE/FINAL — under 3 minutes, YouTube or Vimeo, public]

```bash
git clone https://github.com/jwlai-cloud/mise.git && cd mise
python3 -m venv .venv && .venv/bin/pip install -e .
PYTHONPATH=src .venv/bin/python -m uvicorn mise.app:app --port 8000
```

Open <http://localhost:8000/dev/control>, press **1 2 3 4**, watch
<http://localhost:8000/dev/panel> beside it. Four buttons, one per verdict, **no AWS
account, no camera, no model, no API key**. Walked from a clean clone on a machine with
no credentials; the README's "Judges start here" block is the same sequence.

**Press 2.** The progress meter sits visibly past the gate marker and the verdict still
reads CAN'T TELL, with `confidence 0.22 / 0.60 needed` underneath. A system that guessed
would say GO there. That one screen is the submission.

For a real MCP client: `npx @modelcontextprotocol/inspector` against
`http://localhost:8000/mcp` (spec 2025-11-25, streamable HTTP). A browser hitting `/mcp`
returns 406 — that is the protocol requiring an `Accept` header, not a fault.

---

## Pre-submission checklist

- [ ] **[SPIKE]** placeholders filled or cut — no unearned claims
- [ ] Demo video under 3 min, public, showing the MCP server in action
- [ ] Story, video and diagrams tell the same story with the same numbers
- [ ] `docs/PRODUCT-FEEDBACK.md` pasted into the product-feedback field (**required**)
- [ ] `docs/FRICTION.md` submitted (optional, up to 10% bonus)
- [ ] Open Source mini challenge: contribution URL + repo URL + GitHub username
- [ ] AWS Builder mini challenge: named services with the reason for each primitive
- [ ] Confirm the abstention figures still carry their "not a result" caveat
