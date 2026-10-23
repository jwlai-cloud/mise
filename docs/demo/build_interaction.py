"""Build the interaction demo: a cook, a simulated Alexa+, and the real Mise server.

Nothing on screen is mocked except Alexa herself. Every frame is POSTed to the
real /ingest and judged by a real vision model (Gemini 2.5 Flash through Mise's
perception schema and confidence clamp). Every tool call is a real JSON-RPC
request to the real /mcp endpoint, and Alexa's spoken line is the `say` field
that came back. The Echo Show panel is the real ui://mise/panel page polling
the same process.

Two passes. The first runs the story once to learn what the server actually
says, so the voices can be synthesised from real responses. The second records
it, re-running every call live; the vision cache makes repeated frames free and
identical, so the second pass hears the same answers.

    MISE_GCLOUD_ACCOUNT=you@example.com MISE_GCLOUD_PROJECT=your-project \\
      python3 docs/demo/build_interaction.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STILLS = HERE / "stills"
WORK = HERE / "raw" / "interaction"
OUT = HERE / "mise-interaction.mp4"
PORT = 8997
BASE = f"http://127.0.0.1:{PORT}"

VOICES = {
    "narrator": ("Kore", "Narrate a short product demo. Warm, clear and confident, "
                         "measured pace, not salesy."),
    "cook": ("Puck", "A home cook at the stove talking to a smart speaker. Casual, "
                     "a little impatient, natural."),
    "alexa": ("Aoede", "A friendly voice assistant answering a cook. Calm, concise, "
                       "helpful."),
}

# The story. ("frame", name) posts a still; ("cook", text) and ("narrator", text)
# speak; ("call", tool) makes a real MCP call and Alexa speaks its `say`;
# ("hold", s) lets the panel catch up on camera.
STORY = [
    ("beat", "1 / 5 · the question"),
    ("frame", "f2_soft"),
    ("narrator", "This is Meez. A phone watches the pan, a vision model reads each frame, "
                 "and Alexa asks a real MCP server whether the cook can move on."),
    ("cook", "Alexa, can I add the garlic yet?"),
    ("call", "check_doneness"),
    ("narrator", "Well under the gate of point eight. The answer is wait, with a time "
                 "estimate, not a guess."),
    ("beat", "2 / 5 · steam on the lens"),
    ("frame", "f3_steam"),
    ("hold", 1.5),
    ("cook", "How about now?"),
    ("call", "check_doneness"),
    ("narrator", "Steam. The model still offered a confidence, but it admitted the "
                 "obstruction, so the clamp caps it at point three five. "
                 "Meez refuses to judge rather than guess."),
    ("beat", "3 / 5 · closer"),
    ("frame", "f4b_done"),
    ("hold", 1.5),
    ("cook", "Now?"),
    ("call", "check_doneness"),
    ("narrator", "Closer, still under the gate, and it won't round up. A second not-yet "
                 "inside two minutes is spoken short. The panel keeps the detail."),
    ("beat", "4 / 5 · trying to skip"),
    ("cook", "Alexa, just go to the next step."),
    ("call", "advance_step"),
    ("narrator", "The skip is refused at the tool boundary. No passing observation, "
                 "no next step, whatever the assistant is asked."),
    ("beat", "5 / 5 · nobody asked"),
    ("frame", "f5_smoke"),
    ("hold", 3.5),
    ("narrator", "Smoke. Nobody asked. The panel polls on its own clock, and danger is "
                 "never rate-limited or confidence-gated."),
    ("cook", "Alexa?"),
    ("call", "check_doneness"),
    ("hold", 1.0),
    ("close", None),
    ("narrator", "Every recipe app pushes you forward. This one can refuse."),
    ("hold", 1.5),
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).stdout
    return float(out.strip().split(",")[0])


def http(path, data=None, headers=None, timeout=60):
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def ingest(name):
    return http("/ingest", (STILLS / f"{name}.jpg").read_bytes(),
                {"Content-Type": "image/jpeg"})


def call(tool, rid):
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": tool, "arguments": {}}}).encode()
    out = http("/mcp", body, {"Content-Type": "application/json",
                              "Accept": "application/json, text/event-stream",
                              "MCP-Protocol-Version": "2025-11-25"}, timeout=10)
    res = out["result"]
    return res.get("structuredContent") or json.loads(res["content"][0]["text"])


def reset():
    http("/dev/reset")
    http("/dev/start?slug=soffritto-demo&step=1")


# ------------------------------------------------------------------- voices

def tts(role: str, text: str) -> Path:
    """Gemini-TTS via Cloud Text-to-Speech, cached by voice and text."""
    voice, style = VOICES[role]
    wav = WORK / f"{role}-{hashlib.sha1((voice + text).encode()).hexdigest()[:10]}.wav"
    if wav.exists():
        return wav
    acct, proj = os.environ["MISE_GCLOUD_ACCOUNT"], os.environ["MISE_GCLOUD_PROJECT"]
    token = run(["gcloud", "auth", "print-access-token", "--account", acct]).stdout.strip()
    body = json.dumps({"input": {"prompt": style, "text": text},
                       "voice": {"languageCode": "en-US", "name": voice,
                                 "modelName": "gemini-2.5-pro-tts"},
                       "audioConfig": {"audioEncoding": "LINEAR16",
                                       "sampleRateHertz": 24000}}).encode()
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize", data=body,
        headers={"Authorization": f"Bearer {token}", "x-goog-user-project": proj,
                 "Content-Type": "application/json"})
    raw = WORK / (wav.stem + ".24k.wav")
    raw.write_bytes(base64.b64decode(
        json.load(urllib.request.urlopen(req, timeout=120))["audioContent"]))
    run(["ffmpeg", "-y", "-i", str(raw), "-ar", "48000", "-ac", "2", str(wav)])
    return wav


# ------------------------------------------------------------------ pass 1

def rehearse() -> list[str]:
    """Run the story once, unrecorded, and return what Alexa will say."""
    reset()
    said = []
    for i, (kind, arg) in enumerate(STORY):
        if kind == "frame":
            r = ingest(arg)
            print(f"  {arg}: {r.get('model_raw', {}).get('confidence')} -> "
                  f"{r.get('reading', {}).get('confidence')}")
        elif kind == "call":
            said.append(alexa_line(arg, call(arg, i)))
            print(f"  {arg}: {said[-1]}")
    return said


def alexa_line(tool, resp):
    # advance_step has no `say`; Alexa relays its reason, which is what the
    # server would speak through check_doneness anyway.
    return resp.get("say") or resp.get("reason") or ""


# ------------------------------------------------------------------ pass 2

def record(said: list[str]):
    from playwright.sync_api import sync_playwright

    shots = WORK / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    for f in shots.glob("*.jpg"):
        f.unlink()
    ui: queue.Queue = queue.Queue()      # JS for the main thread to evaluate
    audio: list[tuple[float, Path]] = []
    done = threading.Event()
    current = {"frame": None}

    def js(expr):
        ui.put(expr)

    def keep_fresh():
        # The gate refuses a view older than 15 s. A real phone posts every few
        # seconds; so does this.
        while not done.is_set():
            if current["frame"]:
                try:
                    ingest(current["frame"])
                except Exception:
                    pass
            done.wait(4)

    def speak(role, text, t0):
        wav = tts(role, text)
        audio.append((time.time() - t0, wav))
        if role != "narrator":
            js(f"stage.{role}({json.dumps(text)})")
        else:
            js(f"stage.sub({json.dumps(text)})")
        time.sleep(duration(wav) + 0.35)
        if role == "narrator":
            js("stage.sub('')")

    def direct(t0):
        lines = iter(said)
        time.sleep(1.0)
        for i, (kind, arg) in enumerate(STORY):
            if kind == "beat":
                js(f"stage.beat({json.dumps(arg)})")
            elif kind == "frame":
                js(f"stage.frame('stills/{arg}_hd.jpg'); stage.flow(['n-ingest']); "
                   "stage.posting(true)")
                current["frame"] = arg
                r = ingest(arg)
                time.sleep(0.5)
                js("stage.flow(['n-ingest','n-model'])")
                time.sleep(0.6)
                js(f"stage.reading({json.dumps(r['model_raw'])}, {json.dumps(r['reading'])}); "
                   "stage.flow(['n-model','n-clamp'])")
                time.sleep(0.6)
                js("stage.flow(['n-cache']); stage.posting(false)")
            elif kind == "cook" or kind == "narrator":
                speak(kind, arg, t0)
            elif kind == "call":
                js("stage.flow(['n-cache','n-gate'])")
                resp = call(arg, 100 + i)
                js(f"stage.tool({json.dumps(arg)}, {{}}, {json.dumps(resp)})")
                time.sleep(0.5)
                line = next(lines)
                got = alexa_line(arg, resp)
                if got != line:
                    print(f"  ! live answer drifted from rehearsal: {got!r} vs {line!r}")
                speak("alexa", got, t0)
                js("stage.flow([])")
            elif kind == "hold":
                time.sleep(arg)
            elif kind == "close":
                js("stage.close(true)")
        done.set()

    reset()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        # Serve the stage from the server's origin so its host bridge can reach /mcp.
        page.route(f"{BASE}/stage/**", lambda route: route.fulfill(
            path=str(HERE / route.request.url.split("/stage/", 1)[1])))
        page.goto(f"{BASE}/stage/stage.html")
        page.evaluate("stage.panel('/dev/panel')")
        page.wait_for_timeout(2500)
        t0 = time.time()
        threading.Thread(target=direct, args=(t0,), daemon=True).start()
        threading.Thread(target=keep_fresh, daemon=True).start()
        stamps = []
        n = 0
        while not done.is_set():
            while not ui.empty():
                page.evaluate(ui.get())
            path = shots / f"{n:05d}.jpg"
            page.screenshot(path=str(path), type="jpeg", quality=90)
            stamps.append((time.time() - t0, path))
            n += 1
        browser.close()
    print(f"  {n} shots over {stamps[-1][0]:.1f}s ({n / stamps[-1][0]:.1f} fps)")
    return stamps, audio


def assemble(stamps, audio):
    # Variable-rate screenshots -> constant 30 fps via the concat demuxer.
    lst = WORK / "shots.txt"
    with lst.open("w") as f:
        for (t, path), (t_next, _) in zip(stamps, stamps[1:] + [(stamps[-1][0] + 0.1, None)]):
            f.write(f"file '{path}'\nduration {max(t_next - t, 0.001):.4f}\n")
        f.write(f"file '{stamps[-1][1]}'\n")
    video = WORK / "video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18",
         "-preset", "medium", str(video)])
    # Every voice clip placed at the moment it started on screen.
    inputs, chains = [], []
    for k, (t, wav) in enumerate(audio):
        inputs += ["-i", str(wav)]
        ms = max(int(t * 1000), 0)
        chains.append(f"[{k + 1}:a]adelay={ms}|{ms}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(audio)))
    graph = ";".join(chains) + f";{mix}amix=inputs={len(audio)}:normalize=0," \
                               "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    run(["ffmpeg", "-y", "-i", str(video), *inputs, "-filter_complex", graph,
         "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(OUT)])
    print(f"  wrote {OUT.relative_to(ROOT)}  {duration(OUT):.1f}s")


def main():
    for var in ("MISE_GCLOUD_ACCOUNT", "MISE_GCLOUD_PROJECT"):
        if not os.environ.get(var):
            sys.exit(f"needs {var} (Gemini perception and TTS)")
    WORK.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), MISE_VISION_BACKEND="gemini")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "mise.app:app",
                               "--port", str(PORT), "--log-level", "warning"],
                              cwd=ROOT, env=env)
    try:
        for _ in range(60):
            try:
                http("/dev/state")
                break
            except Exception:
                time.sleep(0.5)
        print("rehearsal (real server, real model)")
        said = rehearse()
        print("voices")
        for kind, arg in STORY:
            if kind in ("cook", "narrator"):
                tts(kind, arg)
        for line in said:
            tts("alexa", line)
        print("recording")
        stamps, audio = record(said)
        print("assembling")
        assemble(stamps, audio)
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
