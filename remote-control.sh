#!/bin/zsh
# Always-on Claude Code Remote Control server ("Zac's Mac").
# Lets the Claude phone app start NEW sessions on this Mac, in ~ (so every project is reachable).
# Run by launchd (com.zac.remote-control) at login; restarted if it dies.
#   caffeinate -s  = keep the Mac awake while on the charger (battery behaves normally)
#   script -q      = gives claude a fake terminal, since launchd has none
#   tail -f        = an input that never ends (launchd's empty stdin made it quit right away)
# Stop for good:  launchctl bootout gui/$(id -u)/com.zac.remote-control
# Logs:           ~/Library/Logs/remote-control.log

export PATH="$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$HOME" || exit 1

/usr/bin/tail -f /dev/null | /usr/bin/caffeinate -s /usr/bin/script -q /dev/null \
  claude remote-control --name "Zac's Mac" --permission-mode bypassPermissions
