# Tutorial: one audiobook, start to finish

This is the real path that produced `audiobooks/en-only/`, with the timings and costs that actually came out. Follow it and you end with a 30-minute book, four episodes, and five private YouTube drafts.

## The goal

A 30-minute English study from a written script, in the author's cloned voice, split into four publishable episodes, for as close to zero cost as possible.

## Step 1. Decide where the voice comes from

Two candidates:

- **Cloud clone** (ElevenLabs Instant). Best ear, costs credits per character, needs two minutes of clean speech.
- **Local clone** (Voicebox profile). Free, copies timbre directly from your takes, runs on CPU, English-only on this machine.

Measured head to head on the same 190-character passage, against the speaker's own recordings:

| | cloud clone | local clone |
|---|---|---|
| speaker identity, cosine | 0.815 | **0.959** |
| two other speakers, for scale | 0.63-0.71 | 0.63-0.71 |
| median pitch | 176 Hz | 152 Hz (speaker: 164) |
| pace | 13.3 chars/s (speaker: 13.3) | 18.5, then **13.32** after the speed fix |
| one archaic word slip | none | "needeth" read as "needed" until slowed |

So the local clone wins on timbre, the cloud clone wins on delivery, and the delivery gap closes with a `speed` parameter. That is the whole argument for hybrid.

## Step 2. Write the script in a shape the tools understand

`## Chapter N. Title` headings, one paragraph per idea, scripture quoted exactly. The renderer splits by sentence, so no markup inside paragraphs.

If the book will be published for one audience only, decide that now. This edition removed 16 Korean paragraphs and 3 inline glosses from the bilingual script: 25,436 characters became 22,960, and 32.0 minutes became 30.0. Dropping a language is a content edit, not a settings change.

Check every scripture quotation against a KJV text source after the edit. Seven verses here, seven exact matches.

## Step 3. Render the chapters

```bash
python3 tools/audiobook.py --script audiobooks/en-only/rightly-dividing-30min-en-only.md \
    --engine voicebox --voice henry-local --all --stitch --outdir audiobooks/en-only/audio
```

What to expect on a 4-vCPU Docker VM with LuxTTS:

- about 90 seconds of compute per chunk of 400 characters,
- overall RTF 2.17: 34.8 minutes of audio from 75.5 minutes of CPU,
- one chapter every 5 to 12 minutes,
- zero defects on the six-point gauge when the pacing fix is on.

Two operational notes worth more than they look:

1. **Render serially.** Four parallel renders took the 3.8 GB VM down with an out-of-memory kill; one at a time finished the whole book.
2. **Long shells die.** A render longer than about 30 minutes outlives a single terminal call, so fire it at the running app (`tools/render_via_app.py`) and let the server finish it, then match the result by character count. Never trust "the newest record" alone; that mistake put chapter 7's audio in chapter 8's file, and the mismatch only showed up when each file was compared against its own script length.

## Step 4. Package four episodes

```bash
python3 tools/english_edition.py --book audiobooks/en-only --render-stings
```

Eight stings, about 1,500 characters in total, open and close each part. The tool assembles:

| episode | length | contents |
|---|---|---|
| Part 1, Why Your Bible Feels Like a Puzzle | 7.2 min | open, chapters 1-2, close |
| Part 2, Two Peoples, Not One | 6.6 min | open, chapters 3-4, close |
| Part 3, Two Gospels, and the Questions That Follow | 7.6 min | open, chapters 5-6, close |
| Part 4, Two Destinies, and How to Read Tomorrow | 10.0 min | open, chapters 7-9, close |

It also writes `episodes.md` and `youtube-episodes.md` with real timecodes, ready to paste into YouTube.

Two stings were re-recorded in the cloud voice on purpose: the series opening, because the first five seconds carry the brand and the local model said "Riley Dividing", and the sting quoting 2 Timothy 2:15, because the local model read "needeth" as "needed". Everything else stayed free and local. That is the hybrid rule in one sentence: **scripture and first impressions go to the best voice, the body goes to the free one.**

## Step 5. Turn audio into video

YouTube rejects audio-only files, so mux a still:

```bash
docker run --rm -v "$PWD":/b --entrypoint bash voicebox-voicebox:latest -c '
ffmpeg -loop 1 -framerate 2 -i /b/thumbs/part1.png -i /b/audio/ep1.wav \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p" \
  -c:v libx264 -preset veryfast -tune stillimage -r 2 -c:a aac -b:a 128k -b:v 500k -shortest \
  -movflags +faststart /b/video/ep1.mp4'
```

A 30-minute narration lands around 41 MB as MP4 and about 21 MB as a 96 kbps MP3 for listening.

## Step 6. Upload as drafts

```bash
python3 tools/upload_english_edition.py 5
```

It authenticates with a YouTube OAuth token, uploads each MP4 as **private**, sets the thumbnail, writes chapter timecodes into the description so YouTube builds chapters, and records video ids in `uploaded.json` so a rerun never duplicates.

YouTube enforces a daily upload cap per channel and enforces it identically on the Data API and in Studio. When you hit it, nothing partial is created: the request is refused whole, so retry the same file tomorrow.

## The ledger

| line | amount |
|---|---|
| 18 local renders, 26,508 characters | $0.00 |
| 2 cloud stings, 573 characters | 229 credits |
| **total for the 30-minute English edition** | **~$0.04** |
| same book, all cloud | 17,200 credits, ~$2.85 |
| machine time | 75.5 minutes |

## What to do differently next time

- Fix the `seed` when a series needs stable timing; unset means each run differs by a second or two.
- Keep takes 20-30 seconds for local cloning: the bridge rejects reference clips over 30 seconds.
- Raise Docker's memory to 8 GB before trying a multilingual local model. Qwen 0.6B is killed by a 3.8 GB VM during generation.
