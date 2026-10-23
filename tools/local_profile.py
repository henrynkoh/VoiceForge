#!/usr/bin/env python3
"""
VoiceForge - build the local voice profile inside the voicebox container.

Creates a profile, transcribes each recorded take with the container's own
Whisper, and attaches the sample with its transcript so the local clone has a
proper reference prompt.

Usage: python3 tools/local_profile.py
"""

import json
import mimetypes
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:17600"
PROFILE = "Henry - RD local"
SAMPLES = ROOT / "data/samples/henry-rd"


def call(path, data=None, ctype="application/json"):
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": ctype} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()
        return json.loads(body.decode()) if body[:1] in (b"{", b"[") else body


def multipart(fields, files):
    b = "----vf" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, p in files:
        ct = mimetypes.guess_type(p.name)[0] or "audio/wav"
        out += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{p.name}\"\r\n"
                f"Content-Type: {ct}\r\n\r\n").encode()
        out += p.read_bytes() + b"\r\n"
    out += f"--{b}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={b}"


def transcribe(path):
    raw, ct = multipart({"language": "en"}, [("file", path)])
    for _ in range(60):
        try:
            r = call("/transcribe", raw, ct)
        except Exception as e:
            print(f"    transcribe error: {e}")
            time.sleep(10)
            continue
        if isinstance(r, dict) and r.get("text"):
            return r["text"].strip()
        detail = r.get("detail") if isinstance(r, dict) else None
        if isinstance(detail, dict) and detail.get("downloading"):
            print("    waiting for whisper model download...")
            time.sleep(10)
            continue
        time.sleep(5)
    return ""


def main():
    existing = [p for p in call("/profiles") if p.get("name") == PROFILE]
    if existing:
        pid = existing[0]["id"]
        print(f"profile exists: {pid}")
    else:
        pid = call("/profiles", json.dumps({
            "name": PROFILE,
            "description": "Cloned in VoiceForge from RODE NT-USB takes",
            "language": "en",
            "voice_type": "cloned",
        }).encode())["id"]
        print(f"created profile: {pid}")

    samples = sorted(SAMPLES.glob("*.wav"))
    if not samples:
        sys.exit("no samples")
    for s in samples:
        print(f"  {s.name} ({s.stat().st_size/1e6:.1f} MB)")
        text = transcribe(s)
        if not text:
            print("    no transcript, skipped")
            continue
        raw, ct = multipart({"reference_text": text[:1000]}, [("file", s)])
        try:
            call(f"/profiles/{pid}/samples", raw, ct)
            print(f"    added with {len(text)} chars: {text[:70]}...")
        except Exception as e:
            print(f"    upload failed: {e}")
    print(f"PROFILE={pid}")
    (ROOT / "data/local_profile_id.txt").write_text(pid)


if __name__ == "__main__":
    main()
