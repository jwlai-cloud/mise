# 0002 — Positioning against prior art

Status: accepted · 2026-09-15

An originality audit found the vision loop is **not** novel:

- **Fullerton, IEEE IRI 2025**, "Real-Time Camera-based Smart Cooking Assistant" —
  overhead hob camera, YOLO11S over six cooking states, mAP@0.5 = 0.96, prompts the
  cook to advance when the pan looks right. That is this project's perception layer,
  already built and measured.
- **CamCook** ships marketing copy reading "confirms when steps are done right. Are
  those onions translucent enough?" — *do not use that phrasing.*
- **GE Profile Kitchen Hub** put a cooktop camera in kitchens in 2020;
  **Samsung AI Vision Inside** does 80 dishes plus burn detection; **GE CookCam**
  adjusts temperature from an in-oven camera.

**Decision: cite the prior art openly and position on the contract, not the camera.**
"Quality of the Idea" rewards ecosystem understanding, so naming Fullerton and saying
"perception is solved; the contract is missing" scores better than claiming novelty
a judge can puncture in thirty seconds.

What the audit found genuinely unoccupied:

1. Every cooking MCP server that exists (at least seven) is a **database** — search,
   store, meal-plan. Generic webcam MCP servers exist separately. **Nobody has joined them.**
2. Alexa+'s published partner list has **zero cooking partners and zero vision partners**.
3. No shipping product is designed to **withhold**. Hestan holds the pan's temperature,
   GE and Samsung adjust the oven, every recipe app pushes forward. Nobody sells "no."
4. **Calibrated abstention on degraded perception** has no consumer implementation.
   Samsung's own footnote admits burn detection fails on dark or covered food.
5. Nobody does **multi-dish choreography** — landing two pans and the oven together.

**Hard constraint discovered:** Alexa's only camera-facing developer API is the Object
Detection Sensor API (person/pet/package/vehicle from security cameras). **Echo Show
will not hand camera frames to a third-party MCP server.** The camera is your own
webcam or phone; the Show is display only. State this in the demo before a judge asks.

## Open questions carried forward

- Camera source: phone browser (chosen for week 1) vs the Echo Show's own camera via
  `_meta.ui.permissions` — the latter is unverified on Echo Show silicon.
- Whether Alexa's MCP client implements the full `ui/*` method set; its lifecycle doc
  confusingly cites protocol 2025-03-26 in one example.

