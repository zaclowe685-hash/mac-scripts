#!/bin/bash
PY="/Applications/LTX Desktop.app/Contents/Resources/python/bin/python3"
[ -x "$PY" ] || PY=$(command -v python3)
exec "$PY" "$HOME/scripts/ltx-monitor.py"
