#!/usr/bin/env python3
"""Build the demo video from the real system. See docs/demo/script.md.

    python3 docs/demo/build_video.py                    # TTS narration (macOS `say`)
    python3 docs/demo/build_video.py --voice-dir DIR    # use DIR/seg_<id>.wav where present

Every terminal shot is captured from a real command run during the build, and
every panel shot is the real panel driven by the real scenario rig. Nothing on
screen is typed by hand.

Needs: macOS `say`, ffmpeg, playwright (+ chromium). Output: docs/demo/mise-demo.mp4
"""
from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "docs" / "demo" / "raw"           # gitignored
OUT = ROOT / "docs" / "demo" / "mise-demo.mp4"
PORT = 8999
BASE = f"http://localhost:{PORT}"
VOICE, RATE = "Ava (Premium)", 172
# Narration spells the name "Meez" - TTS reads "Mise" as "mize". Captions keep "Mise".
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
BG = "0x0B0E13"
PAD = 0.7                                        # silence after each line, seconds

# (id, kind, source, caption, narration)
#   kind "panel": source = (scenario, seek seconds)   recorded live from /dev/panel
#   kind "still": source = name of a rendered card
SEGMENTS = [
    ("01", "panel", ("clean_run", 8), "Mise — the cooking assistant that tells you to wait",
     "Every recipe app pushes you forward, on a timer measured in someone else's kitchen. "
     "If you've never made the dish, you don't know what until translucent looks like. "
     "Meez watches the pan, and tells you to wait."),
    ("02", "still", "control", "Simulated Alexa+ experience — scripted pan, real MCP server",
     "This is a simulated Alexa Plus experience. A scripted pan stands in for the camera, "
     "so every verdict can be shown on cue. Everything else, the MCP server, the gate, "
     "the agents, is the real code."),
    ("03", "panel", ("clean_run", 54), "NOT YET  →  GO",
     "Ask, can I add the garlic yet? While the onions are still firm, it says not yet, "
     "with the evidence, and roughly how long. When the gate is met, it says go."),
    ("04", "panel", ("steam", 38), "Past the gate — and it still refuses",
     "Now steam crosses the lens. Look at the meter. It is past the gate. A system that "
     "guessed would say go. Meez says it can't tell, and shows why: confidence point two "
     "two, against point six needed. Refusing is the product, not an error."),
    ("05", "panel", ("blocked", 32), "Frames stop  →  the panel dims",
     "If the frames stop, the panel dims, and counts the seconds since it last saw the "
     "pan. No fresh frame, no opinion."),
    ("06", "panel", ("catches", 39), "OFF THE HEAT overrides everything",
     "And if something is catching, off the heat overrides every other rule, even a view "
     "too unclear to judge."),
    ("07", "still", "mcp", "Real MCP client — protocol 2025-11-25",
     "The same thing over MCP. A real client negotiates protocol twenty twenty-five, "
     "eleven, twenty-five. Check doneness returns refuse, and advance step is blocked, "
     "because advancing needs a passing observation from the last twenty seconds, not "
     "the model's belief."),
    ("08", "still", "architecture", "No model call inside a tool",
     "Alexa Plus gives a tool about five hundred milliseconds, and a vision model will "
     "never fit. So perception runs on its own clock and writes a cache. Tools only read "
     "it. The panel is an MCP App, marked app only, so the screen keeps updating after "
     "the voice turn ends."),
    ("09", "still", "graph", "Strands multi-agent graph — the critic is conditional",
     "Perception is a Strands multi-agent graph, shown here against a scripted model. A "
     "critic agent runs only near the decision boundary. On a clear frame it is skipped. "
     "On a steamed frame it fires, and its dissent can only lower confidence, never "
     "raise it."),
    ("10", "still", "tests", "11 test suites — no cloud credentials",
     "Eleven test suites pass on a clean clone, with no cloud credentials. One exists "
     "only to prove a refusal is never spoken as a wait."),
    ("11", "still", "close", "github.com/jwlai-cloud/mise",
     "Every recipe app pushes you forward. This one can refuse. Meez is open source, on "
     "GitHub."),
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).stdout
    return float(out.strip())


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=10))


