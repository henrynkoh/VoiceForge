# Six Sigma control plan — VoiceForge

**Project charter.** Deliver narration for the Rightly Dividing channel that is clean on the
first render, so a video never waits on a re-record. Scope: one generation = one script →
one audio file. Out of scope: music, video assembly, upload.

**Y (the output metric).** DPMO of audio defects per generation, measured automatically.
**Target.** DPMO ≤ 3,400 (4.0σ with the 1.5σ shift). **Entitlement.** 0 measurable defects,
which is what the current engine already delivers — so the real work is *keeping* it there
when engines change, and closing the blind spots listed in section 8.

---

## 1. CTQ tree

```
Clean narration
├── Intelligible
│   ├── no truncated or runaway render      -> D6 duration
│   └── word accuracy (not yet measured, see 8.1)
├── Audible
│   ├── level inside -34..-10 dBFS RMS      -> D2 level
│   ├── no hard clipping                    -> D3 clipping
│   └── not silent                          -> D1 empty
├── Smooth
│   ├── no click at a chunk join            -> D5 join click
│   └── head/tail padding within bounds     -> D4 silence pad
└── Fast enough to iterate
    └── wall time per render                -> recorded, charted, not a defect
```

## 2. Operational definitions (the unit and its opportunities)

Unit = **1 generation**. Opportunities per unit = **6**. Every definition is checked in
`voiceforge/analysis.py` and `defects()`.

| code | definition | spec | how it is computed |
|---|---|---|---|
| D1_EMPTY | no audio above the silence floor | peak < -45 dBFS | global peak |
| D2_LEVEL | too quiet or too hot | -34 ≤ RMS ≤ -10 dBFS | RMS over whole file |
| D3_CLIPPING | flat-topped samples | < 0.05% of frames at ≥ 0.999 FS | sample count |
| D4_SILENCE_PAD | dead air at the edges | lead ≤ 1.2 s, tail ≤ 2.0 s | first/last sample above -45 dBFS |
| D5_JOIN_CLICK | splice step left by chunking | 0 events | adjacent-sample step > 35% FS within 5 ms of a known boundary |
| D6_DURATION | rate outside the plausible band | 3.0 ≤ s/100 chars ≤ 14.0 | duration ÷ characters × 100 |

D6 is the truncation and runaway detector. The band comes from measured speech rate, not from
taste: the clone runs 7.0–8.1 s per 100 characters.

## 3. Measurement system validation (MSA)

A gauge that cannot see the defect makes the control chart decoration. `tools/msa.py` seeds
seven known conditions into synthetic audio and checks the detector:

```
seeded defect         expected                      found                         ok
clean control         none                          none                          PASS
silent file           D1_EMPTY                      D1_EMPTY                      PASS
too quiet             D2_LEVEL                      D2_LEVEL                      PASS
clipped               D3_CLIPPING,D2_LEVEL          D2_LEVEL,D3_CLIPPING          PASS
silence padding       D4_SILENCE_PAD                D4_SILENCE_PAD                PASS
join click            D5_JOIN_CLICK                 D5_JOIN_CLICK                 PASS
duration out of spec  D6_DURATION                   D6_DURATION                   PASS

detection 7/7      false positives on clean control: none
```

Re-run it after any change to `analysis.py`. If detection drops, the metric is void, not the audio.

## 4. Baseline (Measure)

Seven real generations, Henry - RD Narration, ElevenLabs Multilingual v2, 24 kHz PCM,
17–44 s of audio. Cost of the whole study: 1,396 credits.

| # | settings | chars | chunks | dur s | s/100ch | RMS dBFS | clip | joins | latency s | RTF |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | baseline | 128 | 1 | 9.94 | 7.76 | -16.4 | 0 | 0 | 2.02 | 0.20 |
| 2 | 1600 / 50 | 558 | 1 | 40.64 | 7.28 | -18.7 | 0 | 0 | 7.13 | 0.17 |
| 3 | 1600 / 50 (repeat of 2) | 558 | 1 | 43.47 | 7.79 | -17.9 | 0 | 0 | 7.75 | 0.17 |
| 4 | 400 / 50 | 558 | 2 | 39.15 | 7.02 | -18.8 | 0 | 0 | 7.18 | 0.17 |
| 5 | 400 / 0 | 558 | 2 | 43.61 | 7.81 | -17.5 | 0 | 0 | 6.02 | 0.13 |
| 6 | 400 / 120 | 558 | 2 | 44.04 | 7.89 | -18.9 | 0 | 0 | 7.67 | 0.17 |
| 7 | UI run, 800 / 50 | 111 | 1 | 8.96 | 8.07 | -18.3 | 0 | 0 | 2.20 | 0.24 |

Result: **0 defects in 7 units → DPMO 0, process sigma 8.5σ (censored, zero-defect sample),
first-pass yield 100%.** Latency p50 7.1 s, p95 7.7 s.

## 5. Analyse — what the data actually says

**5.1 The repeatability finding (the real defect risk).** Runs 2 and 3 are the *same text with
the same settings*: 40.64 s versus 43.47 s. That is +7.0% of duration on an identical request,
because the request carries no seed. It did not break the D6 spec (both inside 3–14 s/100ch),
but it shifts every downstream timing decision: caption sync, scene cuts, and the promise that
a 5-minute script fills a 5-minute slot. This is the top item for control, not a cosmetic detail.

