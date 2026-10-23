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

## Repository layout

```
voiceforge/     the app: http server, engines, chunker, QA, Six Sigma
tools/          audiobook renderer, episode packager, Doe/MSA experiments, YouTube uploader
audiobooks/     a finished English edition: script, stings, episode sheets, upload sheet
marketing/      launch copy for Facebook, Instagram, Threads, Blogger, Naver, Tistory, WordPress, newsletter, email
docs/           the analysis and the measurement method
index.html      the landing page served by GitHub Pages
```

## Privacy by construction

The repo ships code and documents only. Your cloned-voice recordings, rendered audio, API keys and generation history stay on your machine in `data/`, which is ignored by git. There is no telemetry and no cloud call unless you choose the cloud engine.

## Licence

MIT for the code in `voiceforge/` and `tools/`. The chunker and crossfade logic are ported from [voicebox](https://github.com/jamiepine/voicebox) (MIT) and say so in the source. Narration you render is yours; Apple system voices and any cloud provider's terms still apply to their own engines.
