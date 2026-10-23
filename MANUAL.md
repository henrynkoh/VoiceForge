# Manual

Everything the app does, and where each piece lives.

## Shape of the program

```
python3 -m voiceforge.app
  voiceforge/app.py        HTTP server, page, /api routes, generation orchestration
  voiceforge/engines.py    engine adapters: elevenlabs, voicebox, say, tone
  voiceforge/pipeline.py   sentence chunker, crossfade join, normalise, resample
  voiceforge/analysis.py   WAV io, level/clipping/silence/click/rate measurement
  voiceforge/sixsigma.py   DPMO, sigma, I-MR control chart, capability
  voiceforge/cloning.py    take storage, take grading, cloud and local cloning
```

Data lives beside the code, never inside it:

```
data/voices.json          the voice library
data/generations.jsonl    one line per render, with metrics and defects
data/audio/               rendered wav files
data/samples/<voice>/     the takes a clone was built from
data/URL.txt              the address the app last served on
```

## Engines

### `voicebox` (free, local)

Talks to the open-source studio over its OpenAI-compatible endpoint, probing `127.0.0.1:17493` then `17600`.

- **Model choice is automatic.** The adapter asks `/models/status` which TTS models are on disk and picks the best available, preferring multilingual models over English-only ones. An empty Model field means "choose for me".
- **Chunk ceiling.** LuxTTS falls over near 800 characters on CPU, so the adapter caps chunk size at 400 for LuxTTS, 600 for Qwen 0.6B and 800 for the rest. The cap is applied before chunking, so long-paragraph scripts stay safe.
- **Pace.** LuxTTS speaks about 35% faster than the performance it clones, so narration is time-stretched to the speaker's own measured rate (13.3 characters per second) through the bridge's `speed` parameter.
- **Auto-start.** If the container is installed but stopped, the next Generate starts it and waits up to 90 seconds.

### `elevenlabs` (cloud, quality reference)

Uses `POST /v1/text-to-speech/{voice_id}` with `eleven_multilingual_v2` by default, returning 24 kHz PCM. Bills one credit per character on the reference plan; see `docs/SIXSIGMA.md` for how credits were measured.

### `tone` (probe)

A deterministic synthetic signal used by the measurement harness. Never a real voice. Use it with the `QA probe (synthetic)` voice to exercise the whole pipeline without spending credits.

## Voices and the engine/voice contract

Each library entry carries its own engine. The two can never disagree:

- picking a voice sets its engine,
- picking an engine selects a voice that belongs to it,
- a request whose voice does not match the engine is reconciled server-side: a voice from the same engine is substituted and the substitution is written into the render record as `note`.

`data/voices.json` entry:

```json
{"id": "henry-local", "name": "Henry - RD local", "engine": "voicebox",
 "ref": "Henry - RD local", "language": "en", "provider": "local"}
```

## Generation knobs

| knob | what it does | sane default |
|---|---|---|
| `max_chunk_chars` | sentence-aware split size | 400 local, 800 cloud |
| `crossfade_ms` | overlap at chunk joins | 50 |
| `normalize` | peak to -1 dBFS, RMS to -16 | on |
| `seed` | cloud determinism; unset means different timing per run | unset |
| `language` | engine hint | the voice's language |

## Mixed-language routing

`route_other_language: true` splits the script by script (Hangul vs everything else), sends each run to an engine that can speak it, resamples both sides to one rate and joins them with the same crossfade. English stays free and local, Korean goes to the cloud clone. The UI exposes it as **Korean parts: same engine / ElevenLabs clone**, and the render record shows `engines_used` and `mixed_engines`.

## Measurement

Every render gets six defect opportunities: `empty`, level out of band, clipping, silence padding, join clicks, duration out of band. The control panel reports DPMO, sigma, first-pass yield, a defect pareto and an I-MR chart over the last 200 generations; `/api/metrics` returns the same summary as JSON.

Duration bands are language aware. Korean runs 13.6-16.2 seconds per 100 characters where English runs 6.9-8.1, so the `D6_DURATION` limit is 18.0 rather than 14.

## HTTP API

| method | path | body / notes |
|---|---|---|
| GET | `/api/state` | voices, engine availability, history, Six Sigma summary |
| POST | `/api/voices` | `{name, engine, ref}` |
| POST | `/api/generate` | `{voice_id, text, engine, max_chunk_chars, crossfade_ms, normalize, seed, language, route_other_language}` |
| POST | `/v1/audio/speech` | OpenAI-compatible `{model, voice, input, response_format}` |
| GET | `/audio/<file>` | a rendered wav |
| POST | `/api/samples` | `{voice_key, audio_b64}` take upload |
| POST | `/api/clone` | `{name, provider, voice_key}` clone and verify |
| GET | `/api/history` | render records |
| POST | `/api/shutdown` | stop the app |

## Tools

```bash
tools/audiobook.py          chapters -> wav (+ --stitch full book)
tools/english_edition.py    stings + episode assembly + upload sheets
tools/render_via_app.py     drive a running app for renders longer than one shell call
tools/render_chapter_exact.py  one chapter, matched to its script by character count
tools/upload_english_edition.py  YouTube drafts with thumbnails, idempotent
tools/episodes.py, episodes_ko.py, msa.py, doe.py, local_profile.py  experiments and analysis
```

## Environment

| variable | effect |
|---|---|
| `VOICEFORGE_PORT` | preferred port, default 8777 |
| `VOICEFORGE_DATA` | data directory, default `./data` |
| `VOICEFORGE_VOICEBOX_URL` | pin the local bridge address |
| `VOICEFORGE_ELEVEN_API` | pin the cloud API base |
| `ELEVENLABS_API_KEY` | key inline instead of `.elevenlabs_key` |

## Troubleshooting

| symptom | meaning | fix |
|---|---|---|
| `engine changed sample rate mid-run` | two engines at different rates | handled automatically by resampling; if it reappears, check `pipeline.resample` |
| `the local model cannot render a piece this short` | a two-word chunk | put a longer sentence in front of it |
| `model_not_downloaded` | no model on disk | download one in Voicebox → Models |
| container restarts mid-render | out of memory | render serially, keep chunks at 400, give Docker more RAM |
| voice id rejected with `not a Voicebox voice profile` | an ElevenLabs id sent to the local engine | the app now substitutes a valid voice; check the `note` field |
