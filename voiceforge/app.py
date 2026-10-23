#!/usr/bin/env python3
"""
VoiceForge - a local-first text-to-speech studio built by reverse-engineering
voicebox (github.com/jamiepine/voicebox, MIT) and putting it under Six Sigma
control.

Run:  python3 -m voiceforge.app          (from the project folder)
      or double-click VoiceForge.command
"""

import json
import os
import re
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from voiceforge import analysis, cloning, engines, pipeline, sixsigma
else:
    from . import analysis, cloning, engines, pipeline, sixsigma

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("VOICEFORGE_DATA", ROOT / "data"))
AUDIO = DATA / "audio"
SAMPLES = DATA / "samples"
VOICES = DATA / "voices.json"
HISTORY = DATA / "generations.jsonl"
PORT = int(os.environ.get("VOICEFORGE_PORT", 8777))

SEED_VOICES = [
    {
        "id": "henry-rd",
        "name": "Henry - RD Narration",
        "engine": "elevenlabs",
        "ref": "oNev1aUqmmy2JTVur0DD",
        "language": "en",
        "note": "cloned 2026-10-21 from the RODE NT-USB sessions",
    },
    {
        "id": "probe",
        "name": "QA probe (synthetic)",
        "engine": "tone",
        "ref": "probe",
        "language": "en",
        "note": "measurement harness only, not a real voice",
    },
]


# ------------------------------------------------------------------ storage
def ensure_dirs():
    DATA.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    cloning.set_samples_dir(SAMPLES)
    if not VOICES.exists():
        VOICES.write_text(json.dumps(SEED_VOICES, indent=2))


def load_voices():
    ensure_dirs()
    try:
        return json.loads(VOICES.read_text())
    except Exception:
        return list(SEED_VOICES)


def save_voices(voices):
    VOICES.write_text(json.dumps(voices, indent=2))


def load_history(limit=200):
    ensure_dirs()
    if not HISTORY.exists():
        return []
    rows = []
    with HISTORY.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-limit:]


def append_history(record):
    with HISTORY.open("a") as f:
        f.write(json.dumps(record) + "\n")


def slug(text, fallback="clip"):
    words = re.sub(r"[^A-Za-z0-9가-힣\s-]", "", text or "").split()
    return ("-".join(words[:5]).lower() or fallback)[:48]


# --------------------------------------------------------------- generation
def voices_for_engine(voices, engine_name):
    return [v for v in voices if (v.get("engine") or "elevenlabs") == engine_name]


def resolve_pair(voices, voice, engine_name):
    """Return (voice, note) that actually works for this engine.

    The engine and the voice have to agree: an ElevenLabs voice_id sent to the
    local bridge is meaningless. Instead of failing, fall back to a library
    voice that belongs to the requested engine and say so.
    """
    if voice is None:
        raise ValueError("unknown voice_id")
    if (voice.get("engine") or "elevenlabs") == engine_name:
        return voice, ""
    candidates = voices_for_engine(voices, engine_name)
    if not candidates:
        names = ", ".join(sorted({v.get("engine") or "elevenlabs" for v in voices})) or "none"
        raise ValueError(
            f"the {engine_name} engine has no voice in the library yet. "
            f"Voices you have belong to: {names}. Add one under \"Add a voice\", "
            "or switch the engine to match the voice you picked.")
    same_lang = [v for v in candidates if (v.get("language") or "en") == (voice.get("language") or "en")]
    pick = (same_lang or candidates)[0]
    return pick, (f"engine {engine_name} cannot use {voice.get('name')} "
                  f"(that voice belongs to {voice.get('engine')}), so {pick.get('name')} was used instead")


HANGUL = ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F))


def _script_of(ch):
    for lo, hi in HANGUL:
        if lo <= ord(ch) <= hi:
            return "ko"
    if ch.isalpha():
        return "en"
    return ""


def split_by_script(text):
    """Split text into runs of one script, so Korean and English can go to
    different engines. Punctuation and digits stay with the current run."""
    runs, buf, cur = [], [], ""
    for ch in text:
        s = _script_of(ch)
        if s and s != cur:
            if "".join(buf).strip():
                runs.append((cur or "en", "".join(buf)))
            buf, cur = [], s
        if s:
            cur = s
        buf.append(ch)
    if "".join(buf).strip():
        runs.append((cur or "en", "".join(buf)))
    if not runs:
        return [("en", text)]
    # a two-word run of one language in the middle of another is a recipe for a
    # one-word chunk; fold it into a neighbouring run of the same language
    merged = []
    for lang, body in runs:
        if len(body.strip()) < 40 and merged and merged[-1][0] == lang:
            merged[-1] = (lang, merged[-1][1] + body)
        else:
            merged.append((lang, body))
    short = [i for i, (l, b) in enumerate(merged) if len(b.strip()) < 40]
    for i in short:
        for j in (i - 1, i + 1):
            if 0 <= j < len(merged) and merged[j][0] == merged[i][0] and j != i:
                merged[j] = (merged[j][0], merged[j][1] + merged[i][1])
                merged[i] = (merged[i][0], "")
                break
    return [(l, b) for l, b in merged if b.strip()]


def route_chunks(text, max_chars):
    """[(language, chunk, engine_name or None)] in speaking order."""
    out = []
    for lang, run in split_by_script(text):
        for chunk in pipeline.split_text(run, max_chars):
            out.append([lang, chunk, None])
    return out


