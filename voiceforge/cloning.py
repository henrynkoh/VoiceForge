"""
VoiceForge - cloning.

Two providers behind one call:

  elevenlabs_ivc   upload samples, get a voice_id back, use it immediately.
                   No fine-tuning step; quality is decided by the samples.
  local_ref        keep the samples as a speaker prompt for a local engine
                   (voicebox / Chatterbox), which references them at inference.

Both are preceded by the same sample gate: a recording is measured before it is
allowed to become a clone, because a bad sample cannot be fixed downstream.
"""

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import analysis

SAMPLES_DIR = None  # set by app.py
ELEVEN_API = os.environ.get("VOICEFORGE_ELEVEN_API", "https://api.elevenlabs.io")

# A sample must clear these before it is worth cloning from.
SAMPLE_MIN_S = 5.0
SAMPLE_MAX_S = 300.0
SAMPLE_DEAD_RMS = -50.0   # below this there is no voice to lift
SAMPLE_QUIET_RMS = -30.0  # between dead and quiet: accept, then normalise up
SAMPLE_TARGET_RMS = -20.0
SAMPLE_MAX_CLIP = 0.001


def set_samples_dir(path):
    global SAMPLES_DIR
    SAMPLES_DIR = Path(path)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def _sample_dir(voice_key):
    d = SAMPLES_DIR / voice_key
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_sample(voice_key, wav_bytes, label=""):
    """Persist one recording and grade it. Returns the sample record."""
    d = _sample_dir(voice_key or "unsorted")
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.wav"
    path = d / name
    path.write_bytes(wav_bytes)
    m = analysis.analyze(path, text="")

    # A quiet take is a recording problem, not a reason to throw the take away:
    # lift it to target level before it becomes a clone sample.
    gain_db = 0.0
    raw_rms = m["rms_dbfs"]
    if SAMPLE_DEAD_RMS <= raw_rms < SAMPLE_QUIET_RMS:
        from . import pipeline as _pipeline
        samples, rate, channels = analysis.read_wav(path)
        lifted = _pipeline.normalize(analysis.to_mono(samples, channels),
                                     target_dbfs=SAMPLE_TARGET_RMS,
                                     ceiling_dbfs=-1.5)
        analysis.write_wav(path, lifted, rate)
        gain_db = round(SAMPLE_TARGET_RMS - raw_rms, 1)
        m = analysis.analyze(path, text="")

    defects = analysis.defects(m, spec={"sec_per_100chars_min": 0, "sec_per_100chars_max": 9999})

    gate = []
    if m["duration_s"] < SAMPLE_MIN_S:
        gate.append(f"too short ({m['duration_s']}s, need {SAMPLE_MIN_S}s+)")
    if m["duration_s"] > SAMPLE_MAX_S:
        gate.append(f"too long ({m['duration_s']}s)")
    if raw_rms < SAMPLE_DEAD_RMS:
        gate.append(f"almost silent ({raw_rms} dBFS)")
    if m["clipping_ratio"] > SAMPLE_MAX_CLIP:
        gate.append(f"clipping ({m['clipping_ratio']:.4f})")
    if m["lead_silence_s"] > 2.0:
        gate.append(f"long lead-in ({m['lead_silence_s']}s)")

    return {
        "gain_db": gain_db,
        "raw_rms_dbfs": raw_rms,
        "note": (f"your take was quiet ({raw_rms} dBFS) so it was lifted {gain_db} dB; "
                 "next time move a little closer for a cleaner clone") if gain_db else "",
        "id": name.removesuffix(".wav"),
        "voice_key": voice_key or "unsorted",
        "file": f"{voice_key or 'unsorted'}/{name}",
        "path": str(path),
        "label": label,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metrics": m,
        "qa_defects": defects,
        "gate": gate,
        "usable": not gate,
    }


def list_samples(voice_key=None):
    if SAMPLES_DIR is None or not SAMPLES_DIR.exists():
        return []
    out = []
    dirs = [_sample_dir(voice_key)] if voice_key else sorted(p for p in SAMPLES_DIR.iterdir() if p.is_dir())
    for d in dirs:
        for f in sorted(d.glob("*.wav")):
            m = analysis.analyze(f, text="")
            out.append({
                "id": f.stem,
                "voice_key": d.name,
                "file": f"{d.name}/{f.name}",
                "path": str(f),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime)),
                "metrics": m,
                "usable": (m["duration_s"] >= SAMPLE_MIN_S and m["rms_dbfs"] >= SAMPLE_DEAD_RMS
                           and m["clipping_ratio"] <= SAMPLE_MAX_CLIP),
            })
    return out


# --------------------------------------------------------------- providers
def _multipart(fields, files):
    """fields: dict[str,str]; files: list[(field_name, filename, bytes, mimetype)]."""
    boundary = "----voiceforge" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for field, filename, data, ctype in files:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                 f"filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def clone_elevenlabs(api_key, name, sample_paths, description="", labels=None):
    if not api_key:
        raise RuntimeError("no API key with voices_write")
    files = []
    for p in sample_paths:
        p = Path(p)
        ext = p.suffix.lower()
        ctype = "audio/wav" if ext == ".wav" else "audio/mpeg"
        files.append(("files", p.name, p.read_bytes(), ctype))
    if not files:
        raise RuntimeError("no sample files")
    fields = {"name": name}
    if description:
        fields["description"] = description
    if labels:
        fields["labels"] = json.dumps(labels)
    body, ctype = _multipart(fields, files)
    req = urllib.request.Request(
        f"{ELEVEN_API}/v1/voices/add",
        data=body,
        headers={"xi-api-key": api_key, "Content-Type": ctype},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"clone failed {e.code}: {e.read().decode(errors='replace')[:300]}")
    voice_id = data.get("voice_id")
    if not voice_id:
        raise RuntimeError(f"clone returned no voice_id: {data}")
    return voice_id


def clone_local_ref(name, sample_paths, engine="voicebox"):
    """Local engines keep the samples as a speaker prompt; nothing is trained."""
    if not sample_paths:
        raise RuntimeError("no sample files")
    return {
        "engine": engine,
        "ref": name,
        "samples": [str(p) for p in sample_paths],
        "note": "local engine references these samples at inference time",
    }


def delete_elevenlabs_voice(api_key, voice_id):
    req = urllib.request.Request(
        f"{ELEVEN_API}/v1/voices/{voice_id}",
        headers={"xi-api-key": api_key},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status
