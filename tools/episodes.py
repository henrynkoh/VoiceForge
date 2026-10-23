#!/usr/bin/env python3
"""
VoiceForge - cut the audiobook into YouTube episodes.

Each episode gets its own cold open and outro, then the chapter WAVs already on
disk are stitched underneath. Only the new opening/outro text is rendered, so the
episodes cost a fraction of the book.

Usage: python3 tools/episodes.py            # render openings and assemble
       python3 tools/episodes.py --dry      # show the plan, render nothing
"""

import argparse
import array
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voiceforge import analysis, app  # noqa: E402

BOOK_DIR = ROOT / "audiobooks"
AUDIO_DIR = BOOK_DIR / "audio"
EP_DIR = BOOK_DIR / "episodes"

VOICE = "henry-rd-091b"

EPISODES = [
    {
        "n": 1,
        "title": "Why Your Bible Feels Like a Puzzle | Rightly Dividing, Part 1",
        "slug": "ep1-why-your-bible-feels-like-a-puzzle",
        "chapters": [1, 2],
        "open": (
            "Friend, welcome back. This is part one of four, and it starts with a question that has "
            "closed more Bibles than any argument ever has. Not, is the Bible true. But, why does it "
            "read like a puzzle with pieces missing? If you have ever finished a chapter and quietly "
            "wondered why it did not sound like the last one, you are not careless. You are reading a "
            "book with more than one address on it. 오늘 우리가 물어볼 질문은 아주 단순합니다. 이 말씀은 "
            "과연 누구에게 주신 말씀입니까. In the next eight minutes we will look at one verse that "
            "commands us to cut straight, and we will learn the question that unlocks the rest of the Book."
        ),
        "outro": (
            "That is part one. Part two opens the seam itself, and shows you two peoples in one Bible. "
            "1부를 마칩니다. 2부에서 뵙겠습니다."
        ),
    },
    {
        "n": 2,
        "title": "Two Peoples, Not One | Rightly Dividing, Part 2",
        "slug": "ep2-two-peoples-not-one",
        "chapters": [3, 4],
        "open": (
            "This is part two of four. Last time we learned to cut straight. Now we look at the seam "
            "itself, because the biggest reason the Bible confuses honest readers is that it contains "
            "two peoples with two callings, and we were taught to read them as one. A nation with a land "
            "and a throne. And a body with a heavenly calling and no land at all. 성경에는 두 백성이 있습니다. "
            "이스라엘과 그리스도의 몸입니다. Then we will look at law and grace, and why mixing them makes "
            "a third thing God never gave."
        ),
        "outro": (
            "That is part two. Part three takes up the two gospels, and the questions people always ask "
            "next. 2부를 마칩니다. 3부에서 뵙겠습니다."
        ),
    },
    {
        "n": 3,
        "title": "Two Gospels, and the Questions That Follow | Rightly Dividing, Part 3",
        "slug": "ep3-two-gospels-and-the-questions",
        "chapters": [5, 6],
        "open": (
            "This is part three of four, and it is the one that troubles people most, because it sounds "
            "at first like two ways of being saved. It is not. There is one Saviour. But there is more "
            "than one announcement in your Bible, and the announcements were made to different people "
            "about different things. 오늘 우리에게 주신 사명은 은혜의 복음입니다. We will compare the gospel "
            "of the kingdom with the gospel of grace, and then we will answer the five questions that come "
            "up every single time this is taught."
        ),
        "outro": (
            "That is part three. Part four ends where the whole story ends, with two destinies and a "
            "simple way to read tomorrow morning. 3부를 마칩니다. 마지막 4부에서 뵙겠습니다."
        ),
    },
    {
        "n": 4,
        "title": "Two Destinies, and How to Read Tomorrow | Rightly Dividing, Part 4",
        "slug": "ep4-two-destinies-and-how-to-read",
        "chapters": [7, 8, 9],
        "open": (
            "This is the last of four parts. We have looked at the command to cut straight, at two "
            "peoples, at law and grace, and at two gospels. Now we come to the question underneath all "
            "of them. Where is all of this going? Because God is not taking everyone to the same place, "
            "and He never said He would. 하나님께서는 두 가지 목적을 모두 신실하게 이루십니다. We will look at "
            "two destinies, at where the confusion came from, and then I will give you five plain things "
            "to do tomorrow morning with your Bible open."
        ),
        "outro": (
            "That is the series. If it helped you, read the Book yourself, ask who it was written to, and "
            "cut straight. 함께해 주셔서 감사합니다. 주 예수 그리스도를 믿으십시오."
        ),
    },
]


