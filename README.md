<div align="center">

# VoiceForge

**A local-first narration studio: clone your own voice, render audiobooks, and pay nothing per word.**

[![Open the landing page](https://img.shields.io/badge/OPEN%20LANDING%20PAGE-4b8ef7?style=for-the-badge&logo=githubpages&logoColor=white)](https://henrynkoh.github.io/VoiceForge/)

[![Quickstart](https://img.shields.io/badge/QUICKSTART-5%20minutes-3f9c6d?style=flat-square)](QUICKSTART.md)
[![Manual](https://img.shields.io/badge/MANUAL-full%20reference-c9a227?style=flat-square)](MANUAL.md)
[![Tutorial](https://img.shields.io/badge/TUTORIAL-end%20to%20end-c0483c?style=flat-square)](TUTORIAL.md)
[![Audiobooks](https://img.shields.io/badge/AUDIOBOOKS-what%20it%20made-4b8ef7?style=flat-square)](audiobooks/en-only/README.md)
[![Marketing kit](https://img.shields.io/badge/MARKETING%20KIT-9%20channels-8d9098?style=flat-square)](marketing/index.md)

</div>

---

## What it is

VoiceForge is a standard-library Python app that turns a script into narration in **your own cloned voice**, measures the result like a manufacturing process, and packages it for publishing. Two engines sit behind one interface:

| engine | what it is | cost |
|---|---|---|
| `voicebox` | the open-source voice studio on your own machine, reached over its OpenAI-compatible endpoint | **$0**, CPU time only |
| `elevenlabs` | a cloud instant voice clone, the quality reference | billed per character |
| `tone` | deterministic synthetic probe used by the QA harness | $0 |

Screens stay honest: every render is measured for six defects (empty, level, clipping, silence padding, join clicks, duration out of band), and the app keeps a Six Sigma control panel over the last 200 generations.

## The numbers this repo was built on

| | all cloud | hybrid (local English, cloud Korean) | local only |
|---|---|---|---|
| 30-minute audiobook | 17,200 credits | 229 credits | 0 |
| cost at $6.63 / 40,000 credits | **$2.85** | **$0.04** | **$0.00** |
| machine time | ~0 | 76 min | 76 min |
| voice identity vs the real speaker (cosine) | 0.815 | 0.959 on English | 0.959 |
| Korean narration | yes | yes | needs a multilingual local model |

Measured on one real project: a 30-minute, two-language audiobook, then a 30-minute English-only edition, then five YouTube drafts.

## Quickstart

```bash
python3 -m voiceforge.app          # serves http://127.0.0.1:8777/
```

Add a voice, paste a script, press Generate. For the free local engine, run Voicebox on your machine first; the app finds it on `127.0.0.1:17493` or `17600` and picks whichever model is already downloaded.

Full paths:

- **[QUICKSTART.md](QUICKSTART.md)** - five minutes from clone to first render
- **[MANUAL.md](MANUAL.md)** - every engine, flag, endpoint and file explained
- **[TUTORIAL.md](TUTORIAL.md)** - one audiobook built end to end, with real timings and costs
- **[docs/REA.md](docs/REA.md)** - the reverse-engineering analysis behind the design
- **[docs/SIXSIGMA.md](docs/SIXSIGMA.md)** - the measurement system

## Series workflow: one command per title

A series is where narration projects actually live, and where an agent's token bill quietly doubles, because a long session re-sends everything it has ever read. The fix is to separate the one expensive planning pass from many cheap execution passes.

| file | what it is |
|---|---|
| [SERIES.md](SERIES.md) | the plan: titles, outlines, descriptions, hashtags, thumbnail hooks. Written once. |
| [SERIES_BRIEF.md](SERIES_BRIEF.md) | the fixed brief pasted at the top of **every** per-title session. Identical prefix means the cheap part is cached. |
| [PROJECT_STATE.md](PROJECT_STATE.md) | the one file a fresh session reads to become productive in a single turn. |
| [tools/series.py](tools/series.py) | the runner. `new`, `render`, `upload`, `status`. |

```bash
python3 tools/series.py new --title "Why the Address Matters"   # scaffold script + state
python3 tools/series.py render 1                                # chapters -> audio + timecodes
python3 tools/series.py upload 1                                # still + audio -> private draft
python3 tools/series.py status                                  # every title on one screen
```

Then a fresh session per title, opening with the brief and one line naming the title. Measured on the project's own account: a heavy exchange in one long session carried 207,000 tokens per request at $0.0016; a fresh session starting from a one-page brief carries a few thousand, so the same series costs roughly a third as much and stops accumulating.

## Repository layout

```
voiceforge/     the app: http server, engines, chunker, QA, Six Sigma
tools/          audiobook renderer, single-title series runner, episode packager, Doe/MSA experiments, YouTube uploader
audiobooks/     a finished English edition: script, stings, episode sheets, upload sheet
marketing/      launch copy for Facebook, Instagram, Threads, Blogger, Naver, Tistory, WordPress, newsletter, email
docs/           the analysis and the measurement method
index.html      the landing page served by GitHub Pages
```

## Privacy by construction

The repo ships code and documents only. Your cloned-voice recordings, rendered audio, API keys and generation history stay on your machine in `data/`, which is ignored by git. There is no telemetry and no cloud call unless you choose the cloud engine.

## Licence

MIT for the code in `voiceforge/` and `tools/`. The chunker and crossfade logic are ported from [voicebox](https://github.com/jamiepine/voicebox) (MIT) and say so in the source. Narration you render is yours; Apple system voices and any cloud provider's terms still apply to their own engines.
