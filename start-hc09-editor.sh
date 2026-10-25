#!/usr/bin/env bash
# Start the HC09 editor on Linux / macOS: checks Python 3.9+ (with Tk) and Node.js 18+, checks that the bridge starts (its libraries ship with the editor,
# nothing is installed), then starts the editor.   ./start-hc09-editor.sh --check   only reports what is installed (exit code 0 = ready)
cd "$(dirname "$0")" || exit 1
problem=0
py=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then py="$cand"; break; fi
done
if [ -n "$py" ]; then echo "[ok] Python found: $py"; else echo "[MISSING] Python 3.9 or newer with Tk (python3-tk on Debian/Ubuntu, brew install python-tk on macOS)."; problem=1; fi
if command -v node >/dev/null 2>&1 && node -e 'process.exit(Number(process.versions.node.split(".")[0])>=18?0:1)' >/dev/null 2>&1; then
  echo "[ok] Node.js found"
else
  echo "[MISSING] Node.js 18 or newer (https://nodejs.org/)."; problem=1
fi
[ "$problem" -ne 0 ] && exit 1
# The bridge's libraries ship with the editor (hc09-bridge/vendor): nothing to install, no npm, no internet, no compiler. Check that the bridge starts.
if node hc09-bridge/bridge.js selftest >/dev/null 2>&1; then
  echo "[ok] The bridge starts"
else
  echo "[FAILED] The bridge does not start. To see why, run:  node hc09-bridge/bridge.js selftest"
  echo "         (The folder hc09-bridge/vendor has to be there: download the editor again if it is missing.)"
  exit 1
fi
if [ "$1" = "--check" ]; then echo "Ready: the editor would start with: $py guiHC09.py"; exit 0; fi
exec "$py" guiHC09.py
