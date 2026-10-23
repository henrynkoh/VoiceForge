# Blogger

**Post title:** How I narrated a 30-minute audiobook in my own voice for four cents

Meta description: A measured breakdown of cloning your own voice and rendering a 30-minute audiobook, with a hybrid setup that costs four cents instead of three dollars.

Body:

Most guides about AI narration start with the plan tiers and end with "it depends". This one starts with a finished 30-minute audiobook and works backwards through the numbers, because the numbers are the interesting part.

## What was built

A 30-minute Bible study, narrated in a cloned version of my own voice, delivered as one audiobook file and as a four-part series, each part opening and closing with its own short intro and outro. Nine chapters, 22,960 characters, 30 minutes and 13 seconds of finished audio, zero defects on the project's six-point quality gauge.

## Two clones, one book

I cloned myself twice. One copy lives in ElevenLabs, a cloud service that bills per character. The other lives in Voicebox, an open-source studio running on my own machine that bills nothing.

Then I split the manuscript by language. English sections, about 35 minutes of audio, went to the free local clone. Korean sections, about 33 minutes, went to the cloud clone, because the small local model I could run on CPU is English-only.

Two short pieces went to the cloud even though they are English: the series opening, where the brand name has to be flawless, and the intro that quotes 2 Timothy 2:15, where the local model had been reading "needeth" as "needed". First impressions and Scripture go to the best voice; the body goes to the free one.

## The cost, measured

| | all cloud | hybrid | local only |
|---|---|---|---|
| credits | 17,200 | 229 | 0 |
| cost | $2.85 | $0.04 | $0.00 |
| machine time | none | 76 min | 76 min |

The hybrid number is not an estimate. It is the sum of two sting renders at 573 characters, read off the provider's own character counter.

## Three things that surprised me

**The free clone was closer to my timbre.** Against my own recordings, measured with a speaker-verification embedding, the local clone scored 0.959 and the cloud clone 0.815. Two other speakers scored 0.63 to 0.71, so both clones are clearly me, and the local one is simply closer.

**It read too fast.** The local model compressed my delivery to 18.5 characters per second where I speak at 13.3. Slowing it to my own rate took one parameter and fixed what sounded like a quality problem but was a pacing problem.

**Parallelism was a trap.** Rendering four chunks at once killed the container with an out-of-memory error. Rendering one at a time finished the whole book unattended.

## The production loop

1. Write the script with chapter headings; the renderer splits by sentence.
2. Render chapter by chapter with a chunk size the model can survive (400 characters for the small local model).
3. Measure every render; never accept one with a level, clipping, or join-click defect.
4. Render the short stings, assemble four episodes, and write out real timecodes.
5. Mux each audio file against a still image for YouTube, which rejects audio-only uploads.
6. Upload as private drafts and let the descriptions carry chapter markers.

## Is it worth it

If you narrate Scripture, teaching, or a course and you have been putting off recording it, this is the cheapest path I have found that still sounds like a person rather than a phone menu. The free path needs no account at all.

Source, documentation, and the finished English edition: https://github.com/henrynkoh/VoiceForge

Labels: voice cloning, audiobook, open source, text to speech