def chapter_file(n):
    matches = sorted(AUDIO_DIR.glob(f"{n:02d}-*.wav"))
    if not matches:
        raise SystemExit(f"missing chapter {n} in {AUDIO_DIR}")
    return matches[0]


def render(text, out_path):
    rec = app.run_generation({
        "voice_id": VOICE,
        "text": text,
        "engine": "elevenlabs",
        "language": "en",
        "max_chunk_chars": 800,
        "crossfade_ms": 50,
        "normalize": True,
    })
    src = app.AUDIO / rec["file"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(src.read_bytes())
    return rec, out_path


def assemble(parts, out_path, gap_s=1.0):
    samples = array.array("h")
    rate = None
    for p in parts:
        pcm, sr, _ = analysis.read_wav(p)
        rate = rate or sr
        samples.extend(pcm)
        samples.extend(array.array("h", [0] * int(sr * gap_s)))
    analysis.write_wav(out_path, samples, rate)
    return analysis.analyze(out_path, text="")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--skip-render", action="store_true", help="reuse opening files already on disk")
    args = ap.parse_args()

    EP_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Rightly Dividing, a four-part series", ""]
    total_chars = 0

    for ep in EPISODES:
        chars = len(ep["open"]) + len(ep["outro"])
        total_chars += chars
        print(f"\nEpisode {ep['n']}: {ep['title']}")
        print(f"  chapters {ep['chapters']}, new text {chars} chars")
        if args.dry:
            continue

        open_wav = EP_DIR / f"ep{ep['n']}-open.wav"
        outro_wav = EP_DIR / f"ep{ep['n']}-outro.wav"
        if not (args.skip_render and open_wav.exists()):
            rec, _ = render(ep["open"], open_wav)
            print(f"  opening rendered: {rec['metrics']['duration_s']}s, defects {rec['defects'] or 'none'}")
        if not (args.skip_render and outro_wav.exists()):
            rec, _ = render(ep["outro"], outro_wav)
            print(f"  outro rendered:   {rec['metrics']['duration_s']}s, defects {rec['defects'] or 'none'}")

        parts = [open_wav] + [chapter_file(n) for n in ep["chapters"]] + [outro_wav]
        target = EP_DIR / f"{ep['slug']}.wav"
        m = assemble(parts, target)
        defects = analysis.defects(m)
        print(f"  episode file: {target.name}, {m['duration_s']/60:.1f} min, "
              f"peak {m['peak_dbfs']} dBFS, defects {defects or 'none'}")

        # timestamps for the YouTube description
        t = 0.0
        marks = []
        for label, p in [("Open", open_wav)] + [(f"Chapter {n}", chapter_file(n)) for n in ep["chapters"]] + [("Close", outro_wav)]:
            pcm, sr, _ = analysis.read_wav(p)
            marks.append((f"{int(t)//60}:{int(t)%60:02d}", label))
            t += len(pcm) / sr + 1.0
        lines.append(f"## Part {ep['n']}. {ep['title']}")
        lines.append("")
        lines.append(f"{m['duration_s']/60:.1f} minutes, file `{ep['slug']}.wav`")
        lines.append("")
        lines.append("```")
        for ts, label in marks:
            lines.append(f"{ts} {label}")
        lines.append("```")
        lines.append("")

    print(f"\nnew narration total: {total_chars} characters")
    if not args.dry:
        (BOOK_DIR / "episodes.md").write_text("\n".join(lines) + "\n")
        print(f"wrote {BOOK_DIR / 'episodes.md'}")


if __name__ == "__main__":
    main()
