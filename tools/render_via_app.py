#!/usr/bin/env python3
"""Render missing chapters by driving the running VoiceForge server.

The server outlives the shell that asks for a chapter, so a 10-minute render is
safe here: fire the request, let the client give up, then wait for the chapter
to show up in data/generations.jsonl and copy it to its chapter name.
"""
import argparse, json, re, socket, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
BOOK = Path(__file__).resolve().parent.parent / "audiobooks/en-only"
APP = "http://127.0.0.1:60065"
HIST = Path(__file__).resolve().parent.parent / "data/generations.jsonl"


def chapters():
    text = (BOOK / "rightly-dividing-30min-en-only.md").read_text()
    out = []
    for part in re.split(r"\n## ", text)[1:]:
        title, _, body = part.partition("\n")
        body = body.replace("---", "").strip()
        if body:
            out.append({"title": title.strip(), "text": body,
                        "n": int(re.match(r"Chapter\s+(\d+)", title).group(1))})
    return out


def history():
    if not HIST.exists():
        return []
    return [json.loads(l) for l in HIST.read_text().splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", type=int, default=540)
    ap.add_argument("--voice", default="henry-local")
    args = ap.parse_args()
    t0 = time.time()
    for c in chapters():
        dest = list((BOOK / "audio").glob(f"{c['n']:02d}-*.wav"))
        if dest:
            continue
        if time.time() - t0 > args.deadline:
            print("deadline reached, stopping"); return
        # a chapter may already be rendering or finished from an earlier run
        recent = [r for r in history() if r["chars"] == len(c["text"]) and r.get("engine") == "voicebox"]
        inflight = bool(recent) and (time.time() - time.mktime(time.strptime(recent[-1]["created_at"], "%Y-%m-%dT%H:%M:%S"))) < 900
        before = len(history())
        body = json.dumps({"voice_id": args.voice, "engine": "voicebox", "language": "en",
                           "text": c["text"], "max_chunk_chars": 800,
                           "crossfade_ms": 50, "normalize": True}).encode()
        req = urllib.request.Request(f"{APP}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        if inflight:
            print(f"chapter {c['n']}: already rendering, waiting", flush=True)
            before -= 1
        else:
            print(f"chapter {c['n']}: {len(c['text'])} chars, fired", flush=True)
            try:
                urllib.request.urlopen(req, timeout=4)
            except (socket.timeout, TimeoutError, OSError):
                pass  # expected: the render is longer than the client waits
        while time.time() - t0 < args.deadline:
            recs = history()
            if len(recs) > before:
                rec = recs[-1]
                src = Path("data/audio") / rec["file"]
                slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:48]
                out = BOOK / "audio" / f"{c['n']:02d}-{slug}.wav"
                out.write_bytes(src.read_bytes())
                m = rec["metrics"]
                print(f"chapter {c['n']}: {m['duration_s']:.1f}s audio, {rec['chars']} chars, "
                      f"{m['chars_per_sec']} c/s, defects {rec['defects'] or 'none'}", flush=True)
                break
            time.sleep(5)
        else:
            print("deadline in wait, stopping"); return
    print("all chapters present")


if __name__ == "__main__":
    main()
