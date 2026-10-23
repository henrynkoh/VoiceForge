#!/usr/bin/env python3
"""Render one chapter by exact character count and save it under its chapter name."""
import json, re, socket, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BOOK = ROOT / "audiobooks/en-only"
HIST = ROOT / "data/generations.jsonl"

want = [int(x) for x in sys.argv[1].split(",")]
text = (BOOK / "rightly-dividing-30min-en-only.md").read_text()
chs = {}
for part in re.split(r"\n## ", text)[1:]:
    title, _, body = part.partition("\n")
    chs[int(re.match(r"Chapter\s+(\d+)", title).group(1))] = (title.strip(), body.replace("---", "").strip())

def hist():
    return [json.loads(l) for l in HIST.read_text().splitlines() if l.strip()]

deadline = time.time() + 520
for n in want:
    title, body = chs[n]
    L = len(body)
    fired = time.time()
    if time.time() > deadline:
        print("deadline"); break
    req = urllib.request.Request("http://127.0.0.1:60065/api/generate",
        data=json.dumps({"voice_id": "henry-local", "engine": "voicebox", "language": "en",
                         "text": body, "max_chunk_chars": 800, "crossfade_ms": 50,
                         "normalize": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    print(f"chapter {n}: {L} chars fired", flush=True)
    try:
        urllib.request.urlopen(req, timeout=4)
    except (socket.timeout, TimeoutError, OSError):
        pass
    while time.time() < deadline:
        hit = [r for r in hist() if r["chars"] == L and r["engine"] == "voicebox"]
        if hit:
            rec = hit[-1]
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
            out = BOOK / "audio" / f"{n:02d}-{slug}.wav"
            out.write_bytes((ROOT / "data/audio" / rec["file"]).read_bytes())
            print(f"chapter {n}: {rec['metrics']['duration_s']}s, {rec['chars']} chars, defects {rec['defects'] or 'none'}", flush=True)
            break
        time.sleep(5)
    else:
        print("deadline while waiting"); break
