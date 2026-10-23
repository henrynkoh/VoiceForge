# REA — reverse engineering analysis of voicebox

Target: **github.com/jamiepine/voicebox** (`main`, commit snapshot 2026-10-06, MIT licence,
58,189 stars, 7,303 forks, 41 MB source, 152 Python files in `backend/`).

Why this repo and not the others in the same news cycle:

| Candidate | Stars | Licence | Verdict |
|---|---|---|---|
| jamiepine/voicebox | 58,189 | MIT | chosen — MIT allows reuse, 8 TTS engines, cloning, active |
| resemble-ai/chatterbox | 27,137 | MIT | engine only, no app around it |
| offreal/voicestudio | 0 | AGPL-3.0 | hostile to reuse, no community |
| hexgrad/kokoro | 9,567 | Apache-2.0 | engine only, no cloning, no Korean |

Rule applied: reverse-engineer the *system*, borrow the *engine*. MIT on both layers means a
new app can ship without licence contamination. Check this yourself before publishing anything.

---

## 1. What the app actually is

Three processes, not one:

```
Tauri v2 desktop shell (Rust)          tauri/
      |  IPC
React + Vite front end                 web/, app/
      |  HTTP / SSE / WebSocket
FastAPI backend (Python)               backend/
      +-- engine registry (9 TTS)      backend/backends/__init__.py
      +-- SQLite via SQLAlchemy        backend/database/models.py
      +-- 118 REST endpoints           backend/routes/*.py
      +-- PyInstaller sidecar entry    backend/server.py
```

The desktop shell is packaging, not product. The product is the FastAPI backend, and that is
the part worth cloning.

## 2. The one interface that matters

Everything else in the app is plumbing around this contract (`backend/backends/__init__.py`):

```python
@dataclass
class ModelConfig:
    model_name: str          # "chatterbox-tts"
    display_name: str        # "Chatterbox TTS (Multilingual)"
    engine: str              # "chatterbox"
    hf_repo_id: str          # HuggingFace repo
    aux_hf_repo_ids: tuple   # extra tokenizer repos
    model_size: str          # "1.7B" | "0.6B" | "default"
    size_mb: int             # download size shown in the catalogue
    needs_trim: bool
    retries_runaway: bool    # <-- defect knowledge, encoded in config
    supports_instruct: bool  # delivery instructions honoured?
    languages: list[str]
```

Engines are classes implementing a `TTSBackend` protocol (`load_model`, generation, unload,
capability flags). Adding an engine = one file plus one `ModelConfig` entry. There is no
central dispatch table, which is why they can carry nine engines without the routes knowing
about any of them.

Engine inventory and the download cost a user pays to switch:

| engine id | model | size | Korean | instruct |
|---|---|---|---|---|
| `qwen` | Qwen TTS 1.7B / 0.6B | 3500 / 1200 MB | yes | no (base drops it silently) |
| `qwen_custom_voice` | Qwen CustomVoice 1.7B / 0.6B | 3500 / 1200 MB | yes | yes |
| `qwen_voice_design` | Qwen VoiceDesign 1.7B | 3500 MB | yes | yes |
| `luxtts` | LuxTTS | 300 MB | — | — |
| `chatterbox` | Chatterbox TTS multilingual | 3000–3200 MB (MLX / torch) | yes | no |
| `chatterbox_turbo` | Chatterbox Turbo, English + `[tags]` | 1500 MB | no | tags |
| `tada` | TADA 1B (HumeAI) | — | no | — |
| `kokoro` | Kokoro 82M | 350 MB | no | preset voices |
| `omnivoice` | OmniVoice | — | yes (600+) | yes |

## 3. The request contract (the part a clone must reproduce)

`backend/models.py`, class `GenerationRequest`:

| field | type / range | default | why it exists |
|---|---|---|---|
| `profile_id` | str | required | the voice, not the engine |
| `text` | 1–50000 chars | required | long-form input |
| `language` | enum, 23 codes incl. `ko` | `en` | per-request language |
| `seed` | int ≥ 0 | None | **reproducibility** |
| `model_size` | 1.7B \| 0.6B \| 1B \| 3B | 1.7B | quality vs memory |
| `instruct` | ≤ 500 chars | None | delivery direction |
| `engine` | enum of 9 | profile default | engine hop per generation |
| `personality` | bool | False | LLM rewrites text before TTS |
| `max_chunk_chars` | 100–5000 | 800 | join count |
| `crossfade_ms` | 0–500 | 50 | click suppression at joins |
| `normalize` | bool | True | level consistency |
| `effects_chain` | list | None | post-processing |

Those last four are the quality levers, exposed per request rather than buried in settings.
That design choice is the single best idea in the codebase: it makes defects addressable at
the call site instead of forcing a model swap.

