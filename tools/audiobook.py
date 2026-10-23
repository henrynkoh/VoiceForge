#!/usr/bin/env python3
"""
VoiceForge - audiobook renderer.

Reads a markdown script with '## Chapter N. Title' headings, renders each chapter
through the same generation + QA path as the app, and can concatenate the result
into one audiobook file.

Usage:
  python3 tools/audiobook.py --script audiobooks/rightly-dividing-30min.md --chapters 1
  python3 tools/audiobook.py --script ... --voice henry-rd-091b --all --stitch
"""

import argparse
import array
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voiceforge import analysis, app, pipeline, sixsigma  # noqa: E402

BOOKS = Path(__file__).resolve().parent.parent / "audiobooks"


def parse_chapters(path):
    text = Path(path).read_text()
    parts = re.split(r"\n## ", text)[1:]
    chapters = []
    for part in parts:
        title, _, body = part.partition("\n")
        body = body.replace("---", "").strip()
        if not body:
            continue
        number = re.match(r"Chapter\s+(\d+)", title)
        chapters.append({
            "n": int(number.group(1)) if number else len(chapters) + 1,
            "title": title.strip(),
            "text": body,
        })
    return chapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default=str(BOOKS / "rightly-dividing-30min.md"))
    ap.add_argument("--voice", default="henry-rd-091b")
    ap.add_argument("--engine", default="elevenlabs")
    ap.add_argument("--chapters", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stitch", action="store_true")
    ap.add_argument("--outdir", default=str(BOOKS / "audio"))
    args = ap.parse_args()

    chapters = parse_chapters(args.script)
    if not chapters:
        sys.exit("no chapters found")
    wanted = chapters if args.all else [
        c for c in chapters if str(c["n"]) in {x.strip() for x in args.chapters.split(",") if x.strip()}
    ]
    if not wanted:
        sys.exit("nothing selected; use --all or --chapters 1,2")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"{'chapter':<44}{'chars':>7}{'dur_s':>8}{'rate':>7}{'lat':>7}  defects")
    records = []
    for c in wanted:
        rec = app.run_generation({
            "voice_id": args.voice,
            "text": c["text"],
            "engine": args.engine,
            "language": "en",
            "max_chunk_chars": 800,
            "crossfade_ms": 50,
            "normalize": True,
        })
        m = rec["metrics"]
        # keep a chapter-named copy next to the generated file
        src = app.AUDIO / rec["file"]
        dest = outdir / f"{c['n']:02d}-{re.sub(r'[^a-z0-9]+', '-', c['title'].lower()).strip('-')[:48]}.wav"
        dest.write_bytes(src.read_bytes())
        records.append({**rec, "chapter": c["n"], "dest": str(dest)})
        print(f"{c['title'][:42]:<44}{rec['chars']:>7}{m['duration_s']:>8.1f}"
              f"{str(m['sec_per_100chars']):>7}{rec['latency_s']:>7}  {','.join(rec['defects']) or 'clean'}")

    total_s = sum(r["metrics"]["duration_s"] for r in records)
    total_c = sum(r["chars"] for r in records)
    print(f"\n{len(records)} chapter(s), {total_c:,} characters = {total_s/60:.1f} minutes of audio")

    if args.stitch and len(records) > 1:
        samples = array.array("h")
        rate = None
        gap_s = 1.2
        for r in records:
            pcm, sr, _ = analysis.read_wav(r["dest"])
            rate = rate or sr
            samples.extend(pcm)
            samples.extend(array.array("h", [0] * int(sr * gap_s)))
        target = outdir / "rightly-dividing-full-book.wav"
        analysis.write_wav(target, samples, rate)
        m = analysis.analyze(target, text="")
        print(f"stitched: {target}")
        print(f"  total {m['duration_s']/60:.1f} min, peak {m['peak_dbfs']} dBFS, "
              f"clipping {m['clipping_ratio']:.6f}, defects {analysis.defects(m) or 'none'}")


if __name__ == "__main__":
    main()
