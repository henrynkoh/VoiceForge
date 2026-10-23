# Quickstart

Five minutes from nothing to a narrated paragraph in your own voice.

## 0. What you need

- macOS with Python 3.9+ (`python3 --version`)
- **Free local engine:** Docker Desktop plus the Voicebox image, or the Voicebox desktop app
- **Cloud engine (optional):** an ElevenLabs key with `text_to_speech` and `voices_write`

Nothing else. No pip install, no build step; the app is standard library only.

## 1. Start the app

```bash
cd ~/Documents/Claude/Projects/voiceforge
python3 -m voiceforge.app
```

Or double-click `VoiceForge.command`. It opens `http://127.0.0.1:8777/` (if that port is taken it prints the port it chose, and writes it to `data/URL.txt`).

## 2. Add your voice

- **Cloud clone:** in ElevenLabs, create an Instant Voice Clone, copy the voice id, then in VoiceForge fill **Add a voice** with a name, engine `elevenlabs`, and that id.
- **Free local clone:** start Voicebox, create a profile there (three 25-second takes is plenty), then add a voice with engine `voicebox` and the profile name, for example `Henry - RD local`.

## 3. Record a clone inside the app (optional)

Press **Record**, allow the microphone once, read for 30-90 seconds, press **Stop**. The app grades the take, clones it, and plays a verification line automatically.

## 4. Render

Paste a script, pick the voice, press **Generate**. Watch the status line: duration, chunk count, which voice and model actually spoke, and any defects.

For a script that mixes English and Korean, set **Korean parts** to `ElevenLabs clone`. English goes to the free local voice, Korean to the cloud clone, and the pieces are resampled and crossfaded into one file.

## 5. Render a whole audiobook

```bash
python3 tools/audiobook.py --script audiobooks/en-only/rightly-dividing-30min-en-only.md \
    --engine voicebox --voice henry-local --all --stitch --outdir audiobooks/en-only/audio
```

Chapters are written as `01-...wav`; `--stitch` also writes the full book with a 1.2-second gap between chapters.

## 6. Package episodes

```bash
python3 tools/english_edition.py --book audiobooks/en-only --render-stings
```

That renders the eight stings, assembles the four episodes, and writes `episodes.md` and `youtube-episodes.md` with real timecodes.

## When it goes wrong

| symptom | cause | fix |
|---|---|---|
| `engine 'voicebox' unavailable: not running` | container asleep | press Generate again, the app tries to start it; or `docker start voicebox` |
| `Voicebox: no TTS model is downloaded` | no model on disk | Voicebox → Models → download LuxTTS (about 1.1 GB) |
| `luxtts is English-only` | Korean sent to an English model | set **Korean parts** to the cloud clone, or install a multilingual model |
| render dies at 800 characters | LuxTTS memory ceiling | leave Max chunk at 400; the app clamps it for you |
| `Daily upload limit reached` | YouTube channel cap | wait 24 hours, then rerun the uploader |
