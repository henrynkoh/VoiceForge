"""
VoiceForge - audio quality analysis.

Pure standard library. Reads WAV (16-bit PCM), returns the measurements the
Six Sigma control plan needs: level, clipping, silence, clicks, speech rate.

Every number here is a defect opportunity. See docs/SIXSIGMA.md.
"""

import array
import math
import wave
from pathlib import Path

FULL_SCALE = 32768.0
SILENCE_DBFS = -45.0
CLIP_LEVEL = 0.999
CLICK_JUMP = 0.35  # fraction of full scale between adjacent samples


def read_wav(path):
    """Return (samples: array('h'), sample_rate, channels)."""
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        rate = w.getframerate()
        width = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")
    data = array.array("h")
    data.frombytes(frames)
    return data, rate, channels


def write_wav(path, samples, rate, channels=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())


def to_mono(samples, channels):
    if channels == 1:
        return samples
    out = array.array("h")
    for i in range(0, len(samples) - channels + 1, channels):
        out.append(int(sum(samples[i:i + channels]) / channels))
    return out


def _db(amplitude):
    if amplitude <= 0:
        return -120.0
    return 20.0 * math.log10(amplitude)


def analyze(path, text="", chunk_boundaries=None, spec=None):
    """Measure one generated file.

    chunk_boundaries: optional list of sample indices where chunks were joined,
    used to count join clicks separately from speech-internal transients.
    """
    spec = spec or {}
    samples, rate, channels = read_wav(path)
    mono = to_mono(samples, channels)
    n = len(mono)
    if n == 0:
        return {
            "duration_s": 0.0, "peak_dbfs": -120.0, "rms_dbfs": -120.0,
            "clipping_ratio": 0.0, "silence_ratio": 1.0,
            "lead_silence_s": 0.0, "tail_silence_s": 0.0,
            "sec_per_100chars": None, "chars_per_sec": None,
            "join_clicks": 0, "internal_clicks": 0, "dc_offset": 0.0,
            "empty": True,
        }

    peak = 0
    clipped = 0
    sq = 0
    silent = 0
    floor = FULL_SCALE * (10 ** (SILENCE_DBFS / 20.0))
    for s in mono:
        a = s if s >= 0 else -s
        if a > peak:
            peak = a
        if a >= CLIP_LEVEL * FULL_SCALE:
            clipped += 1
        if a < floor:
            silent += 1
        sq += s * s

    rms = math.sqrt(sq / n)
    dc = sum(mono) / n

    def first_voice(step):
        idx = range(n) if step > 0 else range(n - 1, -1, -1)
        for i in idx:
            if abs(mono[i]) >= floor:
                return i
        return None

    lead_idx = first_voice(1)
    tail_idx = first_voice(-1)
    lead_s = (lead_idx / rate) if lead_idx is not None else n / rate
    tail_s = ((n - 1 - tail_idx) / rate) if tail_idx is not None else n / rate

    jump_limit = CLICK_JUMP * FULL_SCALE
    boundaries = set()
    if chunk_boundaries:
        for b in chunk_boundaries:
            boundaries.add(b)

    join_clicks = 0
    internal_clicks = 0
    prev = mono[0]
    for i in range(1, n):
        cur = mono[i]
        d = cur - prev
        if d < 0:
            d = -d
        if d > jump_limit:
            if any(abs(i - b) <= int(0.005 * rate) for b in boundaries):
                join_clicks += 1
            else:
                internal_clicks += 1
        prev = cur

    duration = n / rate
    chars = len(text.strip())
    return {
        "duration_s": round(duration, 3),
        "peak_dbfs": round(_db(peak / FULL_SCALE), 2),
        "rms_dbfs": round(_db(rms / FULL_SCALE), 2),
        "clipping_ratio": round(clipped / n, 6),
        "silence_ratio": round(silent / n, 4),
        "lead_silence_s": round(lead_s, 3),
        "tail_silence_s": round(tail_s, 3),
        "sec_per_100chars": round(duration / chars * 100, 2) if chars else None,
        "chars_per_sec": round(chars / duration, 2) if duration else None,
        "join_clicks": join_clicks,
        "internal_clicks": internal_clicks,
        "dc_offset": round(dc / FULL_SCALE, 5),
        "empty": peak < floor,
    }


DEFAULT_SPEC = {
    "rms_dbfs_min": -34.0,
    "rms_dbfs_max": -10.0,
    "clipping_ratio_max": 0.0005,
    "lead_silence_max_s": 1.2,
    "tail_silence_max_s": 2.0,
    "join_clicks_max": 0,
    "sec_per_100chars_min": 3.0,
    "sec_per_100chars_max": 18.0,  # Korean reads ~15, English ~7.7
}


def defects(metrics, spec=None):
    """Return the list of defect codes for one generation (Six Sigma unit)."""
    sp = dict(DEFAULT_SPEC)
    if spec:
        sp.update(spec)
    out = []
    if metrics.get("empty"):
        return ["D1_EMPTY"]
    if metrics["rms_dbfs"] < sp["rms_dbfs_min"] or metrics["rms_dbfs"] > sp["rms_dbfs_max"]:
        out.append("D2_LEVEL")
    if metrics["clipping_ratio"] > sp["clipping_ratio_max"]:
        out.append("D3_CLIPPING")
    if metrics["lead_silence_s"] > sp["lead_silence_max_s"] or metrics["tail_silence_s"] > sp["tail_silence_max_s"]:
        out.append("D4_SILENCE_PAD")
    if metrics["join_clicks"] > sp["join_clicks_max"]:
        out.append("D5_JOIN_CLICK")
    rate = metrics.get("sec_per_100chars")
    if rate is not None and not (sp["sec_per_100chars_min"] <= rate <= sp["sec_per_100chars_max"]):
        out.append("D6_DURATION")
    return out


def spec_snapshot():
    return dict(DEFAULT_SPEC)