**5.2 Crossfade did not prove itself at these lengths.** Runs 4, 5, 6 vary the join treatment
from 0 ms to 120 ms and produced **zero** join clicks in all three. At 400-character chunks the
engine already pads boundaries, so the crossfade was undetectable in this design. Honest read:
keep the 50 ms default because it costs nothing and helps at rougher seams, but do not claim it
is proven at this scale. To prove it, the test needs chunk lengths that cut mid-clause, or a
different engine.

**5.3 Latency is generation-bound, not chunk-bound.** RTF 0.13–0.24 means the engine renders
4–8× faster than the audio plays. Latency clusters at ~2 s for short text and 6–8 s for ~40 s
of audio, i.e. it scales with output length, and chunking at 400 chars did not make it slower.
Video iteration is therefore not latency-limited; it is credit-limited (see 6.3).

**5.4 Capability against the rate spec.** With spec 3.0–14.0 s/100 chars: Cp 4.95, Cpk 4.19,
mean 7.66, sd 0.37. The process sits comfortably inside a wide spec, which is why D6 alone is a
weak gauge — it catches truncation and runaway, not subtle drift. That is what the I-MR chart
is for.

## 6. Improve — countermeasures

| # | countermeasure | status |
|---|---|---|
| 1 | log `seed` on every generation; fix a seed for series intros and outros so timing is stable | implemented (field logged), policy is yours to adopt |
| 2 | default `max_chunk_chars` 800, `crossfade_ms` 50, `normalize` on | implemented as defaults |
| 3 | measure every render and chart rate per engine, so an engine switch cannot silently degrade quality | implemented |
| 4 | treat latency from *measured duration*, not from text length, when planning scenes | recommended workflow |
| 5 | add ASR-based word error rate as the seventh defect opportunity | not built, see 8.1 |
| 6 | freeze one engine per channel format, record it in the generation record | implemented (`engine` + `model` on each row) |

## 7. Control — the phase to hand over

**I-MR chart, s per 100 characters** (n = 7): center **7.66**, UCL **8.91**, LCL **6.41**,
σ-hat **0.415**.

Reaction rules, in plain terms:

- One point outside UCL/LCL → stop and listen to that file before publishing.
- Two of three consecutive points beyond 2σ on the same side → engine drift or a text class
  that splits badly; check Korean honorific sentences first.
- Nine points in a row on one side of center → re-baseline the center, something changed
  upstream (model update, engine switch).
- Any D1, D3 or D5 → do not publish that render; re-run with `normalize` on and crossfade 50.

Cadence: re-run `tools/doe.py --runs 2` monthly to refresh the center line, and re-baseline
after any engine or model change. The chart lives in the app, not in a spreadsheet, so it
cannot fall out of date silently.

## 7b. Cloning as a second process

The narration metric assumes a good voice exists. Producing that voice is its own process with
its own CTQs, so it gets its own gate (`voiceforge/cloning.py`):

| input CTQ | spec | failure mode it prevents |
|---|---|---|
| sample duration | 5-300 s | nothing to learn from / wasted voice slot |
| sample level | ≥ -38 dBFS RMS | a thin, quiet clone forever |
| sample clipping | ≤ 0.1% of frames | brittle, harsh output on loud syllables |
| lead-in silence | ≤ 2 s | dead air copied into every render |

Acceptance test for a new clone: the verification render (one English sentence plus one Korean
sentence, ~140 characters) must produce zero defects on the same six-item gauge used for
narration. That is the cloning equivalent of a first-article inspection: the voice is not
"ready" because the upload finished, it is ready because it spoke and measured clean.

Measured on the pipeline proof run (2026-10-21): 43.5 s sample, -17.9 dBFS, no clipping →
clone registered → verification render 4.09 s, zero defects. The throwaway voice was deleted
afterwards so it would not consume one of the account's instant-clone slots.

## 8. Honest limits

**8.1 No intelligibility gauge.** Nothing here measures word accuracy. Everything is
signal-level. A render can pass all six checks and still mispronounce a name, or read
"2 Timothy" as "two Timothy" when you wanted "second Timothy". Closing this needs a
transcript-based defect: synthesize → transcribe with Whisper → word error rate against the
script. That is the next measurement to build, and it is the only one that would catch the
error class a viewer actually notices.

**8.2 Korean is under-covered.** The chunker's sentence rules are ASCII and CJK punctuation;
Korean honorific endings (…습니다, …입니다) carry no terminal punctuation inside a sentence, so
long Korean paragraphs rely on clause and whitespace cuts. Rate and level still detect a bad
render, but a mid-clause split can sound wrong while staying inside spec.

**8.3 The gauge still cannot hear words.** A clone can pass the gate, pass the verification
render, and still pronounce "2 Timothy" as "two Timothy". Sample cleanliness is necessary, not
sufficient. This is the same blind spot as 8.1, now attached to the voice instead of the render.

**8.4 Zero defects is a statement about this sample, not about the process.** Seven clean
renders give DPMO 0 and a censored 8.5σ. The rule of three says a zero-defect sample of 7
units only bounds the defect rate below ~43% at 95% confidence. More units, and a harder gauge
(8.1), are what turn this from a clean start into a controlled process.
