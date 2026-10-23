# Rightly Dividing, English edition

An English-only cut of the 30-minute audiobook, made for listeners who speak English and
nothing else. Same teaching, same nine chapters, no Korean narration and no bilingual
framing.

## What changed from the bilingual build

- 16 Korean paragraphs and 3 inline Korean glosses removed; the teaching now stands on its
  own in English. 25,436 -> 22,960 characters.
- Scripture rule is King James Version only. All seven quotations re-checked word for word
  against a KJV text source after the edit.
- Eight new English stings (`episode-stings.md`) replace the old bilingual opens and closes.
- New upload sheet written for an English audience.

## Files

| file | length | voice |
|---|---|---|
| `audio/01..09-*.wav` | 29.8 min total | local clone (LuxTTS, free) |
| `audio/rightly-dividing-full-book-en-only.wav` | 30.0 min | local clone |
| `audio/ep1-why-your-bible-feels-like-a-puzzle.wav` | 7.2 min | local + cloud open |
| `audio/ep2-two-peoples-not-one.wav` | 6.6 min | local + cloud open |
| `audio/ep3-two-gospels-and-the-questions.wav` | 7.6 min | local |
| `audio/ep4-two-destinies-and-how-to-read.wav` | 10.0 min | local |
| `audio/chapters-en-only.txt` | timecodes | - |
| `episodes.md`, `youtube-episodes.md` | sheets | - |
| `episode-stings.md` | 8 stings, 1,487 chars | - |

## Ledger

- Local renders: 18 requests, 26,508 characters, 34.8 minutes of audio, 75.5 minutes of CPU
  (RTF 2.17), zero defects on the app's six-point QA gauge.
- Cloud renders: 2 stings, 573 characters, 229 credits, about $0.04.
- Total: **$0.04**, against 17,200 credits (~$2.85) for the all-cloud bilingual build.

Two stings went to the cloud on purpose: `p1-open` because the first words of a series
should be flawless, and `p2-open` because the local model read "needeth not" as "needed
not" in the 2 Timothy quotation. Everything else is the free local clone.

## Re-render

```
python3 tools/audiobook.py --script audiobooks/en-only/rightly-dividing-30min-en-only.md \
    --engine voicebox --voice henry-local --all --stitch --outdir audiobooks/en-only/audio
python3 tools/english_edition.py --book audiobooks/en-only --render-stings
```

The local engine time-stretches LuxTTS to the speaker's own measured pace (13.3 characters
per second, `DEFAULT_SPEED = 0.72` in `engines.py`).
