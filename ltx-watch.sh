#!/bin/bash
# Watch memory while LTX generates. Run this in Terminal, leave it visible.
# If "available" hits ~0 and stays there, it has stalled - quit LTX and retry
# with a shorter/smaller clip.
PY="/Applications/LTX Desktop.app/Contents/Resources/python/bin/python3"
LOG="$HOME/Library/Application Support/LTXDesktop/logs"
printf "\n  Watching. Ctrl-C to stop.\n\n"
while true; do
  A=$("$PY" -c "import psutil;print(round(psutil.virtual_memory().available/1024**3,1))" 2>/dev/null)
  SW=$(sysctl -n vm.swapusage 2>/dev/null | grep -oE "used = [0-9.]+M" | grep -oE "[0-9.]+")
  L=$(uptime | sed -n 's/.*load averages*: *\([0-9.]*\).*/\1/p')
  case "$(awk -v a="${A:-0}" 'BEGIN{print (a<1)?"STALL":(a<3)?"tight":"ok"}')" in
    STALL) S="<-- STALLING" ;; tight) S="<-- getting tight" ;; *) S="" ;;
  esac
  printf "\r  available %-5s GB   swap %-7s MB   load %-6s %-18s" "$A" "$SW" "$L" "$S"
  sleep 3
done
