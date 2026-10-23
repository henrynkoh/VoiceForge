#!/usr/bin/env python3
"""
VoiceForge - Design of Experiments run.

Six Sigma "Improve" phase. Four factors known from the REA of voicebox,
two levels each, measured on the defect opportunities in analysis.py.

  A  max_chunk_chars   400 / 1600   (how many joins the audio goes through)
  B  crossfade_ms        0 / 120    (how joins are smoothed)
  C  normalize          off / on    (level control)

Usage:  python3 tools/doe.py --runs 6
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voiceforge import app, sixsigma  # noqa: E402

SCRIPT = (
    "Dear friends, welcome back to the channel. Today we open the Scriptures together "
    "and ask one simple question: who is this passage actually written to? "
    "오늘 우리가 물어볼 질문은 아주 단순합니다. 이 말씀은 과연 누구에게 주신 말씀입니까? "
    "Not every verse in your Bible is written directly to you, and once you see that, "
    "a lot of the confusion just falls away. Paul told Timothy to rightly divide. "
    "그 선을 곧게 유지하면 혼란은 사라지고 확신이 자라납니다. "
    "When you keep those lines straight, the Bible stops feeling like a puzzle and "
    "starts reading like a letter, written on purpose, to a people, in a time, with a promise."
)

RUNS = [
    ("baseline A1", {"max_chunk_chars": 1600, "crossfade_ms": 50, "normalize": True}),
    ("repeat A1", {"max_chunk_chars": 1600, "crossfade_ms": 50, "normalize": True}),
    ("A2 chunked", {"max_chunk_chars": 400, "crossfade_ms": 50, "normalize": True}),
    ("A2 B1 no-crossfade", {"max_chunk_chars": 400, "crossfade_ms": 0, "normalize": True}),
    ("A2 B2 long-crossfade", {"max_chunk_chars": 400, "crossfade_ms": 120, "normalize": True}),
    ("C1 no-normalize", {"max_chunk_chars": 1600, "crossfade_ms": 50, "normalize": False}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=len(RUNS))
    ap.add_argument("--voice", default="henry-rd")
    args = ap.parse_args()

    print(f"script: {len(SCRIPT)} chars, voice: {args.voice}")
    print(f"{'run':<22}{'chunks':>7}{'dur_s':>7}{'s/100ch':>9}{'rms':>7}{'clips':>7}{'joins':>6}{'lat':>7}  defects")
    records = []
    for name, cfg in RUNS[: args.runs]:
        payload = {
            "voice_id": args.voice,
            "engine": "elevenlabs",
            "text": SCRIPT,
            "language": "en",
            **cfg,
        }
        rec = app.run_generation(payload)
        m = rec["metrics"]
        records.append(rec)
        print(f"{name:<22}{rec['chunks']:>7}{m['duration_s']:>7}{str(m['sec_per_100chars']):>9}"
              f"{m['rms_dbfs']:>7}{m['clipping_ratio']:>7}{m['join_clicks']:>6}{rec['latency_s']:>7}"
              f"  {','.join(rec['defects']) or 'clean'}")

    summary = sixsigma.summarize(records)
    print("\nsummary")
    print(f"  units              {summary['units']}")
    print(f"  defects            {summary['defects']}")
    print(f"  DPMO               {summary['dpmo']}")
    print(f"  sigma              {summary['sigma']}")
    print(f"  pareto             {summary['pareto']}")
    print(f"  rate chart         {summary['rate_chart']}")
    print(f"  latency p50/p95    {summary['latency_p50']} / {summary['latency_p95']}")


if __name__ == "__main__":
    main()
