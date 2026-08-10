#!/bin/zsh
# loadblock.sh <minutes> — preload a SelfControl preset (sites + duration) and open the app.
# Must quit the app first: SelfControl reads its settings on launch and overwrites them on quit.
MINS="${1:-120}"

osascript -e 'quit app "SelfControl"' 2>/dev/null
sleep 1

# duration (minutes) + the blocklist (SelfControl 4 reads the "Blocklist" key, not HostBlacklist)
defaults write org.eyebeam.SelfControl BlockDuration -int "$MINS"
defaults write org.eyebeam.SelfControl Blocklist -array \
  youtube.com www.youtube.com m.youtube.com youtu.be youtube-nocookie.com ytimg.com \
  chess.com www.chess.com chesspuzzle.net www.chesspuzzle.net

killall cfprefsd 2>/dev/null   # flush the prefs cache so the app reads the fresh values
sleep 1
open -a SelfControl
