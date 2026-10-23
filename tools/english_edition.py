#!/usr/bin/env python3
"""
VoiceForge - English-audience edition packager.

Renders the eight episode stings with the local clone, assembles the four
episodes from the rendered chapters, and writes the episode sheets with real
timecodes.

Usage:
  python3 tools/english_edition.py --book audiobooks/en-only --render-stings
  python3 tools/english_edition.py --book audiobooks/en-only            # assemble only
"""

import argparse
import array
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voiceforge import analysis, app  # noqa: E402

EPISODES = [
    ("ep1-why-your-bible-feels-like-a-puzzle", "Why Your Bible Feels Like a Puzzle", "Rightly Dividing, Part 1", [1, 2], ["2 Timothy 2:15"]),
    ("ep2-two-peoples-not-one", "Two Peoples, Not One", "Rightly Dividing, Part 2", [3, 4], ["Ephesians 3:2", "Ephesians 3:6"]),
    ("ep3-two-gospels-and-the-questions", "Two Gospels, and the Questions That Follow", "Rightly Dividing, Part 3", [5, 6], ["Romans 6:14", "Romans 6:23", "Matthew 4:17"]),
    ("ep4-two-destinies-and-how-to-read", "Two Destinies, and How to Read Tomorrow", "Rightly Dividing, Part 4", [7, 8, 9], ["1 Corinthians 15:3-4"]),
]


def load_stings(path):
    text = Path(path).read_text()
    return {k: " ".join(v.split()) for k, v in re.findall(r"## ([a-z0-9-]+)\n\n(.+?)(?=\n## |\Z)", text, re.S)}


def chapter_file(book, n):
    hits = sorted((book / "audio").glob(f"{n:02d}-*.wav"))
    if not hits:
        sys.exit(f"chapter {n} not rendered yet")
    return hits[0]


def mmss(seconds):
    return f"{int(seconds // 60)}:{int(round(seconds % 60)):02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="audiobooks/en-only")
    ap.add_argument("--render-stings", action="store_true")
    ap.add_argument("--voice", default="henry-local")
    ap.add_argument("--engine", default="voicebox")
    args = ap.parse_args()

    book = Path(args.book)
    audio_dir = book / "audio"
    sting_dir = book / "stings"
    sting_dir.mkdir(parents=True, exist_ok=True)

    stings = load_stings(book / "episode-stings.md")

    if args.render_stings:
        for key, text in stings.items():
            rec = app.run_generation({
                "voice_id": args.voice, "text": text, "engine": args.engine,
                "language": "en", "max_chunk_chars": 800, "crossfade_ms": 50, "normalize": True,
            })
            dest = sting_dir / f"{key}.wav"
            dest.write_bytes((app.AUDIO / rec["file"]).read_bytes())
            print(f"{key:<10}{rec['chars']:>5} chars {rec['metrics']['duration_s']:>6.1f}s "
                  f"{','.join(rec['defects']) or 'clean'}")

    rate = None
    chapters = {n: chapter_file(book, n) for n in range(1, 10)}

    # full book, chapter gap 1.2 s
    full = array.array("h")
    marks = []
    for n in range(1, 10):
        pcm, sr, _ = analysis.read_wav(chapters[n])
        rate = rate or sr
        marks.append((len(full) / sr, n))
        full.extend(pcm)
        full.extend(array.array("h", [0] * int(sr * 1.2)))
    target = audio_dir / "rightly-dividing-full-book-en-only.wav"
    analysis.write_wav(target, full, rate)
    m = analysis.analyze(target, text="")
    lines = [f"{mmss(t)} Chapter {n}" for t, n in marks]
    (audio_dir / "chapters-en-only.txt").write_text("\n".join(lines) + "\n")
    print(f"full book: {m['duration_s']/60:.1f} min, peak {m['peak_dbfs']} dBFS, defects {analysis.defects(m) or 'none'}")

    sheets, yt = [], []
    for slug, title, series, chs, verses in EPISODES:
        out = array.array("h")
        cues = []
        open_key = {"1": "p1-open", "3": "p2-open", "5": "p3-open", "7": "p4-open"}[str(chs[0])]
        close_key = {"2": "p1-close", "4": "p2-close", "6": "p3-close", "9": "p4-close"}[str(chs[-1])]
        seq = [(open_key, "Open")] + [(f"ch{n}", f"Chapter {n}") for n in chs] + [(close_key, "Close")]
        for key, label in seq:
            src = sting_dir / f"{key}.wav" if key.startswith("p") else chapters[int(key[2:])]
            pcm, sr, _ = analysis.read_wav(src)
            cues.append((len(out) / sr, label))
            out.extend(pcm)
            out.extend(array.array("h", [0] * int(sr * 1.0)))
        ep = audio_dir / f"{slug}.wav"
        analysis.write_wav(ep, out, rate)
        mm = analysis.analyze(ep, text="")
        dur = mm["duration_s"]
        cues_txt = "\n".join(f"{mmss(t)} {label}" for t, label in cues)
        sheets.append(f"## {title} | {series}\n\n{dur/60:.1f} minutes, file `{ep.name}`\n\n```\n{cues_txt}\n```\n")
        yt.append({
            "title": f"{title} | {series}", "file": ep.name, "length": f"{dur/60:.1f} minutes",
            "cues": cues_txt, "verses": ", ".join(verses),
        })
        print(f"{slug:<40}{dur/60:>5.1f} min  {','.join(analysis.defects(mm)) or 'clean'}")

    (book / "episodes.md").write_text(
        "# Rightly Dividing, a four-part series (English edition)\n\n"
        "English-only cut: no Korean narration, no bilingual framing, KJV quotations only.\n\n"
        + "\n".join(sheets))

    body = ["# YouTube upload sheet, English edition\n",
            "King James Version quotations only. Every verse verified against a KJV text source.\n"]
    for e in yt:
        body.append(f"""## {e['title']}

- file: `{e['file']}`
- length: {e['length']}
- verses: {e['verses']}

**Description**

```
{e['title']}

Rightly dividing the word of truth is not a slogan, it is a workman's job. This is part of a four-part study in the King James Bible, narrated in my own voice.

Timecodes:
{e['cues']}

Scripture in this episode:
{e['verses']}

If this helped you, subscribe for the rest of the series, and leave a comment with the passage you are studying this week.

#RightlyDividing #KJV #BibleStudy
```
""")
    (book / "youtube-episodes.md").write_text("\n".join(body))
    print("wrote episodes.md and youtube-episodes.md")


if __name__ == "__main__":
    main()
