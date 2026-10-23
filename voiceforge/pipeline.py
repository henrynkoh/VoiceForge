"""
VoiceForge - chunking and audio assembly.

The splitter is a port of the algorithm in voicebox's
backend/utils/chunked_tts.py (MIT). Priority: sentence end that is not an
abbreviation or inside a [tag] -> clause boundary -> whitespace -> hard cut.
Same rules here so that A/B numbers are comparable to upstream.
"""

import array
import math
import re

DEFAULT_MAX_CHUNK_CHARS = 800
DEFAULT_CROSSFADE_MS = 50

_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "blvd", "inc",
    "ltd", "corp", "dept", "est", "approx", "vs", "etc", "e.g", "i.e",
    "a.m", "p.m", "u.s", "u.s.a", "u.k",
})
_PARA_TAG_RE = re.compile(r"\[[^\]]*\]")


def split_text(text, max_chars=DEFAULT_MAX_CHUNK_CHARS):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        remaining = remaining.lstrip()
        if not remaining:
            break
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        segment = remaining[:max_chars]
        pos = _last_sentence_end(segment)
        if pos == -1:
            pos = _last_clause_boundary(segment)
        if pos == -1:
            pos = segment.rfind(" ")
        if pos == -1:
            pos = _safe_hard_cut(segment)
        chunk = remaining[: pos + 1].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[pos + 1:]
    return chunks


def _last_sentence_end(text):
    best = -1
    for m in re.finditer(r"[.!?](?:\s|$)", text):
        pos = m.start()
        before = text[:pos]
        m2 = re.search(r"([A-Za-z.]+)$", before)
        word = (m2.group(1) if m2 else "").lower().strip(".")
        if word in _ABBREVIATIONS:
            continue
        if _inside_tag(text, pos):
            continue
        best = pos
    for ch in "。！？":
        idx = text.rfind(ch)
        if idx > best:
            best = idx
    return best


def _last_clause_boundary(text):
    best = -1
    for ch in ";:—,":
        idx = text.rfind(ch)
        if idx > best:
            best = idx
    return best


def _inside_tag(text, pos):
    for m in _PARA_TAG_RE.finditer(text):
        if m.start() <= pos <= m.end():
            return True
    return False


def _safe_hard_cut(segment):
    for m in _PARA_TAG_RE.finditer(segment):
        if m.start() < len(segment) - 1 <= m.end():
            return m.start() - 1
    return len(segment) - 1


def crossfade_concat(chunks, rate, crossfade_ms=DEFAULT_CROSSFADE_MS):
    """Concatenate int16 chunks with a short linear crossfade.

    Returns (samples, boundaries) where boundaries are sample indices of joins.
    """
    if not chunks:
        return array.array("h"), []
    fade = int(rate * max(0, crossfade_ms) / 1000)
    result = array.array("h", chunks[0])
    boundaries = []
    for chunk in chunks[1:]:
        if fade <= 0 or len(result) < fade or len(chunk) < fade:
            boundaries.append(len(result))
            result.extend(chunk)
            continue
        overlap = min(fade, len(result), len(chunk))
        start = len(result) - overlap
        for i in range(overlap):
            w = i / overlap
            mixed = int(result[start + i] * (1 - w) + chunk[i] * w)
            result[start + i] = max(-32768, min(32767, mixed))
        boundaries.append(start + overlap // 2)
        result.extend(chunk[overlap:])
    return result, boundaries


def normalize(samples, target_dbfs=-16.0, ceiling_dbfs=-1.0):
    """Scale to a target RMS, never letting the peak cross the ceiling."""
    if not len(samples):
        return samples
    sq = 0
    peak = 0
    for s in samples:
        sq += s * s
        if abs(s) > peak:
            peak = abs(s)
    if peak == 0:
        return samples
    rms = math.sqrt(sq / len(samples))
    if rms == 0:
        return samples
    target = 32768.0 * (10 ** (target_dbfs / 20.0))
    ceiling = 32768.0 * (10 ** (ceiling_dbfs / 20.0))
    gain = target / rms
    if peak * gain > ceiling:
        gain = ceiling / peak
    out = array.array("h", bytes(2 * len(samples)))
    for i, s in enumerate(samples):
        v = int(s * gain)
        out[i] = max(-32768, min(32767, v))
    return out


def resample(samples, src_rate, dst_rate):
    """Linear resample, so pieces rendered by different engines can be joined."""
    if not samples or src_rate == dst_rate:
        return samples
    ratio = dst_rate / float(src_rate)
    n = int(len(samples) * ratio)
    out = array.array("h", bytes(2 * n))
    last = len(samples) - 1
    for i in range(n):
        pos = i / ratio
        j = int(pos)
        if j >= last:
            out[i] = samples[last]
            continue
        frac = pos - j
        a = samples[j]
        out[i] = int(a + (samples[j + 1] - a) * frac)
    return out
