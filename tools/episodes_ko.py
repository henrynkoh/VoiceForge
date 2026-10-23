#!/usr/bin/env python3
"""
VoiceForge - split the Korean audiobook into four YouTube episodes.

Same structure as the English series: a new Korean cold open and close per
episode, with the chapter WAVs already on disk stitched underneath.

Usage: python3 tools/episodes_ko.py [--dry]
"""

import argparse
import array
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voiceforge import analysis, app  # noqa: E402

BOOK_DIR = ROOT / "audiobooks"
AUDIO_DIR = BOOK_DIR / "audio-ko"
EP_DIR = BOOK_DIR / "episodes-ko"
VOICE = "henry-rd-091b"

EPISODES = [
    {
        "n": 1,
        "slug": "ko-ep1-성경이-퍼즐처럼-느껴지는-이유",
        "title": "성경이 퍼즐처럼 느껴지는 이유 | 바르게 나누기 1부",
        "chapters": [1, 2],
        "open": (
            "사랑하는 친구 여러분, 오늘부터 네 번에 걸쳐 성경을 읽는 한 가지 방법을 함께 나누려 합니다. "
            "혹시 성경을 읽다가 이런 생각을 해 보신 적이 있으십니까. 어제 읽은 본문과 오늘 읽은 본문이 같은 책에서 나온 것 같지 않다는 생각입니다. "
            "그것은 게으름이 아니라 정직함입니다. 그리고 오늘 우리는 아주 단순한 질문 하나를 배우겠습니다. "
            "이 말씀은 누구에게 주신 말씀입니까."
        ),
        "outro": (
            "1부를 마칩니다. 2부에서는 이음새 자체를 봅니다. 성경 안에 있는 두 백성에 대하여 함께 나누겠습니다."
        ),
    },
    {
        "n": 2,
        "slug": "ko-ep2-두-백성-하나가-아닙니다",
        "title": "두 백성, 하나가 아닙니다 | 바르게 나누기 2부",
        "chapters": [3, 4],
        "open": (
            "이것은 바르게 나누기 2부입니다. 지난 시간에 우리는 말씀을 곧게 자르는 법을 배웠습니다. "
            "이제 그 이음새 자체를 봅니다. 하나님의 성경 안에는 두 백성이 있고, 두 부르심이 있습니다. "
            "땅과 왕좌를 약속받은 한 나라, 그리고 하늘의 부르심을 받은 한 몸입니다. "
            "성경에는 두 백성이 있습니다. 이스라엘과 그리스도의 몸입니다. 이 둘을 구분하지 않으면 성경이 혼란스러워집니다."
        ),
        "outro": (
            "2부를 마칩니다. 3부에서는 두 복음과, 그다음에 늘 나오는 질문들을 함께 다루겠습니다."
        ),
    },
    {
        "n": 3,
        "slug": "ko-ep3-두-복음-그리고-질문들",
        "title": "두 복음, 그리고 달라지는 것들 | 바르게 나누기 3부",
        "chapters": [5, 6],
        "open": (
            "바르게 나누기 3부입니다. 이 시간은 가장 불편한 부분입니다. 구원의 길이 두 개라는 말로 들리기 때문입니다. 아닙니다. 구원자는 한 분입니다. "
            "그러나 성경 안에는 선포가 하나 이상 있습니다. 왕국의 복음과 은혜의 복음입니다. "
            "오늘 우리에게 주신 사명은 은혜의 복음입니다. 그 차이를 살펴보고, 이 가르침을 들으면 늘 나오는 다섯 가지 질문에 답하겠습니다."
        ),
        "outro": (
            "3부를 마칩니다. 마지막 4부에서는 이 모든 것이 어디로 가는지, 그리고 내일 아침 어떻게 읽을 것인지 나누겠습니다."
        ),
    },
    {
        "n": 4,
        "slug": "ko-ep4-두-목적지와-읽는-법",
        "title": "두 목적지, 그리고 내일 아침 | 바르게 나누기 4부",
        "chapters": [7, 8, 9],
        "open": (
            "마지막 4부입니다. 우리는 지금까지 곧게 자르는 명령, 두 백성, 율법과 은혜, 두 복음을 살펴보았습니다. "
            "이제 그 모든 것 아래에 있는 질문으로 갑니다. 이 모든 것은 어디로 가고 있습니까. "
            "하나님께서는 두 가지 목적을 모두 신실하게 이루십니다. 두 목적지, 혼란이 온 길, 그리고 내일 아침 성경을 여는 다섯 가지 방법을 나누겠습니다."
        ),
        "outro": (
            "이것으로 네 편의 여정을 마칩니다. 성경을 직접 여시고, 누구에게 하신 말씀인지 물으시고, 곧게 나누십시오. 함께해 주셔서 감사합니다."
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
        "language": "ko",
        "max_chunk_chars": 800,
        "crossfade_ms": 50,
        "normalize": True,
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes((app.AUDIO / rec["file"]).read_bytes())
    return rec


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
    args = ap.parse_args()

    EP_DIR.mkdir(parents=True, exist_ok=True)
    sheet = ["# 바르게 나누기 4부작", ""]
    total_chars = 0

    for ep in EPISODES:
        chars = len(ep["open"]) + len(ep["outro"])
        total_chars += chars
        print(f"\n{ep['n']}부: {ep['title']}  (새 텍스트 {chars}자)")
        if args.dry:
            continue
        open_wav = EP_DIR / f"{ep['n']:02d}-open.wav"
        outro_wav = EP_DIR / f"{ep['n']:02d}-outro.wav"
        r1 = render(ep["open"], open_wav); print(f"  오프닝 {r1['metrics']['duration_s']}s, 결함 {r1['defects'] or '없음'}")
        r2 = render(ep["outro"], outro_wav); print(f"  마무리 {r2['metrics']['duration_s']}s, 결함 {r2['defects'] or '없음'}")

        parts = [open_wav] + [chapter_file(n) for n in ep["chapters"]] + [outro_wav]
        target = EP_DIR / f"{ep['slug']}.wav"
        m = assemble(parts, target)
        print(f"  완성: {target.name}, {m['duration_s']/60:.1f}분, 결함 {analysis.defects(m) or '없음'}")

        t = 0.0
        marks = []
        for label, p in ([("오프닝", open_wav)] + [(f"{n}장", chapter_file(n)) for n in ep["chapters"]] + [("마무리", outro_wav)]):
            pcm, sr, _ = analysis.read_wav(p)
            marks.append(f"{int(t)//60}:{int(t)%60:02d} {label}")
            t += len(pcm) / sr + 1.0
        sheet += [f"## {ep['n']}부. {ep['title']}", "",
                  f"- 파일: `{ep['slug']}.wav`", f"- 길이: {m['duration_s']/60:.1f}분", "",
                  "```", *marks, "```", ""]

    print(f"\n새 낭독 합계: {total_chars}자")
    if not args.dry:
        (BOOK_DIR / "episodes-ko.md").write_text("\n".join(sheet) + "\n")
        print("wrote episodes-ko.md")


if __name__ == "__main__":
    main()
