# Mise — what it is, who it's for, and what it refuses to be

The decisions live in `docs/adr/`; what exists lives in `docs/ARCHITECTURE.md`. This
is the other thing: the problem, the person, and the edge. It exists because
"Potential Impact" asks for a *credible, specific* case, and until now this repo
had no persona, no non-goals, and no impact sentence written down anywhere.

Last updated 2026-09-17.

---

## The problem, in one falsifiable sentence

**A recipe's timings were measured in someone else's kitchen, so the only thing in
the room that can actually tell whether the food is ready is the cook — and the
cook is the one person who doesn't know what "ready" looks like for a dish they
haven't made before.**

Falsifiable, so worth stating how it could be wrong: if hob power, pan mass, dice
size and starting temperature varied little between kitchens, a timer would be
fine and this product would be pointless. They vary a lot. "Soften the onions for
7–8 minutes" is a number from a test kitchen, and the cook standing over a thin
pan on a hot gas ring is expected to silently correct it.

So every recipe app has the relationship backwards. **The app pushes; the human
judges.** It should be the other way around: the thing with the camera should be
the one saying *not yet*.

## Who it's for

**Primary: someone cooking a dish they have not made before.** The recipe says
"until translucent" and they do not know what translucent looks like. They are not
short of instructions — they are short of *judgement*, and judgement is the only
part a recipe cannot hand over. This is the person the demo is built around.

**Secondary: a cook who cannot easily look.** Hands in raw chicken, glasses
fogged, a toddler in the other room, or simply not able to see the pan clearly
from where they are standing. The panel keeps showing the detail; the voice
answers when asked.

**Explicitly not: the confident cook.** Someone who has made soffritto two hundred
times needs nothing here and we should not pretend otherwise. A product that
claims to help everyone helps no one in particular, which is the failure mode this
section exists to avoid.

## What it does

Ask *"can I add the garlic yet?"* and get one of four answers:

| | |
|---|---|
| **GO** | the gate is met |
| **NOT YET** | with the evidence, and roughly how long |
| **CAN'T TELL** | stale or unreadable view — it will not guess |
| **OFF THE HEAT** | something is catching; overrides everything |

The third one is the product.

## The edge

### What already exists

The perception is **not novel and we say so** — claiming otherwise is a thirty-second
puncture for any judge who searches. See ADR-0002.

| Prior art | What it does | What it does not do |
|---|---|---|
| **Fullerton, IEEE IRI 2025** | Hob camera, YOLO11S over six cooking states, mAP@0.5 = 0.96. Prompts the cook to advance. | Never withholds. It is our perception layer, already built and measured. |
| **CamCook** | Ships marketing copy about confirming when steps are done right. | Answers every time it is asked. |
| **GE Profile Kitchen Hub** | Put a cooktop camera in kitchens in 2020. | Tied to the appliance you bought; adjusts rather than advises. |
| **Samsung AI Vision Inside** | 80 dishes, plus burn detection. | **Its own footnote admits detection fails on dark or covered food — and it still answers.** |
| **GE CookCam** | In-oven camera adjusts temperature. | Acts on the appliance; never hands judgement back. |
| **~7 cooking MCP servers** | Search, store, meal-plan. | None of them can see anything. |
| **Generic webcam MCP servers** | Stream frames to a model. | Know nothing about cooking. |

Alexa+'s published partner list has **zero cooking partners and zero vision
partners**.

### What is actually unoccupied

**Nobody sells "no."** Every product above either pushes the cook forward or
adjusts the appliance. Not one of them is designed to withhold, and not one admits
when it cannot see. Samsung documents the exact failure mode and answers anyway.

Two mechanisms make that a product rather than a slogan:

1. **Advancement is gated on a recent *observation*, not on the model's belief.**
   `policy.py::may_advance` refuses unless a passing observation was made in the
   last twenty seconds. A prompted vision loop has a conversation; it has no notion
   of observation recency. This is the sentence that survives a skeptic.
2. **Confidence can only ever fall.** The model reports what is obstructing the
   view, and a ceiling table re-applied *in code* clamps its confidence to match.
   A prompt asking a model to be careful is a request; a table applied after
   parsing is a guarantee.

And the honest limit, stated here so it is not discovered by a judge: **the clamp
cannot catch a model that misreports the view.** A clear-looking frame of a
genuinely ambiguous pan carries a high ceiling, and that is where a wrong GO will
come from. Only a labelled corpus and the risk-coverage sweep will find it.

## Non-goals

Recorded so that "cut deliberately" is distinguishable from "did not finish."

- **Not a safety device.** It does not stop anyone cooking unsafely and we make no
  claim that it does. `OFF THE HEAT` is a warning on a screen, not an intervention.
- **No health or nutrition claims.** Ring's content-policy precedent suggests
  Amazon rejects those outright.
- **Not a recipe database.** Seven MCP servers already do that. A recipe here is a
  list of *gates*, not steps, and there is exactly one of them.
- **Not an appliance controller.** It never touches the hob. Hestan and GE do that;
  it requires their hardware and it removes the judgement we are trying to hand back.
- **Not multi-dish, this version.** Backwards-scheduling two pans to land together
  is the strongest remaining differentiator and nothing on the market does it — but
  it needs per-dish state throughout and a perception layer that can attribute
  state to two pans. **Cut on time, not on merit.** It belongs in "What's next".
- **Not using the Echo Show's camera.** Not a choice: Alexa's only camera-facing
  developer API is the Object Detection Sensor API (person/pet/package/vehicle).
  An Echo Show will not hand frames to a third-party server. The camera is a phone.

## How we would know it worked

Product-level, distinct from the eval numbers in `evals/`.

| | Target | Where it is measured |
|---|---|---|
| It never says GO on a frame it could not read | selective risk 0% | `evals/abstention.py` |
| It is still useful — it does not just refuse | coverage well above 50% | same |
| It declines for the right reason | the estimate really was off by >0.15 | same |
| The agent takes a sane path | the critic fires near the gate and only there | `evals/trajectory.py` |
| A cook can use it without a manual | four buttons, no instructions needed | `/dev/control` |

**The falsification test:** if a 4.5-generation vision model cannot judge a
domestic hob to ±0.15 across steam, glare and a moving hand, the contract is
well-built scaffolding around a perception layer that does not work, and the
honest move is to say so rather than demo around it. That is what `docs/SPIKE.md`
is for, and it is three evenings.

## The one sentence

> Every recipe app pushes you forward. This one can refuse — and advancement is
> gated on a recent *observation*, not on the model's belief.
