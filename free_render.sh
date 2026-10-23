#!/bin/bash
# VoiceForge - render the audiobook on the free local engine.
#
# What this does, in order:
#   1. makes sure Docker Desktop is running
#   2. builds and starts the local voicebox stack
#   3. waits for its API
#   4. creates a local voice profile from your recorded samples (transcribes them
#      so the clone gets a reference transcript)
#   5. renders the whole book with that profile, no credits spent
#
# Usage:  ./free_render.sh            full run
#         ./free_render.sh --status   only report readiness
#
# The first run downloads container images and a model (300 MB to 3.2 GB), so it
# is slow once. Later runs reuse everything.

set -u
cd "$(dirname "$0")" || exit 1

DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker

# Docker Desktop on macOS keeps its socket in ~/.docker/run and only sometimes links
# /var/run/docker.sock, so probe both and export whichever answers.
if [ -z "${DOCKER_HOST:-}" ]; then
  for sock in "$HOME/.docker/run/docker.sock" /Users/henryoh/.docker/run/docker.sock /var/run/docker.sock; do
    [ -S "$sock" ] || continue
    if DOCKER_HOST="unix://$sock" "$DOCKER" version --format '{{.Server.Version}}' >/dev/null 2>&1; then
      export DOCKER_HOST="unix://$sock"
      break
    fi
  done
fi
STACK=upstream/voicebox
PROFILE_NAME="Henry - RD local"
SAMPLES_DIR=data/samples/henry-rd
OUTDIR=audiobooks/audio-local
BASE=""

say() { printf '%s\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }

wait_for() {           # wait_for <seconds> <command...>
  local deadline=$((SECONDS + $1)); shift
  while [ $SECONDS -lt $deadline ]; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 3
  done
  return 1
}

daemon_up() { "$DOCKER" version --format '{{.Server.Version}}' 2>/dev/null | grep -q .; }

find_base() {
  for b in http://127.0.0.1:17493 http://127.0.0.1:17600; do
    if curl -s --max-time 3 "$b/v1/models" | grep -q '"object"'; then BASE="$b"; return 0; fi
  done
  return 1
}

say "=== 1. Docker daemon ==="
if daemon_up; then
  say "already running"
else
  say "starting Docker Desktop (this can take a minute)"
  open -a Docker >/dev/null 2>&1 || fail "could not launch Docker. Open it from Applications yourself, then re-run."
  wait_for 300 daemon_up || fail "Docker did not come up in 5 minutes."
  say "docker is up"
fi

say "=== 2. local engine stack ==="
if find_base; then
  say "voicebox already answering at $BASE"
else
  [ -d "$STACK" ] || fail "missing $STACK"
  say "building and starting (first run downloads a lot; go make tea)"
  ( cd "$STACK" && "$DOCKER" compose up -d --build ) || fail "docker compose failed. Run it by hand in $STACK to see the error."
  wait_for 900 find_base || fail "voicebox never became reachable. Check: cd $STACK && $DOCKER compose logs -f"
  say "voicebox answering at $BASE"
fi

[ "${1:-}" = "--status" ] && { say "ready: $BASE"; exit 0; }

say "=== 3. voice profile ==="
python3 - "$BASE" "$PROFILE_NAME" "$SAMPLES_DIR" <<'PY'
import json, mimetypes, sys, urllib.request, uuid
from pathlib import Path

base, name, samples_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])


def call(path, data=None, ctype="application/json", method=None):
    req = urllib.request.Request(base + path, data=data,
                                headers={"Content-Type": ctype} if data else {},
                                method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def multipart(fields, files):
    b = "----vf" + uuid.uuid4().hex
    body = bytearray()
    for k, v in fields.items():
        body += f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    for k, path in files:
        ctype = mimetypes.guess_type(path.name)[0] or "audio/wav"
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{path.name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        body += path.read_bytes() + b"\r\n"
    body += f"--{b}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={b}"


profiles = call("/profiles")
match = next((p for p in profiles if p.get("name") == name), None)
if match:
    print(f"profile already exists: {match['id'][:8]}... ({len(match.get('samples') or [])} samples)")
    pid = match["id"]
else:
    body = json.dumps({"name": name, "description": "Cloned in VoiceForge from RODE NT-USB takes",
                       "language": "en", "voice_type": "cloned"}).encode()
    pid = call("/profiles", body)["id"]
    print(f"created profile {name} ({pid[:8]}...)")

samples = sorted(samples_dir.glob("*.wav"))
if not samples:
    print("no samples found; add a recording in VoiceForge first")
    sys.exit(1)

for path in samples:
    raw, ctype = multipart({"language": "en"}, [("file", path)])
    try:
        text = call("/transcribe", raw, ctype).get("text", "").strip()
    except Exception as e:
        print(f"  transcribe failed for {path.name}: {e}")
        continue
    if not text:
        print(f"  no transcript for {path.name}, skipping")
        continue
    raw, ctype = multipart({"reference_text": text[:1000]}, [("file", path)])
    try:
        call(f"/profiles/{pid}/samples", raw, ctype)
        print(f"  sample added: {path.name} ({len(text)} chars of reference text)")
    except Exception as e:
        print(f"  sample upload failed for {path.name}: {e}")

print(f"PROFILE_ID={pid}")
PY

say "=== 4. rendering the book, free ==="
python3 tools/audiobook.py --all --engine voicebox --voice "$PROFILE_NAME" --outdir "$OUTDIR" \
  || fail "render failed. Check the engine with: curl $BASE/v1/models"

say ""
say "done. files are in $OUTDIR"
