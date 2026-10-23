"""
VoiceForge - engine adapters.

One interface, several backends:

  elevenlabs   cloud clone, the reference implementation (works today)
  voicebox     the local open-source app this project reverse-engineers,
               reached over its OpenAI-compatible endpoint on 127.0.0.1:17493
  say          macOS built-in speech, offline sanity floor
  tone         deterministic synthetic signal, used by the QA harness so
               measurements can be validated without spending credits

Every engine returns mono int16 PCM plus a sample rate, so downstream
measurement is identical no matter who synthesized the audio.
"""

import array
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

KEY_FILE_CANDIDATES = [
    Path(__file__).resolve().parent.parent / ".elevenlabs_key",
    Path.home() / "Documents/Claude/Projects/rightlydividing/.elevenlabs_key",
]
VOICEBOX_URLS = [u for u in [
    os.environ.get("VOICEFORGE_VOICEBOX_URL"),
    "http://127.0.0.1:17493",   # native app / from-source server
    "http://127.0.0.1:17600",   # docker compose port mapping
] if u]
ELEVEN_API = os.environ.get("VOICEFORGE_ELEVEN_API", "https://api.elevenlabs.io")


class EngineError(RuntimeError):
    pass


def _api_key():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    for path in KEY_FILE_CANDIDATES:
        try:
            if path.exists():
                k = path.read_text().strip()
                if k:
                    return k
        except OSError:
            continue
    return ""


def _pcm_from_wav(data: bytes):
    with wave.open(io.BytesIO(data), "rb") as w:
        rate = w.getframerate()
        width = w.getsampwidth()
        channels = w.getnchannels()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise EngineError(f"expected 16-bit wav, got {width * 8}-bit")
    arr = array.array("h")
    arr.frombytes(frames)
    if channels > 1:
        mono = array.array("h")
        for i in range(0, len(arr) - channels + 1, channels):
            mono.append(int(sum(arr[i:i + channels]) / channels))
        arr = mono
    return arr, rate


class Engine:
    name = "base"
    label = "Base"
    kind = "local"
    needs = ""
    can_clone = False

    def available(self):
        return False, "not implemented"

    def synth(self, text, voice_ref, opts=None):
        raise EngineError("not implemented")


class ElevenLabsEngine(Engine):
    name = "elevenlabs"
    label = "ElevenLabs cloud (reference)"
    kind = "cloud"
    needs = "API key with text_to_speech"
    can_clone = True

    def available(self):
        if not _api_key():
            return False, "no API key found"
        return True, "key found"

    def synth(self, text, voice_ref, opts=None):
        opts = opts or {}
        key = _api_key()
        if not key:
            raise EngineError("No ElevenLabs API key. Put one in .elevenlabs_key.")
        fmt = opts.get("format", "pcm_24000")
        model = opts.get("model") or "eleven_multilingual_v2"
        body = {"text": text, "model_id": model}
        if opts.get("instruct"):
            body["voice_settings"] = {"stability": 0.5, "similarity_boost": 0.75}
        if opts.get("seed") is not None:
            body["seed"] = int(opts["seed"])
        req = urllib.request.Request(
            f"{ELEVEN_API}/v1/text-to-speech/{voice_ref}?output_format={fmt}",
            data=json.dumps(body).encode(),
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/pcm" if fmt.startswith("pcm") else "audio/mpeg",
            },
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise EngineError(f"ElevenLabs {e.code}: {detail}")
        latency = time.time() - t0
        if fmt.startswith("pcm"):
            arr = array.array("h")
            arr.frombytes(raw)
            rate = int(fmt.split("_")[1])
        else:
            arr, rate = _pcm_from_wav(raw)
        return arr, rate, {"engine": self.name, "model": model, "latency_s": round(latency, 2), "format": fmt}


