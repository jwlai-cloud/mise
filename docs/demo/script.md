# Demo video — shot list

Runtime 2:38 (hard limit 3:00). Built by `docs/demo/build_video.py`; narration is
Gemini-TTS (`gemini-2.5-pro-tts`, voice Kore) via Cloud Text-to-Speech. Re-record with
a real voice by dropping `seg_<id>.wav` files into a directory and passing `--voice-dir`.

Everything shown is the real code. The pan is **scripted** — the video says so in
shot 2, because the rules require a simulated experience to be clearly shown as one.

| # | Footage | On-screen caption | Narration |
|---|---|---|---|
| 1 hook | panel, NOT YET | Mise — the cooking assistant that tells you to wait | Every recipe app pushes you forward, on a timer measured in someone else's kitchen. If you've never made the dish, you don't know what "until translucent" looks like. Mise watches the pan, and tells you to wait. |
| 2 | demo control page | Simulated Alexa+ experience — scripted pan, real MCP server | This is a simulated Alexa Plus experience. A scripted pan stands in for the camera, so every verdict can be shown on cue. Everything else — the MCP server, the gate, the agents — is the real code. |
| 3 | panel: clean run | NOT YET → GO | Ask, can I add the garlic yet? While the onions are still firm, it says not yet, with the evidence, and roughly how long. When the gate is met, it says go. |
| 4 | panel: steam (zoom on meter) | Past the gate — and it still refuses | Now steam crosses the lens. Look at the meter: it is past the gate. A system that guessed would say go. Mise says it can't tell, and shows why: confidence point two two, against point six needed. Refusing is the product, not an error. |
| 5 | panel: camera blocked | Frames stop → the panel dims | If the frames stop, the panel dims and counts the seconds since it last saw the pan. No fresh frame, no opinion. |
| 6 | panel: pan catches | OFF THE HEAT overrides everything | And if something is catching, off the heat overrides every other rule, even a view too unclear to judge. |
| 7 | terminal: real MCP client | Real MCP client — protocol 2025-11-25 | The same thing over MCP. A real client negotiates protocol twenty twenty-five, eleven, twenty-five. Check doneness returns refuse, and advance step is blocked, because advancing needs a passing observation from the last twenty seconds, not the model's belief. |
| 8 | architecture diagram | No model call inside a tool | Alexa Plus gives a tool about five hundred milliseconds, and a vision model will never fit. So perception runs on its own clock and writes a cache; tools only read it. The panel is an MCP App, marked app-only, so the screen keeps updating after the voice turn ends. |
| 9 | terminal: Strands graph | Strands multi-agent graph — the critic is conditional | Perception is a Strands multi-agent graph, shown here against a scripted model. A critic agent runs only near the decision boundary. On a clear frame it is skipped. On a steamed frame it fires, and its dissent can only lower confidence, never raise it. |
| 10 | terminal: test suites | 11 test suites — no AWS credentials | Eleven test suites pass on a clean clone, with no cloud credentials. One exists only to prove a refusal is never spoken as a wait. |
| 11 close | close card | Every recipe app pushes you forward. This one can refuse. | Every recipe app pushes you forward. This one can refuse. Mise is open source, on GitHub. |

## What the video deliberately does not claim

- No live camera or model call is shown, because none has run yet. Shot 2 says the pan
  is scripted; shot 9 says the graph runs against a scripted model.
- No health or safety claim. "Off the heat" is described as a warning, not an intervention.
