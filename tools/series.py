#!/usr/bin/env python3
"""
VoiceForge - one command per title.

    python3 tools/series.py new    --title "Why the Address Matters" [--n 1]
    python3 tools/series.py render 1
    python3 tools/series.py upload 1
    python3 tools/series.py status

A series lives in audiobooks/series/<slug>/ with series.json as the source of
truth. `render` writes the audio and the sheet for one title and updates that
file; `upload` muxes the still and pushes a private draft. Nothing here needs
the conversation that produced the plan, which is the point: a fresh session
costs a few thousand tokens instead of a few hundred thousand.
"""
import argparse, array, json, os, pickle, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from voiceforge import analysis, app  # noqa: E402

SERIES_ROOT = ROOT / "audiobooks" / "series"
DEFAULT_CFG = {
    "name": "Untitled series", "slug": "untitled",
    "voice_en": "henry-local", "engine_en": "voicebox",
    "voice_ko": "henry-rd", "engine_ko": "elevenlabs",
    "language": "en", "route_korean": True,
    "chunk_chars": 400, "crossfade_ms": 50, "normalize": True,
    "token": "/Users/henryoh/Documents/Claude/Projects/rightlydividing/token.pickle",
}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "title"


def series_dir(args):
    d = Path(args.dir) if args.dir else SERIES_ROOT / args.slug
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("scripts", "audio", "thumbs"):
        (d / sub).mkdir(exist_ok=True)
    return d


def load(d):
    p = d / "series.json"
    if not p.exists():
        cfg = dict(DEFAULT_CFG, titles=[])
        p.write_text(json.dumps(cfg, indent=2))
    return json.loads(p.read_text())


def save(d, cfg):
    (d / "series.json").write_text(json.dumps(cfg, indent=2))


def find_title(cfg, n):
    for t in cfg["titles"]:
        if int(t["n"]) == int(n):
            return t
    return None


def parse_chapters(text):
    """Split on '## ' headings wherever they start, including line one."""
    parts = re.split(r"(?m)^##\s+", text)
    if len(parts) == 1:
        body = text.replace("---", "").strip()
        return [{"n": 1, "title": "Whole title", "text": body}] if body else []
    out = []
    for i, part in enumerate(parts[1:], 1):
        title, _, body = part.partition("\n")
        body = body.replace("---", "").strip()
        if body:
            num = re.match(r"(?:Chapter\s+)?(\d+)", title.strip())
            out.append({"n": int(num.group(1)) if num else i,
                        "title": title.strip(), "text": body})
    return out


def mmss(sec):
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def cmd_new(args):
    d = series_dir(args)
    cfg = load(d)
    if args.slug and cfg.get("slug", "untitled") == "untitled":
        cfg["slug"] = args.slug
    if args.name:
        cfg["name"] = args.name
    n = args.n or (max([int(t["n"]) for t in cfg["titles"]], default=0) + 1)
    if find_title(cfg, n):
        sys.exit(f"title {n} already exists")
    slug = slugify(args.title)
    script = f"scripts/{n}-{slug}.md"
    p = d / script
    if not p.exists():
        p.write_text(f"## Chapter 1. {args.title}\n\nWrite the first paragraph here.\n")
    cfg["titles"].append({"n": n, "title": args.title, "slug": slug, "script": script,
                          "status": "planned", "audio": None, "duration_s": None,
                          "defects": [], "cloud_chars": 0, "video_id": None})
    cfg["titles"].sort(key=lambda t: int(t["n"]))
    save(d, cfg)
    print(f"title {n}: {args.title}")
    print(f"  script  {d / script}")
    print(f"  next    python3 tools/series.py render {n}")