## 4. How cloning works (and what it does not do)

- A **profile** owns one or more **samples**: audio file + `reference_text` (≤ 1000 chars).
- Generation passes the profile's reference audio to the engine as a speaker prompt; engines
  cache the prompt in memory and evict it on unload (see
  `backend/tests/test_voice_prompt_cache_unload.py`).
- No fine-tuning stage, no per-user training job. Clone quality is a function of sample
  cleanliness, and the repo says so in `RESPONSIBLE_USE.md`.
- Profiles also carry a per-engine preset (`GET /profiles/presets/{engine}`), so one voice can
  sound different across engines without duplicating samples.

## 5. Long text: the chunker

`backend/utils/chunked_tts.py`. Split priority, in order:

1. last sentence end (`.` `!` `?` followed by whitespace or EOL), skipping a 25-entry
   abbreviation list (`Mr.`, `e.g.`, `U.S.` …) and any punctuation inside a `[tag]`
2. CJK sentence enders `。！？`
3. clause boundary `; : — ,`
4. last whitespace
5. hard cut that refuses to bisect a `[tag]`

Then chunks are concatenated with a linear crossfade (`crossfade_ms`), and a *runaway* guard
retries a chunk when the model overshoots (`MAX_RUNAWAY_RETRIES = 2`,
`MIN_RUNAWAY_RETRY_CHARS = 100`). Encoding two real failure modes — clicks at joins and
runaway generations — as named constants is what makes the thing operable at scale.

## 6. Endpoint surface, grouped (118 total)

| group | count | representative routes |
|---|---|---|
| generation | 9 | `POST /generate`, `POST /generate/stream`, `GET /generate/{id}/status`, cancel, retry |
| profiles + samples | 14 | `GET/POST /profiles`, `POST /profiles/{id}/samples`, export |
| history | 8 | `GET /history`, `/history/stats`, export, favorite, delete failed |
| audio | 2 | `GET /audio/{generation_id}`, `/audio/version/{version_id}` |
| models | 8 | `GET /models/status`, `GET /models/progress/{name}`, delete, cache dir |
| dictation (`captures`) | 9 | `POST /captures`, refine, retranscribe, readiness |
| effects | 6 | presets, preview per generation |
| stories / channels / tasks / events | 14 | long-form assembly, per-client bindings |
| OpenAI compatibility | 3 | `POST /v1/audio/speech`, `GET /v1/models` |
| MCP | 2 | bindings for agent clients |

The OpenAI shim is the interoperability decision to copy: any client that speaks
`/v1/audio/speech` can point at the local app by changing a base URL.

## 7. What VoiceForge kept, and what it dropped

Kept (ported, credited in file headers):

- sentence-first chunker with the abbreviation and tag rules → `voiceforge/pipeline.py`
- crossfade concatenation with per-request `crossfade_ms`
- the engine-as-adapter pattern → `voiceforge/engines.py`
- the `GenerationRequest` knob set: `max_chunk_chars`, `crossfade_ms`, `normalize`, `seed`
- the OpenAI-compatible `POST /v1/audio/speech` contract → `voiceforge/app.py`

Dropped deliberately: Tauri shell, PyInstaller packaging, 16-engine catalogue, MCP server,
cloud relay, dictation, dubbing, stories. A 3-person channel does not need an app store.

Added, because the upstream has nothing like it: **per-generation audio QA and a Six Sigma
control layer** (see `docs/SIXSIGMA.md`).

## 8. Defects found in the upstream design (input to DMAIC)

| # | Observation | Evidence | Countermeasure in VoiceForge |
|---|---|---|---|
| 1 | No quality telemetry on output audio; a bad clip is only caught by a human ear | no analysis module anywhere in `backend/`; history stores text and path only | D1–D6 measurement on every generation |
| 2 | `seed` defaults to None, so identical requests vary run to run | `GenerationRequest.seed: Optional[int] = None` | seed is logged per generation, and variance is on the control chart |
| 3 | Join quality is a single global crossfade; no detection of clicks that survive it | `crossfade_ms` only, no post-check | join-click detector at chunk boundaries (D5) |
| 4 | Nine engines, four sizes, per-engine licences: switching engine silently changes whether a voice is preserved | repo's own note that clone-less engines "cannot preserve a reference speaker" | engine is recorded per generation; QA is computed per engine |
| 5 | Chunker has no Korean-specific sentence handling; it falls back to `.` and clause cuts | splitter rules are ASCII + CJK punctuation | same behaviour inherited, now visible as a defect class if it degrades rate |

Point 5 is the honest one: VoiceForge inherits the same limitation. Korean narration with
honorific-heavy sentences can still split mid-clause. The difference is that the resulting
audio is now measured and shows up on a chart instead of in a comment section.