def run_generation(payload):
    text = (payload.get("text") or "").strip()
    if not text:
        raise ValueError("text is empty")
    voices = load_voices()
    voice = next((v for v in voices if v["id"] == payload.get("voice_id")), None)
    if voice is None and payload.get("engine"):
        for_engine = voices_for_engine(voices, payload["engine"])
        voice = for_engine[0] if for_engine else None
    if not voice:
        raise ValueError("unknown voice_id")
    engine_name = payload.get("engine") or voice.get("engine") or "elevenlabs"
    voice, engine_note = resolve_pair(voices, voice, engine_name)
    eng = engines.get_engine(engine_name)
    ok, why = eng.available()
    if not ok:
        ensure = getattr(eng, "ensure_up", None)
        if ensure:
            ok, why = ensure()
    if not ok:
        raise RuntimeError(f"engine '{engine_name}' unavailable: {why}")

    max_chars = int(payload.get("max_chunk_chars") or pipeline.DEFAULT_MAX_CHUNK_CHARS)
    cap = getattr(eng, "max_chunk_chars", None)
    if cap:
        try:
            cap_chars = cap(payload.get("model"))
        except Exception:
            cap_chars = None
        if cap_chars:
            max_chars = min(max_chars, int(cap_chars))
    crossfade_ms = int(payload.get("crossfade_ms", pipeline.DEFAULT_CROSSFADE_MS))
    normalize_on = bool(payload.get("normalize", True))
    opts = {
        "model": payload.get("model") or None,
        "language": payload.get("language") or voice.get("language") or "en",
        "instruct": payload.get("instruct") or None,
        "seed": payload.get("seed"),
    }

    routed = route_chunks(text, max_chars)
    chunks = [c for _, c, _ in routed]
    fallback = None
    if payload.get("route_other_language"):
        cands = [v for v in voices_for_engine(voices, "elevenlabs")]
        if cands:
            fallback = {"voice": cands[0], "engine": engines.get_engine("elevenlabs")}
    pieces = []
    rate = None
    resampled = False
    chunk_meta = []
    models = []
    engines_used = []
    t_start = time.time()
    for lang, chunk, _ in routed:
        use_voice, use_eng, use_lang = voice, eng, lang
        ok, why = True, ""
        checker = getattr(use_eng, "supports_text", None)
        if checker:
            model_for_check = payload.get("model")
            resolver = getattr(use_eng, "resolve_model", None)
            if resolver:
                try:
                    model_for_check = resolver(payload.get("model"))
                except Exception:
                    pass
            ok, why = checker(chunk, model_for_check)
        if not ok:
            if not fallback:
                raise RuntimeError(why + " Turn on \"Korean parts\" to send it there automatically.")
            use_voice, use_eng, use_lang = fallback["voice"], fallback["engine"], "ko"
        chunk_opts = dict(opts, language=use_lang)
        pcm, r, meta = use_eng.synth(chunk, use_voice.get("ref"), chunk_opts)
        if rate is None:
            rate = r
        elif r != rate:
            # two engines in one run (local 48 kHz, cloud 24 kHz) - line them up
            if r > rate:
                pieces = [pipeline.resample(p, rate, r) for p in pieces]
                rate = r
                resampled = True
            else:
                pcm = pipeline.resample(pcm, r, rate)
                resampled = True
        pieces.append(pcm)
        engines_used.append(use_eng.name)
        if meta.get("model"):
            models.append(meta["model"])
        chunk_meta.append({"chars": len(chunk), "samples": len(pcm), "language": use_lang,
                           "engine": use_eng.name, "voice": use_voice.get("name"), **meta})
    synth_s = time.time() - t_start
    mixed = len(set(engines_used)) > 1

    samples, boundaries = pipeline.crossfade_concat(pieces, rate, crossfade_ms)
    if normalize_on:
        samples = pipeline.normalize(samples)

    gen_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    filename = f"{gen_id}-{slug(text)}.wav"
    path = AUDIO / filename
    analysis.write_wav(path, samples, rate)

    metrics = analysis.analyze(path, text=text, chunk_boundaries=boundaries)
    defects = analysis.defects(metrics)
    latency = round(time.time() - t_start, 2)

    record = {
        "id": gen_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "voice_id": voice["id"],
        "voice_name": voice["name"],
        "requested_voice_id": payload.get("voice_id"),
        "note": engine_note,
        "engine": engine_name,
        "engines_used": sorted(set(engines_used)) or [engine_name],
        "mixed_engines": mixed,
        "resampled": resampled,
        "model": ", ".join(dict.fromkeys(models)) if mixed else (chunk_meta[0].get("model") if chunk_meta else None),
        "language": opts["language"],
        "chars": len(text),
        "chunks": len(chunks),
        "chunk_chars": max_chars,
        "crossfade_ms": crossfade_ms,
        "normalize": normalize_on,
        "seed": opts["seed"],
        "instruct": opts["instruct"],
        "file": filename,
        "rate": rate,
        "latency_s": latency,
        "synth_s": round(synth_s, 2),
        "rtf": round(synth_s / metrics["duration_s"], 3) if metrics["duration_s"] else None,
        "metrics": metrics,
        "defects": defects,
        "status": "completed" if not defects else "completed_with_defects",
    }
    append_history(record)
    record["url"] = f"/audio/{urllib.parse.quote(filename)}"
    return record