class VoiceboxEngine(Engine):
    """Bridge to the upstream local app. Free, offline, no credits.

    Model choice is automatic: the adapter asks the bridge which TTS models are
    actually downloaded and picks the best one, so a free render never fails
    just because a default model was never fetched.
    """

    name = "voicebox"
    label = "Voicebox local (open source)"
    kind = "local"
    needs = "voicebox running on 127.0.0.1:17493"
    can_clone = True

    # best first; multilingual models rank above English-only ones
    MODEL_PREFERENCE = ("chatterbox", "tada-3b-ml", "omnivoice", "qwen-tts-0.6B", "luxtts", "kokoro")
    ENGLISH_ONLY = {"luxtts", "chatterbox_turbo", "chatterbox-turbo", "tada-1b", "kokoro"}
    ALIASES = {"chatterbox_tts": "chatterbox", "chatterbox-turbo": "chatterbox_turbo",
               "tada_3b_ml": "tada-3b-ml", "qwen_tts_0_6B": "qwen-tts-0.6B"}

    _live_url = None
    _model_cache = (0.0, None)

    def _probe(self):
        for base in VOICEBOX_URLS:
            for path in ("/health", "/v1/models"):
                try:
                    with urllib.request.urlopen(f"{base}{path}", timeout=1.5) as r:
                        if r.status == 200:
                            return base
                except Exception:
                    continue
        return None

    def _get(self, path, timeout=4.0):
        base = self._live_url or self._probe()
        if not base:
            return None
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None

    def downloaded_models(self):
        """TTS models the bridge already has on disk, best first."""
        now = time.time()
        stamp, cached = self._model_cache
        if cached and now - stamp < 30:
            return cached
        data = self._get("/models/status") or {}
        have = []
        for m in data.get("models") or []:
            name = (m.get("model_name") or "").lower()
            if m.get("downloaded") and not name.startswith("whisper"):
                have.append(name)
        have = [h for h in have if h in self.MODEL_PREFERENCE] or have
        order = {n: i for i, n in enumerate(self.MODEL_PREFERENCE)}
        have.sort(key=lambda h: order.get(h, 99))
        self._model_cache = (now, have)
        return have

    def resolve_model(self, requested=None):
        wanted = (requested or "").strip().lower()
        wanted = self.ALIASES.get(wanted, wanted)
        have = self.downloaded_models()
        if wanted and (wanted in have or not have):
            return wanted
        if have:
            return have[0]
        return wanted or "luxtts"

    def available(self):
        base = self._probe()
        if base:
            self._live_url = base
            models = self.downloaded_models()
            detail = f"server up on {base}"
            if models:
                detail += f" · models: {', '.join(models[:3])}"
            return True, detail
        return False, "not running"

    def supports_text(self, text, model=None):
        model = (model or "").lower()
        if model in self.ENGLISH_ONLY and any("\uac00" <= ch <= "\ud7a3" for ch in text or ""):
            return False, (f"{model} is English-only, and this text has Korean in it. "
                           "Pick the ElevenLabs clone for Korean, or install a multilingual "
                           "model in Voicebox → Models.")
        return True, ""

    def _try_start(self, wait_s=90):
        """Bring the local container back up if it is installed but stopped."""
        candidates = ["/usr/local/bin/docker", "/opt/homebrew/bin/docker",
                      "/Applications/Docker.app/Contents/Resources/bin/docker"]
        docker = shutil.which("docker")
        if not docker:
            for c in candidates:
                try:
                    if Path(c).exists():
                        docker = c
                        break
                except OSError:
                    continue
        if not docker:
            return False
        hosts = [None, f"unix://{Path.home()}/.docker/run/docker.sock"]
        started = False
        for host in hosts:
            env = dict(os.environ)
            if host:
                env["DOCKER_HOST"] = host
            try:
                out = subprocess.run([docker, "start", "voicebox"], capture_output=True,
                                     timeout=60, env=env)
                if out.returncode == 0:
                    started = True
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        if not started:
            return False
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self._probe():
                self._live_url = self._probe()
                return True
            time.sleep(2.0)
        return False

    # LuxTTS speaks about 35% faster than the reference performance it clones, so
    # narration is time-stretched to the speaker's own measured pace (13.3 chars/s).
    DEFAULT_SPEED = {"luxtts": 0.72}

    # longest text each local model takes before it falls over on CPU
    CHUNK_CAP = {"luxtts": 400, "chatterbox": 800, "chatterbox_turbo": 800,
                 "tada-3b-ml": 800, "omnivoice": 800, "qwen-tts-0.6B": 600, "kokoro": 600}

    def max_chunk_chars(self, model=None):
        resolved = self.resolve_model(model)
        return self.CHUNK_CAP.get((resolved or "").lower(), 800)

    def ensure_up(self):
        """Called when a render needs this engine: bring it back if it is asleep."""
        base = self._probe()
        if base:
            self._live_url = base
            return True, f"server up on {base}"
        if self._try_start():
            base = self._probe()
            if base:
                self._live_url = base
                return True, f"started the container, server up on {base}"
        return False, "not running (Docker or the voicebox container is stopped)"

    def _explain(self, raw):
        try:
            err = json.loads(raw).get("error") or {}
            msg = err.get("message") or ""
            code = err.get("code") or ""
        except Exception:
            return raw[:200]
        if code == "model_not_downloaded":
            return ("no TTS model is downloaded in Voicebox yet. Open Voicebox → Models "
                    "and download LuxTTS (about 1.1 GB), then press Generate again.")
        if code == "voice_not_found":
            return ("that voice name is not a Voicebox profile. The local engine needs a "
                    "profile name, for example 'Henry - RD local'.")
        return msg[:240] or raw[:200]

    def synth(self, text, voice_ref, opts=None):
        opts = opts or {}
        model = self.resolve_model(opts.get("model"))
        ok, why = self.supports_text(text, model)
        if not ok:
            raise EngineError(why)
        body = {
            "model": model,
            "voice": voice_ref,
            "input": text,
            "response_format": "wav",
        }
        if opts.get("language"):
            body["language"] = opts["language"]
        speed = opts.get("speed")
        if speed is None:
            speed = self.DEFAULT_SPEED.get((model or "").lower())
        if speed:
            body["speed"] = float(speed)
        base = self._live_url or self._probe()
        if not base and self._try_start():
            base = self._live_url or self._probe()
        if not base:
            raise EngineError("The local engine is not running. Open Docker Desktop, start the "
                              "voicebox container, then press Generate again.")
        req = urllib.request.Request(
            f"{base}/v1/audio/speech",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code >= 500 and len(text.strip()) < 40:
                raise EngineError(
                    f"the local model cannot render a piece this short (\"{text.strip()[:40]}\"). "
                    "Put a longer sentence in front of it, or merge it with the next line.")
            raise EngineError("Voicebox: " + self._explain(detail))
        except urllib.error.URLError as e:
            raise EngineError(f"Voicebox unreachable at {base} ({e.reason}). Is the container running?")
        latency = time.time() - t0
        if raw[:4] != b"RIFF":
            raise EngineError("Voicebox returned non-WAV audio (is response_format supported?)")
        arr, rate = _pcm_from_wav(raw)
        return arr, rate, {"engine": self.name, "model": model, "latency_s": round(latency, 2), "format": "wav"}


class SayEngine(Engine):
    name = "say"
    label = "macOS Speech (offline floor)"
    kind = "local"
    needs = "macOS say + afconvert"

    def available(self):
        if not shutil.which("say"):
            return False, "say missing"
        with tempfile.TemporaryDirectory() as td:
            aiff = Path(td) / "t.aiff"
            try:
                subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), "ok"],
                               check=True, capture_output=True, timeout=20)
            except Exception as e:
                return False, f"say failed: {e}"
            if aiff.stat().st_size < 8000:
                return False, "say produced no audio (sandboxed?)"
        return True, "ready"

    def synth(self, text, voice_ref, opts=None):
        opts = opts or {}
        voice = voice_ref or opts.get("say_voice") or "Samantha"
        with tempfile.TemporaryDirectory() as td:
            aiff = Path(td) / "out.aiff"
            wav = Path(td) / "out.wav"
            t0 = time.time()
            try:
                subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                               check=True, capture_output=True, timeout=300)
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050", "-c", "1",
                                str(aiff), str(wav)], check=True, capture_output=True, timeout=120)
            except Exception as e:
                raise EngineError(f"say/afconvert failed: {e}")
            latency = time.time() - t0
            arr, rate = _pcm_from_wav(wav.read_bytes())
        return arr, rate, {"engine": self.name, "model": f"macos/{voice}", "latency_s": round(latency, 2), "format": "wav"}


