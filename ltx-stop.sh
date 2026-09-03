#!/bin/bash
# Cancel the running LTX generation cleanly (keeps the app open).
PID=$(lsof -tiTCP -sTCP:LISTEN -P 2>/dev/null | xargs -I{} sh -c 'ps -p {} -o comm= | grep -qi python && echo {}' 2>/dev/null | head -1)
if [ -z "$PID" ]; then echo "  LTX backend not running."; exit 1; fi
PORT=$(lsof -a -p "$PID" -iTCP -sTCP:LISTEN -P 2>/dev/null | tail -1 | sed -n 's/.*:\([0-9]*\) .*/\1/p')
TOK=$(ps eww -p "$PID" 2>/dev/null | tr ' ' '\n' | grep '^LTX_AUTH_TOKEN=' | cut -d= -f2-)
CODE=$(curl -s -o /tmp/ltxstop.$$ -w "%{http_code}" --max-time 8 -X POST \
       -H "Authorization: Bearer $TOK" "http://localhost:$PORT/api/generate/cancel")
echo
case "$CODE" in
  200|204) echo "  Generation cancelled. The app stays open and stays local." ;;
  404)     echo "  Nothing running to cancel." ;;
  *)       echo "  Cancel returned HTTP $CODE"; cat /tmp/ltxstop.$$ 2>/dev/null; echo
           echo "  Fallback: quit LTX Desktop (Cmd-Q) - safe, loses only this clip." ;;
esac
rm -f /tmp/ltxstop.$$
echo