# ------------------------------------------------------------------ cloning
PREVIEW_TEXT = ("Hello friend, this is the new clone speaking. "
                "오늘도 성경을 함께 열어보겠습니다. Rightly divide the word of truth.")


def clone_voice(payload):
    """Turn stored recordings into a usable voice, then verify it immediately."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    provider = payload.get("provider") or "elevenlabs"
    voice_key = payload.get("voice_key") or slug(name, "voice")

    samples = [x for x in cloning.list_samples(voice_key) if x.get("usable")]
    if payload.get("sample_ids"):
        wanted = set(payload["sample_ids"])
        samples = [x for x in samples if x["id"] in wanted]
    if not samples:
        raise ValueError("no usable recordings for this voice; record at least one first")

    paths = [x["path"] for x in samples]
    key = engines._api_key()

    if provider == "elevenlabs":
        voice_id = cloning.clone_elevenlabs(
            key,
            name,
            paths,
            description=payload.get("description") or "Cloned inside VoiceForge.",
            labels=payload.get("labels") or {"language": "en", "accent": "korean"},
        )
        engine_name, ref = "elevenlabs", voice_id
        note = f"cloned from {len(paths)} sample(s) via ElevenLabs IVC"
    else:
        info = cloning.clone_local_ref(name, paths, engine=payload.get("engine") or "voicebox")
        engine_name, ref = info["engine"], info["ref"]
        note = info["note"]

    voices = load_voices()
    vid = voice_key + "-" + uuid.uuid4().hex[:4]
    voice = {
        "id": vid,
        "name": name,
        "engine": engine_name,
        "ref": ref,
        "language": payload.get("language") or "en",
        "note": note,
        "samples": [x["file"] for x in samples],
        "sample_s": round(sum(x["metrics"]["duration_s"] for x in samples), 1),
        "provider": provider,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    voices.append(voice)
    save_voices(voices)

    # verification render: a clone is not "done" until it speaks and measures
    preview = None
    try:
        preview = run_generation({
            "voice_id": vid,
            "text": payload.get("preview_text") or PREVIEW_TEXT,
            "engine": engine_name,
            "language": "en",
            "normalize": True,
        })
        preview["kind"] = "clone_preview"
    except Exception as e:
        preview = {"error": str(e)}

    return {"voice": voice, "preview": preview, "samples_used": len(paths)}


# --------------------------------------------------------------------- page
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoiceForge</title>
<style>
  :root { color-scheme: dark; --bg:#0f1012; --panel:#17181b; --line:#272930; --ink:#e9eaee;
          --muted:#8d9098; --ok:#3f9c6d; --warn:#c9a227; --bad:#c0483c; --accent:#4b8ef7; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
  header { display:flex; align-items:center; gap:14px; padding:14px 22px; border-bottom:1px solid var(--line); }
  header h1 { font-size:16px; margin:0; letter-spacing:-.01em; }
  header .tag { font-size:11px; color:var(--muted); border:1px solid var(--line); padding:2px 8px; border-radius:99px; }
  .wrap { display:grid; grid-template-columns: 300px 1fr; gap:0; height:calc(100vh - 53px); }
  .col { overflow:auto; }
  .lib { border-right:1px solid var(--line); padding:16px; }
  .main { padding:16px 20px 40px; }
  h2 { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:0 0 10px; }
  .voice { border:1px solid var(--line); background:var(--panel); border-radius:10px; padding:10px 12px;
           margin-bottom:8px; cursor:pointer; }
  .voice.sel { border-color:var(--accent); box-shadow:0 0 0 2px rgba(75,142,247,.18); }
  .voice .n { font-weight:600; font-size:13px; }
  .voice .m { font-size:11.5px; color:var(--muted); margin-top:2px; }
  textarea { width:100%; min-height:150px; background:var(--panel); color:var(--ink); border:1px solid var(--line);
             border-radius:10px; padding:12px; font:14px/1.55 inherit; resize:vertical; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  label.f { font-size:11.5px; color:var(--muted); display:flex; flex-direction:column; gap:4px; }
  input, select { background:var(--panel); color:var(--ink); border:1px solid var(--line); border-radius:8px;
                  padding:7px 9px; font:13px inherit; }
  input[type=number] { width:92px; }
  button { background:var(--accent); color:#fff; border:0; border-radius:9px; padding:10px 18px;
           font:600 14px inherit; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  button.ghost { background:transparent; border:1px solid var(--line); color:var(--ink); font-weight:500; padding:7px 12px; }
  .card { border:1px solid var(--line); background:var(--panel); border-radius:12px; padding:14px 16px; margin-bottom:14px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .kpi { display:grid; grid-template-columns:repeat(6,1fr); gap:10px; }
  .kpi div { border:1px solid var(--line); border-radius:10px; padding:9px 11px; background:#131417; }
  .kpi .v { font-size:17px; font-weight:650; }
  .kpi .l { font-size:10.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  .bad { color:var(--bad); font-weight:600; }
  .good { color:var(--ok); font-weight:600; }
  .warn { color:var(--warn); font-weight:600; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { font-size:11px; border:1px solid var(--line); border-radius:99px; padding:2px 8px; color:var(--muted); }
  .chip.on { color:var(--ok); border-color:#2f5f47; }
  .bar { height:14px; background:#2a2c33; border-radius:3px; }
  .bar > i { display:block; height:14px; background:var(--bad); border-radius:3px; }
  audio { width:100%; margin-top:10px; }
  .muted { color:var(--muted); font-size:12px; }
  .err { color:var(--bad); }
  .step { font-size:13.5px; line-height:1.5; color:#c9cbd2; }
  .step .num { display:inline-flex; width:20px; height:20px; border-radius:50%; background:#23252b;
               color:#e9eaee; font-size:11px; font-weight:700; align-items:center; justify-content:center;
               margin-right:6px; vertical-align:-4px; }
  .labgrid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  button.big { width:100%; margin-top:10px; padding:16px; font-size:16px; font-weight:650; border-radius:12px; }
  button.big.stop { background:#c0483c; }
  button.big:disabled { opacity:.35; }
</style>
</head>
<body>
<header>
  <h1>VoiceForge</h1>
  <span class="tag">reverse-engineered from voicebox</span>
  <span class="tag">Six Sigma controlled</span>
  <span id="engines" class="chips" style="margin-left:auto"></span>
</header>

<div class="wrap">
  <div class="col lib">
    <h2>Voice library</h2>
    <div id="voices"></div>
    <div class="card" style="margin-top:14px">
      <h2 style="margin-bottom:8px">Add a voice</h2>
      <div class="row" style="flex-direction:column; align-items:stretch; gap:6px">
        <input id="nv-name" placeholder="Name">
        <select id="nv-engine"></select>
        <input id="nv-ref" placeholder="voice_id / profile / say voice">
        <button class="ghost" id="nv-add">Add to library</button>
      </div>
      <p class="muted" style="margin:8px 0 0">Cloud clones take an ElevenLabs voice_id. Local engines take a Voicebox profile name.</p>
    </div>


  </div>

  <div class="col main">
    <div class="card">
      <h2 style="margin-bottom:10px">Record a new voice</h2>

      <div class="step"><span class="num">1</span> Press <b>Record</b>. If Chrome asks for the microphone, click <b>Allow</b>.</div>
      <div class="labgrid">
        <button id="rec-start" class="big">Record</button>
        <button id="rec-stop" class="big stop" disabled>Stop</button>
      </div>
      <div class="row" style="margin-top:8px; gap:10px">
        <span id="rec-time" class="muted">0.0s</span>
        <span id="rec-state" class="muted"></span>
      </div>
      <div class="bar" style="margin-top:8px"><i id="rec-meter" style="width:0%;background:var(--ok)"></i></div>

      <div class="step" style="margin-top:14px"><span class="num">2</span> Read for 30-90 seconds. Korean and English together is best.</div>

      <div class="step" style="margin-top:10px"><span class="num">3</span> Press <b>Stop</b>. It grades, clones, and plays a test by itself.</div>

      <details style="margin-top:12px">
        <summary class="muted" style="cursor:pointer">Options (already set up, open only if you want to change something)</summary>
        <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px">
          <input id="rec-key" placeholder="voice key" value="henry-rd">
          <input id="clone-name" placeholder="New voice name">
          <select id="clone-provider">
            <option value="elevenlabs">elevenlabs (cloud clone)</option>
            <option value="local">local reference (free)</option>
          </select>
          <label class="muted" style="display:flex; gap:6px; align-items:center">
            <input type="checkbox" id="auto-clone" checked> clone automatically when I press Stop
          </label>
          <button id="clone-go" class="ghost">Clone manually instead</button>
        </div>
      </details>

      <div id="rec-status" class="muted" style="margin-top:10px"></div>
      <div id="samples" style="margin-top:10px"></div>
      <div id="clone-status" class="muted" style="margin-top:6px"></div>
      <div id="clone-preview"></div>
    </div>
    <div class="card">
      <h2>Script</h2>
      <textarea id="text" placeholder="Paste the narration. Long scripts are split at sentence boundaries and rejoined with a crossfade."></textarea>
      <div class="row" style="margin-top:10px">
        <label class="f">Engine<select id="engine"></select></label>
        <label class="f">Model<input id="model" placeholder="auto (local: best downloaded)"></label>
        <label class="f">Language<select id="lang">
          <option value="en">en</option><option value="ko">ko</option><option value="es">es</option>
          <option value="ja">ja</option><option value="zh">zh</option></select></label>
        <label class="f">Max chunk<select id="chunk">
          <option>400</option><option selected>800</option><option>1600</option></select></label>
        <label class="f">Crossfade ms<select id="fade">
          <option>0</option><option selected>50</option><option>120</option></select></label>
        <label class="f">Seed<input id="seed" type="number" placeholder="random"></label>
        <label class="f">Normalize<select id="norm"><option value="1" selected>on</option><option value="0">off</option></select></label>
        <label class="f">Korean parts<select id="route"><option value="0" selected>same engine</option><option value="1">ElevenLabs clone</option></select></label>
      </div>
      <div id="engine-note" class="muted" style="margin-top:8px;font-size:11.5px"></div>
      <div class="row" style="margin-top:12px">
        <button id="go">Generate</button>
        <span id="status" class="muted"></span>
      </div>
      <div id="player"></div>
    </div>

    <div class="card">
      <h2>Process control (last 200 generations)</h2>
      <div class="kpi" id="kpi"></div>
      <div class="grid2" style="margin-top:14px">
        <div>
          <h2 style="margin-bottom:6px">Defect pareto</h2>
          <div id="pareto" class="muted">no data yet</div>
        </div>
        <div>
          <h2 style="margin-bottom:6px">Rate chart, sec per 100 chars</h2>
          <div id="chart"></div>
          <div id="limits" class="muted"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>History</h2>
      <div style="max-height:260px; overflow:auto">
        <table id="hist"><thead><tr>
          <th>Time</th><th>Voice</th><th>Engine</th><th>Chars</th><th>Chunks</th>
          <th>Dur</th><th>s/100ch</th><th>Latency</th><th>Defects</th><th></th>
        </tr></thead><tbody></tbody></table>
      </div>
    </div>
  </div>
</div>

<script>
let STATE = { voices: [], engines: [], metrics: null, history: [] };
let selected = null;

const $ = (id) => document.getElementById(id);
const pct = (n) => (n === null || n === undefined ? '-' : n + '%');

async function refresh() {
  const r = await fetch('/api/state');
  STATE = await r.json();
  if (!selected && STATE.voices.length) selected = STATE.voices[0].id;
  paintEngines(); paintVoices(); paintKpi(); paintHistory(); paintPareto(); paintChart();
}

function paintEngines() {
  $('engines').innerHTML = STATE.engines.map(e =>
    `<span class="chip ${e.available ? 'on' : ''}">${e.name}${e.available ? '' : ': ' + e.detail}</span>`).join('');
  const sel = $('engine'), cur = sel.value;
  sel.innerHTML = STATE.engines.filter(e => e.available).map(e =>
    `<option value="${e.name}">${e.name} (${e.kind})</option>`).join('');
  if (cur) sel.value = cur;
  const nv = $('nv-engine');
  nv.innerHTML = STATE.engines.map(e => `<option value="${e.name}">${e.name}</option>`).join('');
}

function engineInfo(name) {
  return (STATE.engines || []).find(e => e.name === name) || null;
}

function paintVoices() {
  const eng = $('engine').value;
  $('voices').innerHTML = STATE.voices.map(v => {
    const info = engineInfo(v.engine);
    const off = info && !info.available;
    const other = eng && v.engine !== eng;
    return `
    <div class="voice ${v.id === selected ? 'sel' : ''}" onclick="pick('${v.id}')"
         style="${off ? 'opacity:.45' : ''}${other && !off ? ';border-style:dashed' : ''}">
      <div class="n">${v.name}</div>
      <div class="m">${v.engine} &middot; ${v.ref}${off ? ' &middot; engine off' : (other ? ' &middot; not this engine' : '')}</div>
    </div>`;
  }).join('');
  paintEngineNote();
}

function paintEngineNote() {
  const name = $('engine').value;
  const info = engineInfo(name);
  const own = STATE.voices.filter(v => v.engine === name);
  const parts = [];
  if (info && !info.available) parts.push(`${name} is not ready: ${info.detail}.`);
  if (info && info.available && info.detail && name === 'voicebox') parts.push(`Local engine: ${info.detail}.`);
  if (!own.length) parts.push(`No voice in the library belongs to ${name}, so Generate will refuse until you add one.`);
  const hasKo = /[\uac00-\ud7a3]/.test($('text').value || '');
  const routed = $('route').value === '1';
  if (hasKo && name === 'voicebox' && !routed) {
    parts.push('Korean detected. Set Korean parts to "ElevenLabs clone", otherwise that passage is refused by the local model.');
  }
  if (hasKo && routed) {
    parts.push('Korean passages go to the cloud clone, which spends ElevenLabs credits; English stays free and local.');
  }
  $('engine-note').textContent = parts.join(' ');
}

window.pickEngine = (name) => {
  $('engine').value = name;
  const own = STATE.voices.filter(v => v.engine === name);
  if (own.length && !own.some(v => v.id === selected)) selected = own[0].id;
  paintVoices();
};

window.pick = (id) => {
  selected = id;
  const v = STATE.voices.find(x => x.id === id);
  if (v) $('engine').value = v.engine;
  paintVoices();
};

$('engine').addEventListener('change', () => pickEngine($('engine').value));
$('text').addEventListener('input', paintEngineNote);
$('route').addEventListener('change', paintEngineNote);

function paintKpi() {
  const m = STATE.metrics || {};
  const cells = [
    ['units', m.units ?? 0],
    ['defects', m.defects ?? 0],
    ['DPMO', m.dpmo ?? '-'],
    ['sigma', m.sigma ?? '-'],
    ['yield', pct(m.yield_pct)],
    ['latency p95', m.latency_p95 ? m.latency_p95 + 's' : '-'],
  ];
  $('kpi').innerHTML = cells.map(([l, v]) =>
    `<div><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
}

function paintPareto() {
  const p = (STATE.metrics || {}).pareto || [];
  if (!p.length) { $('pareto').textContent = 'no defects recorded'; return; }
  const max = Math.max(...p.map(x => x[1]));
  $('pareto').innerHTML = p.map(([code, n]) => `
    <div style="display:grid; grid-template-columns:112px 1fr 34px; gap:8px; align-items:center; margin-bottom:5px">
      <span class="muted">${code}</span>
      <span class="bar"><i style="width:${Math.round(n / max * 100)}%"></i></span>
      <span class="muted">${n}</span>
    </div>`).join('');
}

function paintChart() {
  const rc = (STATE.metrics || {}).rate_chart;
  const pts = (STATE.history || []).map(h => h.metrics && h.metrics.sec_per_100chars).filter(x => x != null);
  if (!pts.length) { $('chart').innerHTML = '<span class="muted">no data</span>'; $('limits').textContent = ''; return; }
  const w = 320, h = 70, min = Math.min(...pts, rc ? rc.lcl : Infinity) - 0.5;
  const max = Math.max(...pts, rc ? rc.ucl : -Infinity) + 0.5;
  const x = i => 6 + i * (w - 12) / Math.max(1, pts.length - 1);
  const y = v => h - 6 - (v - min) / (max - min) * (h - 12);
  const path = pts.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const lines = rc ? `
    <line x1="0" x2="${w}" y1="${y(rc.ucl)}" y2="${y(rc.ucl)}" stroke="#c0483c" stroke-dasharray="3 3" stroke-width="1"/>
    <line x1="0" x2="${w}" y1="${y(rc.center)}" y2="${y(rc.center)}" stroke="#4b8ef7" stroke-width="1"/>
    <line x1="0" x2="${w}" y1="${y(rc.lcl)}" y2="${y(rc.lcl)}" stroke="#c0483c" stroke-dasharray="3 3" stroke-width="1"/>` : '';
  $('chart').innerHTML = `<svg width="100%" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    ${lines}<path d="${path}" fill="none" stroke="#e9eaee" stroke-width="1.4"/>
    ${pts.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="2" fill="#e9eaee"/>`).join('')}</svg>`;
  $('limits').textContent = rc
    ? `center ${rc.center} · UCL ${rc.ucl} · LCL ${rc.lcl} · sigma-hat ${rc.sigma_hat} · n=${rc.n}`
    : '';
}

function paintHistory() {
  const rows = (STATE.history || []).slice().reverse();
  const tb = $('hist').querySelector('tbody');
  tb.innerHTML = rows.map(h => {
    const d = (h.defects || []).length;
    const badge = d ? `<span class="bad">${h.defects.join(' ')}</span>` : '<span class="good">clean</span>';
    const rate = h.metrics && h.metrics.sec_per_100chars;
    return `<tr>
      <td class="muted">${h.created_at.slice(11)}</td>
      <td>${h.voice_name}</td>
      <td class="muted">${h.engine}</td>
      <td>${h.chars}</td>
      <td>${h.chunks}</td>
      <td>${h.metrics.duration_s}s</td>
      <td>${rate ?? '-'}</td>
      <td>${h.latency_s}s</td>
      <td>${badge}</td>
      <td><audio controls preload="none" style="height:26px;width:150px" src="/audio/${encodeURIComponent(h.file)}"></audio></td>
    </tr>`;
  }).join('');
}

$('go').onclick = async () => {
  const body = {
    voice_id: selected,
    text: $('text').value,
    engine: $('engine').value,
    model: $('model').value.trim() || null,
    language: $('lang').value,
    max_chunk_chars: parseInt($('chunk').value, 10),
    crossfade_ms: parseInt($('fade').value, 10),
    seed: $('seed').value === '' ? null : parseInt($('seed').value, 10),
    normalize: $('norm').value === '1',
    route_other_language: $('route').value === '1',
  };
  if (!body.text.trim()) { $('status').textContent = 'Paste a script first.'; return; }
  $('go').disabled = true;
  $('status').className = 'muted';
  $('status').textContent = 'Generating...';
  try {
    const r = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                             body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'failed');
    const defs = (d.defects || []).length;
    $('status').className = defs ? 'err' : 'muted';
    const engs = d.mixed_engines ? d.engines_used.join(' + ') : d.engine;
    const spokes = [d.voice_name, engs, d.model].filter(Boolean).join(' / ');
    $('status').textContent = `${d.metrics.duration_s}s · ${d.chunks} chunk(s) · ${spokes} · ${d.latency_s}s · ` +
      (defs ? d.defects.join(' ') : 'no defects') + (d.note ? ` — ${d.note}` : '');
    $('player').innerHTML = `<audio controls autoplay src="${d.url}"></audio>`;
    await refresh();
  } catch (e) {
    $('status').className = 'err';
    $('status').textContent = e.message;
  } finally {
    $('go').disabled = false;
  }
};

$('nv-add').onclick = async () => {
  const name = $('nv-name').value.trim(), ref = $('nv-ref').value.trim();
  if (!name || !ref) return;
  await fetch('/api/voices', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, engine: $('nv-engine').value, ref }) });
  $('nv-name').value = ''; $('nv-ref').value = '';
  await refresh();
};

refresh();
</script>

<script>
let REC = { ctx: null, stream: null, proc: null, chunks: [], t0: 0, timer: null };

function f32ToWav(chunks, rate) {
  let len = 0;
  for (const c of chunks) len += c.length;
  const buf = new ArrayBuffer(44 + len * 2);
  const view = new DataView(buf);
  const str = (o, t) => { for (let i = 0; i < t.length; i++) view.setUint8(o + i, t.charCodeAt(i)); };
  str(0, 'RIFF'); view.setUint32(4, 36 + len * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  str(36, 'data'); view.setUint32(40, len * 2, true);
  let o = 44;
  for (const c of chunks) {
    for (let i = 0; i < c.length; i++) {
      let v = Math.max(-1, Math.min(1, c[i]));
      view.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7FFF, true);
      o += 2;
    }
  }
  return new Uint8Array(buf);
}

function b64(bytes) {
  let s = '';
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) s += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
  return btoa(s);
}

document.getElementById('rec-start').onclick = async () => {
  const st = document.getElementById('rec-status');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false }
    });
    const ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    REC = { ctx, stream, proc, chunks: [], t0: performance.now(), timer: null };
    proc.onaudioprocess = (e) => {
      const d = e.inputBuffer.getChannelData(0);
      REC.chunks.push(new Float32Array(d));
      let peak = 0;
      for (let i = 0; i < d.length; i += 8) { const a = Math.abs(d[i]); if (a > peak) peak = a; }
      const bar = document.getElementById('rec-meter');
      bar.style.width = Math.min(100, peak * 140) + '%';
      bar.style.background = peak < 0.06 ? 'var(--warn)' : (peak > 0.9 ? 'var(--bad)' : 'var(--ok)');
      const hint = document.getElementById('rec-state');
      if (hint) hint.textContent = peak < 0.06 ? 'too quiet, come closer'
        : (peak > 0.9 ? 'too hot, back off a little' : 'level is good');
    };
    src.connect(proc); proc.connect(ctx.destination);
    REC.timer = setInterval(() => {
      document.getElementById('rec-time').textContent = ((performance.now() - REC.t0) / 1000).toFixed(1) + 's';
    }, 100);
    document.getElementById('rec-start').disabled = true;
    document.getElementById('rec-stop').disabled = false;
    st.className = 'muted';
    st.textContent = 'Listening. Read in your normal teaching voice, then press Stop.';
    if (ctx.state === 'suspended') await ctx.resume();
  } catch (e) {
    st.className = 'err';
    st.textContent = 'Mic blocked: ' + e.message;
  }
};

document.getElementById('rec-stop').onclick = async () => {
  const st = document.getElementById('rec-status');
  clearInterval(REC.timer);
  REC.proc.disconnect(); REC.stream.getTracks().forEach(t => t.stop());
  const rate = REC.ctx.sampleRate;
  await REC.ctx.close();
  document.getElementById('rec-start').disabled = false;
  document.getElementById('rec-stop').disabled = true;
  const wav = f32ToWav(REC.chunks, rate);
  st.textContent = 'Saving your take...';
  try {
    const r = await fetch('/api/samples', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_key: document.getElementById('rec-key').value.trim() || 'unsorted',
                             audio_b64: b64(wav) })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'upload failed');
    st.className = d.usable ? 'good' : 'err';
    st.textContent = `${d.metrics.duration_s}s captured. ` +
      (d.usable ? (d.gain_db ? `Take accepted, quiet take lifted ${d.gain_db} dB.` : 'Take accepted.')
                : 'Rejected: ' + d.gate.join(', ') + '. Record again.');
    await refreshSamples();
    if (d.usable && document.getElementById('auto-clone').checked) {
      await cloneNow();
    }
  } catch (e) {
    st.className = 'err';
    st.textContent = e.message;
  }
};

async function refreshSamples() {
  const r = await fetch('/api/samples');
  const list = await r.json();
  const box = document.getElementById('samples');
  if (!list.length) { box.innerHTML = '<span class="muted">no recordings yet</span>'; return; }
  box.innerHTML = list.map(s => `
    <div style="border:1px solid var(--line); border-radius:8px; padding:7px 9px; margin-bottom:6px">
      <div class="row" style="justify-content:space-between">
        <span class="muted">${s.created_at.slice(5, 16)} · ${s.metrics.duration_s}s · ${s.metrics.rms_dbfs} dBFS</span>
        <span class="${s.usable ? 'good' : 'bad'}">${s.usable ? 'usable' : 'rejected'}</span>
      </div>
      <audio controls preload="metadata" style="height:26px;width:100%;margin-top:5px" src="/sample-audio/${encodeURIComponent(s.file)}"></audio>
    </div>`).join('');
}

document.getElementById('clone-go').onclick = () => cloneNow();

async function cloneNow() {
  const name = document.getElementById('clone-name').value.trim();
  const st = document.getElementById('clone-status');
  if (!name) { st.className = 'err'; st.textContent = 'Name the voice in Options first.'; return; }
  st.className = 'muted';
  st.textContent = 'Cloning, then speaking a test line...';
  document.getElementById('clone-go').disabled = true;
  try {
    const r = await fetch('/api/clone', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, provider: document.getElementById('clone-provider').value,
                             voice_key: document.getElementById('rec-key').value.trim() || 'unsorted' })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'clone failed');
    const p = d.preview || {};
    const defs = (p.defects || []).length;
    st.className = defs ? 'err' : 'good';
    st.textContent = `${d.voice.name} ready from ${d.samples_used} sample(s), ref ${d.voice.ref.slice(0, 12)}... ` +
      (p.error ? 'preview error: ' + p.error : `${p.metrics.duration_s}s preview, ${defs ? p.defects.join(' ') : 'no defects'}`);
    document.getElementById('clone-preview').innerHTML = p.url
      ? `<audio controls autoplay src="${p.url}"></audio>` : '';
    await refresh();
    await refreshSamples();
  } catch (e) {
    st.className = 'err';
    st.textContent = e.message;
  } finally {
    document.getElementById('clone-go').disabled = false;
  }
}

const nameBox = document.getElementById('clone-name');
if (!nameBox.value) {
  const d = new Date();
  const local = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  nameBox.value = 'Henry - RD ' + local;
}

refreshSamples();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if path == "/api/state":
            history = load_history()
            self._json(200, {
                "voices": load_voices(),
                "engines": engines.engine_status(),
                "history": history,
                "metrics": sixsigma.summarize([h for h in history if h.get("engine") != "tone"]) or None,
            })
            return
        if path == "/api/samples":
            self._json(200, cloning.list_samples())
            return
        if path.startswith("/sample-audio/"):
            rel = urllib.parse.unquote(path[len("/sample-audio/"):])
            target = (SAMPLES / rel)
            if target.exists() and target.suffix == ".wav":
                self._send(200, target.read_bytes(), "audio/wav")
            else:
                self._json(404, {"error": "not found"})
            return
        if path == "/api/history":
            self._json(200, load_history())
            return
        if path == "/api/metrics":
            self._json(200, sixsigma.summarize(load_history()) or {})
            return
        if path.startswith("/audio/"):
            name = urllib.parse.unquote(path[len("/audio/"):])
            target = (AUDIO / Path(name).name)
            if target.exists():
                self._send(200, target.read_bytes(), "audio/wav")
            else:
                self._json(404, {"error": "not found"})
            return
        if path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": e["name"], "object": "model", "owned_by": "voiceforge"} for e in engines.engine_status()
            ]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self._body()
        except Exception as e:
            self._json(400, {"error": f"bad json: {e}"})
            return

        if path == "/api/voices":
            voices = load_voices()
            vid = slug(payload.get("name") or "", "voice") + "-" + uuid.uuid4().hex[:4]
            voices.append({
                "id": vid,
                "name": payload.get("name") or vid,
                "engine": payload.get("engine") or "elevenlabs",
                "ref": payload.get("ref") or "",
                "language": payload.get("language") or "en",
                "note": payload.get("note") or "",
            })
            save_voices(voices)
            self._json(200, {"ok": True, "id": vid})
            return

        if path == "/api/samples":
            import base64
            b64 = payload.get("audio_b64") or ""
            if not b64:
                self._json(400, {"error": "no audio"})
                return
            try:
                raw = base64.b64decode(b64)
            except Exception as e:
                self._json(400, {"error": f"bad base64: {e}"})
                return
            rec = cloning.save_sample(payload.get("voice_key") or "unsorted", raw,
                                      label=payload.get("label") or "")
            rec["url"] = "/sample-audio/" + urllib.parse.quote(rec["file"])
            self._json(200, rec)
            return

        if path == "/api/clone":
            try:
                result = clone_voice(payload)
                self._json(200, result)
            except Exception as e:
                self._json(400, {"error": str(e)})
            return

        if path == "/api/shutdown":
            self._json(200, {"ok": True})
            threading.Timer(0.3, lambda: os._exit(0)).start()
            return

        if path == "/api/generate":
            try:
                record = run_generation(payload)
                self._json(200, record)
            except Exception as e:
                self._json(400, {"error": str(e)})
            return

        if path == "/v1/audio/speech":
            # OpenAI-compatible shim, mirroring voicebox's own contract
            try:
                voices = load_voices()
                wanted = payload.get("voice")
                voice = next((v for v in voices if wanted in (v["id"], v["name"])), None)
                if not voice:
                    self._json(404, {"error": f"voice '{wanted}' not in library"})
                    return
                record = run_generation({
                    "voice_id": voice["id"],
                    "text": payload.get("input") or "",
                    "engine": payload.get("model") or voice["engine"],
                    "normalize": True,
                })
                self._send(200, (AUDIO / record["file"]).read_bytes(), "audio/wav")
            except Exception as e:
                self._json(400, {"error": str(e)})
            return

        self._json(404, {"error": "not found"})


def is_voiceforge(port, timeout=0.7):
    """True when something on this port answers like VoiceForge."""
    import urllib.request as _ur
    try:
        with _ur.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=timeout) as r:
            return r.status == 200 and b'"voices"' in r.read()
    except Exception:
        return False


def stop_voiceforge(port, timeout=2.0):
    import urllib.request as _ur
    try:
        _ur.urlopen(_ur.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST"), timeout=timeout)
        return True
    except Exception:
        return False


def open_browser(url):
    """`open` is reliable on macOS; webbrowser falls back to osascript and can fail."""
    import shutil
    import subprocess
    if shutil.which("open"):
        try:
            subprocess.run(["open", url], check=True, capture_output=True, timeout=10)
            return
        except Exception:
            pass
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    ensure_dirs()
    # One preferred address. If an older VoiceForge holds it, stop that copy and wait for
    # the socket to come back. If something else holds it, fall back to any free port
    # rather than refusing to start.
    srv = None
    stopped_ours = False
    deadline = time.time() + 6
    while time.time() < deadline:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
            break
        except OSError:
            if not stopped_ours and is_voiceforge(PORT):
                print(f"Stopping the previous VoiceForge on port {PORT}...")
                stop_voiceforge(PORT)
                stopped_ours = True
                time.sleep(1.0)
                continue
            time.sleep(0.4)
    if srv is None:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        print(f"Port {PORT} is busy, so this run uses {srv.server_address[1]}.")

    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    try:
        (DATA / "URL.txt").write_text(url)
    except OSError:
        pass
    print("=" * 56)
    print(f"  VoiceForge is running at  {url}")
    print("=" * 56)
    print(f"  recordings and renders: {DATA}")
    print("  keep this Terminal window open while you use it")
    print("  press Control-C here to stop")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: open_browser(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
