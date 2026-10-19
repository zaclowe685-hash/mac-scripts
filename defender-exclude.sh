#!/bin/zsh
# Keep Microsoft Defender off Zac's projects (golden rule 15), with ONE fingerprint.
# Adds every project in ~ (any folder with a .git), ~/UnrealProjects, and the overnight-lane log folders
# (~/.overnight, ~/.claude/projects) to Defender's skip list, skipping folders that are already on it.
#
#   zsh ~/scripts/defender-exclude.sh                  # exclude every project not excluded yet
#   zsh ~/scripts/defender-exclude.sh ~/new-thing      # plus this folder (e.g. before its git init)
#   zsh ~/scripts/defender-exclude.sh --full-priority  # plus: put low-priority (nice 15) processes back to normal
#   zsh ~/scripts/defender-exclude.sh --dry-run        # just list what it would add
setopt null_glob
full=0; dry=0; extra=()
for a in "$@"; do
  case $a in
    --full-priority) full=1 ;;
    --dry-run) dry=1 ;;
    *) extra+=("${a:A}") ;;
  esac
done

excluded=$(mdatp exclusion list 2>/dev/null | sed -n 's/.*Path: "\(.*\)"/\1/p')
want=()
for d in $HOME/*(/); do [[ -e $d/.git ]] && want+=("$d"); done
for d in $HOME/UnrealProjects $HOME/.overnight $HOME/.claude/projects "${extra[@]}"; do [[ -d $d ]] && want+=("$d"); done
todo=()
for d in "${(u)want[@]}"; do print -r -- "$excluded" | grep -qxF -- "$d" || todo+=("$d"); done

if (( ${#todo} == 0 )); then
  print "Every project folder is already excluded from Defender."
elif (( dry )); then
  print "Would add ${#todo} folder(s):"; for d in "${todo[@]}"; do print "  ${d/#$HOME/~}"; done
else
  print "Adding ${#todo} folder(s) to Defender's skip list (fingerprint once):"
  for d in "${todo[@]}"; do
    if sudo mdatp exclusion folder add --path "$d" >/dev/null; then print "  done    ${d/#$HOME/~}"; else print "  FAILED  ${d/#$HOME/~}"; fi
  done
fi

if (( full )); then
  pids=($(ps -U $UID -o pid=,nice= | awk '$2==15{print $1}'))
  if (( ${#pids} == 0 )); then print "Nothing is on low priority."
  elif (( dry )); then print "Would put ${#pids} low-priority processes back to full priority."
  else sudo renice 0 -p "${pids[@]}" >/dev/null && print "Put ${#pids} low-priority processes back to full priority."
  fi
fi