class ToneEngine(Engine):
    """Deterministic synthetic speech-like signal. Never a real voice.

    Used only by the measurement harness: it lets the QA math and the
    control chart be exercised without spending credits or needing models.
    """

    name = "tone"
    label = "Synthetic probe (QA harness only)"
    kind = "probe"
    needs = "none"

    def available(self):
        return True, "always"

    def synth(self, text, voice_ref, opts=None):
        rate = 24000
        syllables = max(1, len(text.strip()) // 4)
        out = array.array("h")
        seed = sum(ord(c) for c in (voice_ref or "x")) or 7
        for i in range(syllables):
            freq = 110 + (seed * 7 + i * 13) % 90
            length = int(rate * (0.11 + ((i + seed) % 5) * 0.02))
            for j in range(length):
                env = min(1.0, j / (rate * 0.02), (length - j) / (rate * 0.03))
                val = 9000 * env * (1 if (j // 12) % 2 == 0 else -1)
                out.append(int(val * 0.4 * (1 + 0.3 * ((i + j) % 5) / 5)))
            for _ in range(int(rate * 0.04)):
                out.append(0)
            freq += 1
        return out, rate, {"engine": self.name, "model": "probe", "latency_s": 0.01, "format": "pcm"}


REGISTRY = {e.name: e() for e in (ElevenLabsEngine, VoiceboxEngine, SayEngine, ToneEngine)}


def get_engine(name):
    eng = REGISTRY.get(name)
    if not eng:
        raise EngineError(f"unknown engine '{name}'")
    return eng


def engine_status():
    out = []
    for name, eng in REGISTRY.items():
        ok, why = eng.available()
        out.append({"name": name, "label": eng.label, "kind": eng.kind,
                    "needs": eng.needs, "available": ok, "detail": why,
                    "can_clone": getattr(eng, "can_clone", False)})
    return out
