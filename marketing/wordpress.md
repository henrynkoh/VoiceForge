# WordPress

**Title:** Four cents for a 30-minute audiobook: a hybrid voice-cloning workflow

**Excerpt:** Two clones, one manuscript, one measured ledger. English on a free local model, Korean on a paid cloud clone, and a 30-minute book for the price of nothing much.

## The claim

Thirty minutes of finished narration, in a cloned human voice, for four cents. Not a demo clip: a real book, with chapters, episodes and timecodes, published.

## How the money disappears

Narration bills per character. A 22,960-character book is 22,960 characters whether the audio is one minute or one hour, so the only lever that matters is which engine reads which paragraph.

English paragraphs went to a free open-source model running on a laptop. Korean paragraphs went to a cloud clone at roughly one credit per character. The cloud bill for the entire project was 229 credits, about four cents at the plan's rate. Sending the same manuscript entirely to the cloud would have been 17,200 credits.

## What makes this reliable rather than lucky

Three engineering decisions carry the result:

1. **Chunking that respects the model.** The small local model collapses near 800 characters on CPU, so the pipeline enforces 400, sentence-aware, and crossfades the joins at 50 ms.
2. **Measurement after every render.** Six defect opportunities, from clipping to join clicks to duration out of band, with a control chart over the last 200 renders. A bad chunk is caught in seconds instead of in editing.
3. **A voice/engine contract.** Each voice is bound to the engine that can speak it, so a cloud voice id can never be sent to a local model by accident. That one bug produced the first confusing error of the project and is now impossible.

## The workflow in commands

```
python3 tools/audiobook.py --script book.md --engine voicebox --voice local --all --stitch
python3 tools/english_edition.py --book audiobooks/en-only --render-stings
python3 tools/upload_english_edition.py 5
```

Three commands: render the chapters, package the episodes, upload the drafts.

## Who this is for

People with a microphone, a manuscript, and no budget for a studio: pastors, teachers, course authors, and anyone who has been meaning to turn a written series into audio for years.

The code is MIT licensed, standard library only, and the free path needs no account.

**Call to action:** Clone the repo at https://github.com/henrynkoh/VoiceForge, open the landing page, and run the quickstart. If you only take one idea from this post, take the split: pay for the paragraphs that must be perfect, and let the free model read the rest.

Categories: audio, workflow, open source
Tags: voice cloning, audiobook, text to speech, elevenlabs, voicebox
