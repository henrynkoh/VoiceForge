#!/bin/bash
# VoiceForge launcher: stops any previous copy, finds a working Python 3.9+, starts the app.
cd "$(dirname "$0")" || exit 1

pkill -f "voiceforge.app" >/dev/null 2>&1
sleep 1

for PY in "$VOICEFORGE_PYTHON" /opt/homebrew/bin/python3 /usr/local/bin/python3 \
          /Users/henryoh/.aside/runtime/bin/python3 "$(command -v python3)" /usr/bin/python3; do
  [ -n "$PY" ] || continue
  [ -x "$PY" ] || continue
  if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    echo "Starting VoiceForge with $PY"
    echo
    "$PY" -m voiceforge.app
    CODE=$?
    if [ "$CODE" != "0" ]; then
      echo
      echo "VoiceForge stopped with error code $CODE (scroll up for the message)."
      read -n 1 -s -r -p "Press any key to close this window."
    fi
    exit "$CODE"
  fi
done

echo "No working Python 3.9+ was found on this Mac."
echo "Install it with:  xcode-select --install"
echo
read -n 1 -s -r -p "Press any key to close this window."
