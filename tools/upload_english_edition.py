#!/usr/bin/env python3
"""Upload the English edition to YouTube as unpublished (draft) videos.

Uses the existing Rightly Dividing OAuth token, uploads each MP4 as private,
sets its thumbnail, and records the returned video ids in uploaded.json so a
rerun only touches what is missing.
"""
import json, pickle, re, sys, time
from pathlib import Path
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "audiobooks/en-only"
TOKEN = Path("/Users/henryoh/Documents/Claude/Projects/rightlydividing/token.pickle")
STATE = BOOK / "uploaded.json"

TAGS = ["Rightly Dividing", "KJV", "King James Bible", "Bible study",
        "dispensational truth", "grace", "2 Timothy 2:15", "KJV audio Bible"]

ITEMS = [
    ("book", "rightly-dividing-full-book-en-only", "book"),
    ("part1", "ep1-why-your-bible-feels-like-a-puzzle", "part1"),
    ("part2", "ep2-two-peoples-not-one", "part2"),
    ("part3", "ep3-two-gospels-and-the-questions", "part3"),
    ("part4", "ep4-two-destinies-and-how-to-read", "part4"),
]


def ep_sheets():
    text = (BOOK / "youtube-episodes.md").read_text()
    out = {}
    for block in text.split("\n## ")[1:]:
        title = block.split("\n", 1)[0].strip()
        fence = re.search(r"```\n(.*?)\n```", block, re.S)
        slug = re.search(r"file: `([^`]+)\.wav`", block)
        if fence and slug:
            out[slug.group(1)] = {"title": title, "description": fence.group(1).strip()}
    return out


def book_entry():
    marks = (BOOK / "audio/chapters-en-only.txt").read_text().strip()
    desc = f"""Rightly Dividing the Word of Truth | The Full Book

A thirty-minute study in the King James Bible, narrated in my own voice. One question runs through the whole book: who is this written to? Not every verse in your Bible is written directly to you, and once you see that, a lot of the confusion falls away.

Chapters:
{marks}

Scripture quoted in this book:
2 Timothy 2:15, Ephesians 3:2, Ephesians 3:6, Romans 6:14, Romans 6:23, Matthew 4:17, 1 Corinthians 15:3-4

Every verse is the King James Version, quoted exactly.

Also available as a four-part series:
Part 1, Why Your Bible Feels Like a Puzzle
Part 2, Two Peoples, Not One
Part 3, Two Gospels, and the Questions That Follow
Part 4, Two Destinies, and How to Read Tomorrow

If this helped you, subscribe, and leave a comment with the passage you are studying this week.

#RightlyDividing #KJV #BibleStudy"""
    return {"title": "Rightly Dividing the Word of Truth | Full Book, 30 Minutes (KJV)", "description": desc}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    creds = pickle.loads(TOKEN.read_bytes())
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    sheets = ep_sheets()

    done = 0
    for key, slug, thumb in ITEMS:
        if key in state:
            print(f"{key}: already uploaded {state[key]['id']}"); continue
        if done >= limit:
            print("call limit reached"); return
        meta = book_entry() if key == "book" else sheets.get(slug)
        if not meta:
            print(f"{key}: no metadata, skipped"); continue
        body = {
            "snippet": {"title": meta["title"][:100], "description": meta["description"][:4900],
                        "tags": TAGS, "categoryId": "27", "defaultLanguage": "en",
                        "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                       "license": "youtube", "embeddable": True},
        }
        media = MediaFileUpload(str(BOOK / "video" / f"{slug}.mp4"),
                                mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
        print(f"{key}: uploading {slug} ...", flush=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                print(f"   {int(status.progress() * 100)}%", flush=True)
        vid = resp["id"]
        state[key] = {"id": vid, "title": meta["title"], "privacy": "private"}
        STATE.write_text(json.dumps(state, indent=2))
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(
                str(BOOK / "thumbs" / f"{thumb}.jpg"), mimetype="image/jpeg")).execute()
            print(f"{key}: uploaded {vid} + thumbnail", flush=True)
        except Exception as e:
            print(f"{key}: uploaded {vid}, thumbnail failed: {str(e)[:120]}", flush=True)
        done += 1


if __name__ == "__main__":
    main()
