#!/bin/zsh
# disk-guard: stops the Mac running out of disk space (2026-10-08, after a full-disk crash during SAN ANDREAS work).
# Runs every 2 minutes from launchd (com.zac.disk-guard).
#   under WARN_GB free  -> notification (at most every 30 min)
#   under PAUSE_GB free -> pauses (SIGSTOP, not kill) Blender, Godot and Unreal so nothing can fill the last bit
#   back over RESUME_GB -> resumes whatever it paused
# Manual:  disk-guard.sh status   |   disk-guard.sh resume   (un-pause everything now)
# Log: ~/Library/Logs/disk-guard.log

WARN_GB=40
PAUSE_GB=15
RESUME_GB=25
HEAVY='Blender|Godot|UnrealEditor|ShaderCompileWorker'
STATE="$HOME/Library/Application Support/disk-guard"
LOG="$HOME/Library/Logs/disk-guard.log"
mkdir -p "$STATE"

free_gb=$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')
log() { echo "$(date '+%F %T') free=${free_gb}GB $*" >> "$LOG"; }
notify() { osascript -e "display notification \"$2\" with title \"$1\" sound name \"Basso\"" 2>/dev/null; }

resume_all() {
  [[ -s "$STATE/paused" ]] || return
  while read pid; do kill -CONT "$pid" 2>/dev/null; done < "$STATE/paused"
  log "resumed: $(tr '\n' ' ' < "$STATE/paused")"
  notify "Disk guard" "Space is back (${free_gb} GB). Paused jobs resumed."
  : > "$STATE/paused"
}

case "$1" in
  status) echo "free: ${free_gb} GB (warn <${WARN_GB}, pause <${PAUSE_GB})"; echo "paused pids: $(cat "$STATE/paused" 2>/dev/null)"; tail -5 "$LOG" 2>/dev/null; exit ;;
  resume) resume_all; exit ;;
esac

if (( free_gb < PAUSE_GB )); then
  pids=$(pgrep "^($HEAVY)")   # process names only, so a shell command that mentions "Godot" is never paused
  if [[ -n "$pids" ]]; then
    for pid in ${(f)pids}; do
      grep -qx "$pid" "$STATE/paused" 2>/dev/null && continue
      kill -STOP "$pid" 2>/dev/null && echo "$pid" >> "$STATE/paused"
    done
    log "PAUSED heavy jobs: $(tr '\n' ' ' < "$STATE/paused")"
    notify "Disk almost full: ${free_gb} GB left" "Blender/Godot/Unreal paused. Free some space; they resume by themselves at ${RESUME_GB} GB."
  fi
elif (( free_gb >= RESUME_GB )); then
  resume_all
fi

if (( free_gb < WARN_GB )); then
  last=$(cat "$STATE/last-warn" 2>/dev/null || echo 0)
  if (( $(date +%s) - last > 1800 )); then
    date +%s > "$STATE/last-warn"
    log "warning"
    (( free_gb >= PAUSE_GB )) && notify "Disk getting full" "${free_gb} GB free. Heavy jobs pause at ${PAUSE_GB} GB."
  fi
fi
