#!/usr/bin/env python3
"""
VoiceForge - measurement system validation (MSA).

A control plan is worthless if the gauge cannot see the defect. This seeds
known defects into synthetic audio and checks that analysis.defects() catches
each one, while staying silent on a clean control clip.

Character counts are matched to clip length (13.7 chars per second, the rate
measured on the real engine) except in the deliberate duration case.

Usage: python3 tools/msa.py
"""

import array
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voiceforge import analysis  # noqa: E402

RATE = 24000
CHARS_PER_SEC = 13.7


def tone(seconds=2.0, amp=6000, freq=180):
    out = array.array("h")
    n = int(RATE * seconds)
    for i in range(n):
        env = min(1.0, i / (RATE * 0.05), (n - i) / (RATE * 0.05))
        out.append(int(amp * env * math.sin(2 * math.pi * freq * i / RATE)))
    return out


def tone_hard(seconds=0.5, amp=20000, freq=180):
    """Same tone starting at full amplitude, so a splice creates a real step."""
    out = array.array("h")
    for i in range(int(RATE * seconds)):
        out.append(int(amp * math.sin(2 * math.pi * freq * i / RATE + math.pi / 2)))
    return out


def pad(samples, lead=0.05, tail=0.05):
    out = array.array("h", [0] * int(RATE * lead))
    out.extend(samples)
    out.extend([0] * int(RATE * tail))
    return out


def build(tmp, name, samples):
    p = Path(tmp) / f"{name}.wav"
    analysis.write_wav(p, samples, RATE)
    return p


def main():
    with tempfile.TemporaryDirectory() as tmp:
        clips = {}
        clips["clean control"] = (build(tmp, "clean", pad(tone())), [], None)
        clips["silent file"] = (build(tmp, "silent", array.array("h", [0] * RATE * 2)), ["D1_EMPTY"], None)
        clips["too quiet"] = (build(tmp, "quiet", pad(tone(amp=400))), ["D2_LEVEL"], None)
        clips["clipped"] = (build(tmp, "hot", pad(tone(amp=32767))), ["D3_CLIPPING", "D2_LEVEL"], None)
        clips["silence padding"] = (build(tmp, "pad", pad(tone(1.0), lead=2.0, tail=3.0)), ["D4_SILENCE_PAD"], None)

        joined = pad(tone(1.0))
        boundary = len(joined)
        joined.extend(tone_hard(0.5))
        clips["join click"] = (build(tmp, "join", joined), ["D5_JOIN_CLICK"], [boundary])

        clips["duration out of spec"] = (
            build(tmp, "fast", pad(tone(0.5), 0.01, 0.01)), ["D6_DURATION"], None)

        print(f"{'seeded defect':<22}{'expected':<30}{'found':<30}{'ok'}")
        detected = 0
        for name, (path, expected, boundaries) in clips.items():
            samples, _, _ = analysis.read_wav(path)
            seconds = len(samples) / RATE
            chars = 400 if name == "duration out of spec" else max(1, int(seconds * CHARS_PER_SEC))
            m = analysis.analyze(path, text="x" * chars, chunk_boundaries=boundaries)
            found = analysis.defects(m)
            ok = all(e in found for e in expected)
            detected += 1 if ok else 0
            print(f"{name:<22}{','.join(expected) or 'none':<30}{','.join(found) or 'none':<30}{'PASS' if ok else 'FAIL'}")

        clean_path = clips["clean control"][0]
        samples, _, _ = analysis.read_wav(clean_path)
        clean_chars = int(len(samples) / RATE * CHARS_PER_SEC)
        false_pos = analysis.defects(analysis.analyze(clean_path, text="x" * clean_chars))
        print(f"\ndetection {detected}/{len(clips)}")
        print(f"false positives on clean control: {'none' if not false_pos else ', '.join(false_pos)}")


if __name__ == "__main__":
    main()