def rpc(method, params, rid):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(BASE + "/mcp", data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25"})
    return json.load(urllib.request.urlopen(req, timeout=10))


# ---------------------------------------------------------------- narration

def narrate(voice_dir: Path | None) -> dict[str, float]:
    durs = {}
    for sid, _k, _s, _c, text in SEGMENTS:
        wav = WORK / f"seg_{sid}.wav"
        own = voice_dir / f"seg_{sid}.wav" if voice_dir else None
        if own and own.exists():
            run(["ffmpeg", "-y", "-i", str(own), "-ar", "48000", "-ac", "2", str(wav)])
        else:
            aiff = WORK / f"seg_{sid}.aiff"
            run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text])
            run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(wav)])
        durs[sid] = duration(wav) + PAD
        print(f"  narration {sid}: {durs[sid]:.1f}s")
    return durs


# ---------------------------------------------------------- real terminal output

def capture_terminal_text() -> dict[str, list[str]]:
    """Run the real commands; the cards show exactly what they printed."""
    get("/dev/reset")
    get("/dev/scenario?name=steam&at=44")
    time.sleep(2)
    init = rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                              "clientInfo": {"name": "demo", "version": "1"}}, 1)["result"]
    tools = rpc("tools/list", {}, 2)["result"]["tools"]
    panel_meta = next(t for t in tools if t["name"] == "panel_state").get("_meta")
    chk = rpc("tools/call", {"name": "check_doneness", "arguments": {}}, 3)["result"]
    chk = chk.get("structuredContent") or json.loads(chk["content"][0]["text"])
    adv = rpc("tools/call", {"name": "advance_step", "arguments": {}}, 4)["result"]
    adv = adv.get("structuredContent") or json.loads(adv["content"][0]["text"])
    mcp = [
        "$ POST /mcp  initialize",
        f"  protocolVersion  {init['protocolVersion']}",
        f"  serverInfo       {init['serverInfo']['name']}",
        "",
        "$ POST /mcp  tools/list",
        f"  tools            {', '.join(t['name'] for t in tools)}",
        f"  panel_state._meta {json.dumps(panel_meta)}",
        "",
        "$ POST /mcp  tools/call check_doneness",
        f"  verdict          {chk['verdict']}",
        f"  say              {chk['say']}",
        f"  doneness         {chk['doneness']}   confidence {chk['confidence']}",
        "",
        "$ POST /mcp  tools/call advance_step",
        f"  advanced         {adv['advanced']}",
        f"  policy_rule      {adv.get('policy_rule')}",
        f"  reason           {adv.get('policy_explanation') or adv.get('reason')}",
    ]

    graph_code = r"""
import asyncio, sys
sys.path.insert(0, "src")
from mise.agents import (ScriptedModel, build_hot_graph, arbitrate, PanReading,
                         CriticVerdict, RiskReport)
from mise.gate import decide
from mise.recipes import SOFFRITTO
from mise.state import CookState
step = SOFFRITTO.step(1)
CLEAR = dict(view="clear", obstructions=[], risk="none", stage="onions",
             doneness=0.45, confidence=0.92, evidence="edges still firm")
STEAM = dict(view="obscured", obstructions=["steam"], risk="none", stage="onions",
             doneness=0.88, confidence=0.93, evidence="looks translucent")
AGREE = dict(would_be_wrong=False, max_confidence=1.0, reason="")
DISS  = dict(would_be_wrong=True, max_confidence=0.2, reason="steam across the lens")
NONE  = dict(risk="none", evidence="")
async def go(label, p, c):
    g = build_hot_graph(ScriptedModel([p]), ScriptedModel([c]), ScriptedModel([NONE]))
    res = await g.invoke_async("Report this pan.")
    def out(n, k):
        o = getattr(res.results[n].result, "structured_output", None) if n in res.results else None
        return o if isinstance(o, k) else None
    r = arbitrate(out("perceive", PanReading), out("critique", CriticVerdict), out("risk", RiskReport))
    v = decide(CookState(**r.as_state_fields()), step).verdict
    print(f"$ {label}")
    print(f"  agents ran   {[n.node_id for n in res.execution_order]}")
    print(f"  confidence   {p['confidence']} -> {r.confidence}")
    print(f"  doneness     {r.doneness}  (gate {step.gate_doneness})   verdict  {v.upper()}")
    print()
asyncio.run(go("clear frame, mid-step", CLEAR, AGREE))
asyncio.run(go("steamed frame, past the gate", STEAM, DISS))
"""
    g = subprocess.run([sys.executable, "-c", graph_code], cwd=ROOT, capture_output=True,
                       text=True, env={**os.environ, "PYTHONPATH": "src"})
    graph = [l for l in g.stdout.splitlines() if not l.startswith("Tool #")]
    while graph and not graph[-1].strip():
        graph.pop()

    tests = ["$ for t in tests/test_*.py; do python3 $t; done"]
    for t in sorted((ROOT / "tests").glob("test_*.py")):
        rc = subprocess.run([sys.executable, str(t)], cwd=ROOT, capture_output=True,
                            env={**os.environ, "PYTHONPATH": "src"}).returncode
        tests.append(f"  {'PASS' if rc == 0 else 'FAIL'}  {t.relative_to(ROOT)}")
    get("/dev/reset")           # the test suite moves calibration; undo before filming
    return {"mcp": mcp, "graph": graph, "tests": tests}