def cmd_render(args):
    d = series_dir(args)
    cfg = load(d)
    t = find_title(cfg, args.n)
    if not t:
        sys.exit(f"no title {args.n}; run: python3 tools/series.py new --title \"...\"")
    script_path = d / t["script"]
    if not script_path.exists():
        sys.exit(f"missing script {script_path}")
    chapters = parse_chapters(script_path.read_text())
    if not chapters:
        sys.exit("script has no text")

    pieces, rate, marks, cloud_chars, defects = [], None, [], 0, []
    total_samples = 0
    t0 = time.time()
    for ch in chapters:
        rec = app.run_generation({
            "voice_id": cfg["voice_en"], "engine": cfg["engine_en"],
            "text": ch["text"], "language": cfg["language"],
            "max_chunk_chars": cfg["chunk_chars"], "crossfade_ms": cfg["crossfade_ms"],
            "normalize": cfg["normalize"], "route_other_language": cfg["route_korean"],
        })
        pcm, sr, _ = analysis.read_wav(app.AUDIO / rec["file"])
        rate = rate or sr
        marks.append((total_samples / rate, ch["title"]))
        pieces.append(pcm)
        total_samples += len(pcm) + int(rate * 1.0)
        defects += rec["defects"]
        if "elevenlabs" in rec.get("engines_used", []):
            cloud_chars += len(ch["text"])
        print(f"  ch{ch['n']:<3}{rec['chars']:>5} chars{rec['metrics']['duration_s']:>8.1f}s"
              f"  {','.join(rec['defects']) or 'clean'}", flush=True)

    samples = array.array("h")
    for i, pcm in enumerate(pieces):
        samples.extend(pcm)
        samples.extend(array.array("h", [0] * int(rate * 1.0)))
    out = d / "audio" / f"{t['n']:02d}-{t['slug']}.wav"
    analysis.write_wav(out, samples, rate)
    m = analysis.analyze(out, text="")
    defects += analysis.defects(m)

    sheet = [f"# {t['title']}", "",
             f"{m['duration_s']/60:.1f} minutes, {len(chapters)} chapter(s), file `{out.name}`", "",
             "```"]
    for start, label in marks:
        sheet.append(f"{mmss(start)} {label}")
    sheet += ["```", ""]
    (d / "sheets").mkdir(exist_ok=True)
    (d / "sheets" / f"{t['n']:02d}-{t['slug']}.md").write_text("\n".join(sheet))

    t.update({"status": "rendered", "audio": str(out.relative_to(d)),
              "duration_s": round(m["duration_s"], 1), "defects": defects,
              "cloud_chars": cloud_chars, "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    save(d, cfg)
    print(f"title {t['n']}: {m['duration_s']/60:.1f} min, peak {m['peak_dbfs']} dBFS, "
          f"defects {defects or 'none'}, cloud chars {cloud_chars}, wall {round(time.time()-t0)}s")
    print(f"  audio {out}")
    print(f"  next  python3 tools/series.py upload {t['n']}")


def cmd_upload(args):
    d = series_dir(args)
    cfg = load(d)
    t = find_title(cfg, args.n)
    if not t or not t.get("audio"):
        sys.exit(f"title {args.n} is not rendered yet")
    thumb = d / "thumbs" / f"{int(t['n']):02d}.png"
    if not thumb.exists():
        thumb = d / "thumbs" / "default.png"
    if not thumb.exists():
        sys.exit(f"add a thumbnail at {d}/thumbs/{int(t['n']):02d}.png (or default.png)")

    video = d / "video" / f"{int(t['n']):02d}-{t['slug']}.mp4"
    video.parent.mkdir(exist_ok=True)
    if not video.exists():
        print("muxing still + audio ...", flush=True)
        script = (
            f'ffmpeg -hide_banner -loglevel error -y -loop 1 -framerate 2 '
            f'-i /b/thumbs/{thumb.name} -i /b/{t["audio"]} '
            f'-vf "scale=1280:720:force_original_aspect_ratio=decrease,'
            f'pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p" '
            f'-c:v libx264 -preset veryfast -tune stillimage -r 2 -c:a aac -b:a 128k '
            f'-b:v 500k -shortest -movflags +faststart /b/video/{video.name}')
        env = dict(os.environ, DOCKER_HOST=_docker_host(), PATH=_docker_path())
        subprocess.run(["docker", "run", "--rm", "-v", f"{d}:/b",
                        "--entrypoint", "bash", "voicebox-voicebox:latest", "-c", script],
                       check=True, env=env)

    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = pickle.loads(Path(cfg["token"]).read_bytes())
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)
    sheet = (d / "sheets" / f"{int(t['n']):02d}-{t['slug']}.md").read_text()
    body = {"snippet": {"title": f"{t['title']} | {cfg['name']}"[:100],
                        "description": sheet[:4900], "categoryId": "27",
                        "defaultLanguage": cfg["language"],
                        "defaultAudioLanguage": cfg["language"]},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True,
                            chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(
            str(thumb), mimetype="image/png")).execute()
    except Exception as e:
        print(f"  thumbnail failed: {str(e)[:100]}")
    t.update({"status": "uploaded", "video_id": vid})
    save(d, cfg)
    print(f"title {t['n']}: uploaded private https://studio.youtube.com/video/{vid}/edit")


def _docker_host():
    return "unix:///Users/henryoh/.docker/run/docker.sock"


def _docker_path():
    return "/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin"


def cmd_status(args):
    d = series_dir(args)
    cfg = load(d)
    print(f"{cfg['name']}  ({d})")
    print(f"{'n':<3}{'title':<44}{'status':<10}{'min':>6}{'defects':>9}{'cloud ch':>10}  video")
    for t in cfg["titles"]:
        mins = f"{t['duration_s']/60:.1f}" if t.get("duration_s") else "-"
        print(f"{t['n']:<3}{t['title'][:42]:<44}{t['status']:<10}{mins:>6}"
              f"{len(t.get('defects') or []):>9}{t.get('cloud_chars', 0):>10}  {t.get('video_id') or '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="")
    ap.add_argument("--slug", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("--title", required=True); p.add_argument("--n", type=int, default=0); p.add_argument("--name", default="")
    p = sub.add_parser("render"); p.add_argument("n", type=int)
    p = sub.add_parser("upload"); p.add_argument("n", type=int)
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "new" and not args.slug and not args.dir:
        args.slug = sys.stdin.isatty() and (input("series slug [default]: ").strip() or "default") or "default"
    {"new": cmd_new, "render": cmd_render, "upload": cmd_upload, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
