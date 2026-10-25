#!/usr/bin/env bash
# Start the HC09 editor on Linux / macOS: checks Python 3.9+ (with Tk) and Node.js 18+, installs the bridge's dependencies the
# first time, then starts the editor.   ./start-hc09-editor.sh --check   only reports what is installed (exit code 0 = ready)
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
# The bridge's dependencies need no compiler. A folder left by a failed or older install that does not load is thrown away and installed again.
if [ -f hc09-bridge/node_modules/madden-file-tools/package.json ] && node -e "require('./hc09-bridge/node_modules/madden-file-tools')" >/dev/null 2>&1; then
  echo "[ok] The bridge's dependencies are installed"
elif [ "$1" = "--check" ]; then
  echo "[info] The bridge's dependencies will be installed on the first start (npm install)"
else
  echo "Installing the bridge's dependencies (first start only, needs internet)..."
  rm -rf hc09-bridge/node_modules
  (cd hc09-bridge && npm install --no-audit --no-fund) || { echo "[FAILED] npm install did not finish."; exit 1; }
fi
if [ "$1" = "--check" ]; then echo "Ready: the editor would start with: $py guiHC09.py"; exit 0; fi
exec "$py" guiHC09.py