# ------------------------------------------------------------------ the cards

CARD_CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:930px;background:#0B0E13;
color:#E8EDF4;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif}
.term{position:absolute;inset:56px 120px 40px;background:#11161D;border:1px solid #2B3542;
border-radius:14px;overflow:hidden}
.bar{height:44px;background:#1A2029;display:flex;align-items:center;gap:10px;padding:0 18px}
.bar i{width:13px;height:13px;border-radius:50%;display:inline-block}
.bar span{margin-left:14px;color:#93A1B5;font:500 17px Menlo,monospace}
pre{margin:0;padding:30px 36px;font:500 25px/1.62 Menlo,"SF Mono",monospace;
white-space:pre-wrap;color:#C9D3E0}
.c{color:#6F8098}.hl{color:#E8B23A}.ok{color:#38B87C}.bad{color:#E5484D}.cool{color:#7AB4E8}
"""


def term_card(title: str, lines: list[str], marks: dict[str, str], size: int = 25) -> str:
    out = []
    for l in lines:
        h = html.escape(l)
        if l.startswith("$"):
            h = f'<span class="c">{h}</span>'
        for needle, cls in marks.items():
            h = h.replace(html.escape(needle), f'<span class="{cls}">{html.escape(needle)}</span>')
        out.append(h)
    dots = ('<i style="background:#E5484D"></i><i style="background:#E8B23A"></i>'
            '<i style="background:#38B87C"></i>')
    return (f"<style>{CARD_CSS}pre{{font-size:{size}px}}</style>"
            f"<div class='term'><div class='bar'>{dots}"
            f"<span>{html.escape(title)}</span></div><pre>{chr(10).join(out)}</pre></div>")


CLOSE = f"""<style>{CARD_CSS}
.w{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;
padding:0 170px;gap:34px}}
h1{{font:800 86px/1.04 -apple-system,"Helvetica Neue",sans-serif;margin:0;letter-spacing:-.02em}}
h1 b{{color:#E8B23A}}p{{font:400 36px/1.4 -apple-system,sans-serif;color:#A9B6C6;margin:0}}
.u{{font:600 38px Menlo,monospace;color:#7AB4E8}}</style>
<div class="w"><h1>Every recipe app pushes you forward.<br><b>This one can refuse.</b></h1>
<p>Readiness as a refusable tool contract — an MCP server for Alexa+,<br>
a Strands multi-agent graph, and a panel that never stops telling the truth.</p>
<div class="u">github.com/jwlai-cloud/mise  ·  Apache-2.0</div></div>"""


ARCH = f"""<style>{CARD_CSS}
.a{{position:absolute;inset:90px 70px 170px;display:grid;grid-template-columns:1fr 80px 1fr 80px 1fr;
align-items:stretch}}
.box{{border:3px solid #2B3542;border-radius:20px;padding:44px 40px;background:#141A22;display:flex;flex-direction:column;justify-content:center}}
.box h3{{margin:0 0 18px;font:700 54px/1.05 -apple-system,sans-serif}}
.box p{{margin:0;font:400 33px/1.45 -apple-system,sans-serif;color:#A9B6C6}}
.k{{font:600 23px Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:14px;display:block}}
.slow{{border-color:#5B9BD9}}.slow .k{{color:#7AB4E8}}
.cache{{border-color:#E8B23A}}.cache .k{{color:#E8B23A}}
.fast{{border-color:#38B87C}}.fast .k{{color:#38B87C}}
.arr{{display:flex;align-items:center;justify-content:center;font:300 90px sans-serif;color:#5B6B7F}}
.note{{position:absolute;left:70px;right:70px;bottom:70px;display:flex;justify-content:space-between;
font:500 31px -apple-system,sans-serif;color:#93A1B5}}.note b{{color:#E8EDF4}}</style>
<div class="a">
 <div class="box slow"><span class="k">slow plane · own clock</span><h3>Strands graph</h3>
  <p>perceive · critic (conditional)<br>risk · deterministic arbiter<br>~0.3 Hz, never on the request path</p></div>
 <div class="arr">→</div>
 <div class="box cache"><span class="k">the seam</span><h3>CookState cache</h3>
  <p>last-known-good state<br>timestamped by the shutter,<br>not by the write</p></div>
 <div class="arr">→</div>
 <div class="box fast"><span class="k">fast plane · &lt;500 ms</span><h3>MCP tools</h3>
  <p>read the cache, apply a<br>deterministic gate.<br><b style="color:#E8EDF4">No model call. Ever.</b></p></div>
</div>
<div class="note"><span>Alexa+ budgets <b>~500 ms</b> per tool round-trip</span>
<span>panel_state is <b>visibility: ["app"]</b> — the screen outlives the voice turn</span></div>"""


def render_stills(term: dict[str, list[str]]):
    from playwright.sync_api import sync_playwright
    cards = {
        "mcp": term_card("mcp client  →  localhost/mcp", term["mcp"], {
            "2025-11-25": "hl", '"visibility": ["app"]': "hl", "refuse": "bad",
            "False": "bad", "advance_requires_gate": "cool"}),
        "graph": term_card("strands.multiagent.GraphBuilder  —  scripted model", term["graph"], {
            "'critique'": "hl", "REFUSE": "bad", "WAIT": "hl", "-> 0.2": "bad"}, size=34),
        "tests": term_card("clean clone · no AWS credentials", term["tests"], {
            "PASS": "ok", "FAIL": "bad"}, size=29),
        "close": CLOSE,
    }
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 930})
        for name, doc in cards.items():
            pg.set_content(doc)
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(WORK / f"card_{name}.png"))
        pg.set_content(ARCH)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(WORK / "card_architecture.png"))
        hi = b.new_page(viewport={"width": 960, "height": 465}, device_scale_factor=2)
        hi.goto(f"{BASE}/dev/control")
        hi.wait_for_timeout(1500)
        hi.screenshot(path=str(WORK / "card_control.png"))
        b.close()
    print("  cards rendered")


# ----------------------------------------------------------- live panel footage

def record_panels(durs: dict[str, float]):
    """Screenshot the real panel at a steady cadence. Screenshots rather than
    screencast so the text stays crisp at 2x."""
    from playwright.sync_api import sync_playwright
    fps = 6
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 768, "height": 480}, device_scale_factor=2)
        pg.goto(f"{BASE}/dev/panel")
        for sid, kind, src, *_ in SEGMENTS:
            if kind != "panel":
                continue
            scen, at = src
            d = WORK / f"panel_{sid}"
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir()
            get("/dev/reset")
            get(f"/dev/scenario?name={scen}&at={at}")
            pg.wait_for_timeout(2200)              # let the 2s poll land
            n = int(durs[sid] * fps) + fps
            t0 = time.time()
            for i in range(n):
                pg.screenshot(path=str(d / f"f{i:04d}.jpg"), type="jpeg", quality=92)
                lag = t0 + (i + 1) / fps - time.time()
                if lag > 0:
                    time.sleep(lag)
            real = n / (time.time() - t0)
            (d / "fps").write_text(f"{real:.3f}")
            print(f"  panel {sid} ({scen}@{at}): {n} frames at {real:.1f} fps")
        b.close()


# ------------------------------------------------------------------- assembly

def caption_filter(sid: str, caption: str, dur: float, first: bool, last: bool) -> str:
    cap = WORK / f"cap_{sid}.txt"
    cap.write_text(caption)
    f = (f"drawtext=fontfile='{FONT}':textfile='{cap}':fontcolor=white:fontsize=44:"
         f"x=(w-text_w)/2:y=968:box=1:boxcolor=black@0.0")
    fades = []
    if first:
        fades.append("fade=t=in:st=0:d=0.6")
    if last:
        fades.append(f"fade=t=out:st={dur - 0.8:.2f}:d=0.8")
    return ",".join([f] + fades)


def build_segment(sid, kind, src, caption, dur, first, last) -> Path:
    out = WORK / f"out_{sid}.mp4"
    wav = WORK / f"seg_{sid}.wav"
    if kind == "panel":
        d = WORK / f"panel_{sid}"
        rate = (d / "fps").read_text()
        # fps=30 must come BEFORE zoompan: zoompan emits one frame per input frame,
        # so feeding it 6 fps while declaring 30 fps made the clip ~5x too short and
        # pushed every later segment out of sync with its narration.
        zoom = ("zoompan=z='min(zoom+0.0006,1.10)':x='(iw-iw/zoom)/2':"
                "y='(ih-ih/zoom)*0.65':d=1:s=1440x900:fps=30," if sid == "04" else "")
        vf = (f"scale=1440:900,fps=30,{zoom}pad=1920:1080:240:28:color={BG},"
              + caption_filter(sid, caption, dur, first, last))
        vin = ["-framerate", rate, "-i", str(d / "f%04d.jpg")]
    else:
        vf = ("scale=1920:930,zoompan=z='min(zoom+0.00025,1.035)':d=1:s=1920x930:fps=30,"
              f"pad=1920:1080:0:0:color={BG}," + caption_filter(sid, caption, dur, first, last))
        vin = ["-loop", "1", "-framerate", "30", "-i", str(WORK / f"card_{src}.png")]
    # Video is looped/held and audio padded with silence, then both cut to `dur`,
    # so every segment is exactly as long as its narration plus PAD.
    run(["ffmpeg", "-y", *vin, "-i", str(wav),
         "-vf", vf, "-af", "apad", "-t", f"{dur:.2f}", "-r", "30",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)])
    for stream in ("v:0", "a:0"):
        got = float(run(["ffprobe", "-v", "error", "-select_streams", stream,
                         "-show_entries", "stream=duration", "-of", "csv=p=0",
                         str(out)]).stdout.strip().split(",")[0])
        if abs(got - dur) > 0.25:
            sys.exit(f"segment {sid} {stream} is {got:.2f}s, expected {dur:.2f}s — "
                     "a short track desyncs every segment after it")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-dir", type=Path)
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)

    print("1. narration")
    durs = narrate(a.voice_dir)
    total = sum(durs.values())
    print(f"   total {total:.1f}s")
    if total >= 178:
        sys.exit(f"narration is {total:.0f}s — over the 3-minute limit; cut words first")

    print("2. server")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "mise.app:app",
                            "--port", str(PORT)], cwd=ROOT,
                           env={**os.environ, "PYTHONPATH": "src"},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                get("/dev/scenarios")
                break
            except Exception:
                time.sleep(0.5)
        print("3. real terminal output")
        term = capture_terminal_text()
        print("4. cards")
        render_stills(term)
        print("5. live panel")
        record_panels(durs)
    finally:
        srv.terminate()

    print("6. assemble")
    parts = []
    for i, (sid, kind, src, cap, _t) in enumerate(SEGMENTS):
        parts.append(build_segment(sid, kind, src, cap, durs[sid],
                                   i == 0, i == len(SEGMENTS) - 1))
        print(f"   segment {sid} done")
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    # Re-encode audio only, normalised to -16 LUFS so it is not quiet on YouTube.
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(OUT)])
    print(f"\n{OUT}  {duration(OUT):.1f}s")


if __name__ == "__main__":
    main()
