#!/bin/bash
# Get LTX Desktop into LOCAL mode on a 24GB Mac, then watch the generation.
# Asks for your password FIRST, then closes apps, flushes the disk cache,
# launches the app, and finally hands this window over to the live monitor.
# One command does the whole thing - ltx-monitor.sh still works on its own.

PY="/Applications/LTX Desktop.app/Contents/Resources/python/bin/python3"
LOGDIR="$HOME/Library/Application Support/LTXDesktop/logs"
avail () { "$PY" -c "import psutil;print(round(psutil.virtual_memory().available/1024**3,1))" 2>/dev/null; }

clear
echo "======================================================"
echo " LTX Desktop - local mode + live monitor"
echo "======================================================"
echo " Available RAM now: $(avail) GB   (need 15 at launch)"
echo
echo "------------------------------------------------------"
echo " STEP 1 of 3: your Mac password"
echo
echo " Needed for 'purge' - Apple's own command that empties"
echo " the disk cache. It deletes NOTHING. Type your password"
echo " and press enter (the cursor won't move, that's normal)."
echo "------------------------------------------------------"
if ! sudo -v; then
    echo
    echo " Password not accepted. Nothing has been changed."
    echo " Run the script again."
    exit 1
fi
echo " Password OK."
echo

echo " STEP 2 of 3: closing apps..."
osascript -e 'quit app "LTX Desktop"' >/dev/null 2>&1
for a in "Creative Cloud" "OneDrive" "Google Chrome" "Spotify" "Slack" \
         "Microsoft Outlook" "Microsoft Word" "Microsoft Excel" "Wispr Flow" \
         "VoiceFlow" "Code" "Music" "Safari" "Notion" "Discord" "Photos"; do
    osascript -e "quit app \"$a\"" >/dev/null 2>&1
done
for p in "Creative Cloud" "Adobe Desktop Service" "AdobeIPCBroker" "Core Sync" \
         "CCXProcess" "CCLibrary" "OneDrive" "llama-server"; do
    pkill -f "$p" 2>/dev/null
done
echo "   closing Claude (this chat) - the answer prints HERE"
osascript -e 'quit app "Claude"' >/dev/null 2>&1
sleep 4
pkill -f "Virtualization.VirtualMachine" 2>/dev/null
pkill -x "claude" 2>/dev/null
sleep 3
echo "   available now: $(avail) GB"
echo

echo " STEP 3 of 3: flushing disk cache..."
sudo purge
sleep 5
A=$(avail)
echo "   available after purge: $A GB"
echo

if awk -v a="${A:-0}" 'BEGIN{exit !(a<15)}'; then
    echo "   Under 15 - launching anyway to see the real number."
else
    echo "   Above 15. Launching."
fi
echo
open "/Applications/LTX Desktop.app"
echo " Waiting for the verdict (up to 3 min)..."
STAMP=$(date +%s)
MODE=""; RAM=""

for i in $(seq 1 90); do
    sleep 2
    NEWEST=$(ls -t "$LOGDIR"/*.log 2>/dev/null | head -1)
    [ -z "$NEWEST" ] && continue
    [ "$(stat -f %m "$NEWEST" 2>/dev/null)" -lt "$STAMP" ] && continue
    LINE=$(grep -h "Runtime policy local_generations_mode" "$NEWEST" 2>/dev/null | tail -1)
    [ -z "$LINE" ] && continue
    MODE=$(echo "$LINE" | sed -n 's/.*local_generations_mode=\([a-z_]*\).*/\1/p')
    RAM=$(echo  "$LINE" | sed -n 's/.*available_ram_gb=\([0-9]*\).*/\1/p')
    [ -n "$MODE" ] && break
done

echo
echo "======================================================"
if [ -z "$MODE" ]; then
    echo " No verdict yet - check the model dropdown in the app."
    echo " (A model with no '(API)' after it means local is on.)"
    echo "======================================================"
    exit 0
fi

if [ "$MODE" = "unsupported" ]; then
    echo " STILL API-ONLY - measured ${RAM} GB, needed 15."
    echo
    echo " That's the honest ceiling for this Mac."
    echo " Use ltx.io/studio (800 free credits) instead."
    echo "======================================================"
    echo " Reopen Claude from your Dock whenever you want."
    exit 0
fi

echo " LOCAL MODE ON   ($MODE)  - measured ${RAM} GB"
echo
echo " 1. In the app, pick a model with NO '(API)' after it"
echo " 2. Paste your prompt, set the length and resolution"
echo " 3. Hit Generate"
echo "======================================================"
echo
echo " Then come back here and press ENTER - the live monitor"
echo " takes over this window and shows RAM, step count and"
echo " the heartbeat. (The step counter FREEZES during decode;"
echo " that is normal - watch the heartbeat instead.)"
echo
echo " Ctrl-C in the monitor just stops watching. It never"
echo " touches the generation. To cancel a clip: ~/scripts/ltx-stop.sh"
echo
printf " Press ENTER to start the monitor... "
read -r _

PYM="$PY"; [ -x "$PYM" ] || PYM=$(command -v python3)
exec "$PYM" "$HOME/scripts/ltx-monitor.py"
