#!/bin/zsh
# backup-all.sh — push every project in ~/ to a PRIVATE GitHub repo.
#
#   ~/scripts/backup-all.sh --dry-run    # show what would happen, change nothing
#   ~/scripts/backup-all.sh              # do it
#
# Safe by design: never deletes, never force-pushes, never rewrites history.
# Run it any time — projects already backed up just get their new commits pushed.

set -u
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

GH_USER="zaclowe685-hash"
cd "$HOME" || exit 1

# Every real project folder. Add new ones here (or let /new-project do it).
PROJECTS=(
  abyssal basketball-game camping-map chess_game court-1v1 crimson-moon
  deep-field dinner-planner earth-impact escape-rooms forest-walk gap-map
  glm-prompts hoopfeel house-walkthrough lumen meal-planner meridian
  morning-briefing project-hub redline scripts specimen streetball-mine
  streetball-pro streetball-raw subtracker taskify tower_defence vinterheim
  voiceflow voidstrike xenathel "Space Journey"
)

# Junk that must never be committed. Build artefacts and secrets.
IGNORE_ALWAYS=(
  ".DS_Store" "*.log" "__pycache__/" "*.pyc" ".env" ".env.local"
  ".dev.vars" ".wrangler/" ".netlify/" "venv/" ".venv/" "node_modules/"
)

log()  { printf '%s\n' "$*" }
step() { printf '\n\033[1m%s\033[0m\n' "$1" }

slug_for() {  # folder name -> github repo name
  print -r -- "${${1:l}// /-}"
}

ensure_ignores() {
  local dir="$1" gi="$1/.gitignore" line
  local -a want=("${IGNORE_ALWAYS[@]}")
  # only ignore dist/ where a build tool actually produces it
  [[ -f "$dir/package.json" ]] && want+=("dist/")

  local -a missing=()
  for line in "${want[@]}"; do
    if [[ ! -f "$gi" ]] || ! grep -qxF -- "$line" "$gi" 2>/dev/null; then
      missing+=("$line")
    fi
  done
  (( ${#missing} == 0 )) && return 0

  log "    + .gitignore: ${missing[*]}"
  (( DRY )) && return 0
  { [[ -s "$gi" ]] && print -r -- ""; print -r -- "# added by backup-all.sh"
    for line in "${missing[@]}"; do print -r -- "$line"; done } >> "$gi"
}

ok=0; failed=(); created=()

for p in "${PROJECTS[@]}"; do
  [[ -d "$p" ]] || { log "\n$p — MISSING, skipped"; continue }
  step "$p"

  ensure_ignores "$p"

  if [[ ! -d "$p/.git" ]]; then
    log "    + git init (no history at all right now)"
    (( DRY )) || git -C "$p" init -q -b main
  fi

  # Note: files already tracked stay tracked even if newly ignored. That is
  # deliberate — escape-rooms tracks a node_modules/three symlink it needs.

  if [[ -d "$p/.git" ]]; then
    local_dirty=$(git -C "$p" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  else
    local_dirty=$(( $(find "$p" -type f -not -path "*/node_modules/*" \
      -not -path "*/venv/*" -not -path "*/.venv/*" 2>/dev/null | wc -l) ))
  fi

  if [[ "$local_dirty" != "0" ]]; then
    log "    + commit ($local_dirty files)"
    if (( ! DRY )); then
      git -C "$p" add -A
      # Use the global git identity — it is set to a GitHub noreply address,
      # which keeps the real email out of commit metadata. Never hardcode one.
      git -C "$p" commit -q -m "Backup: snapshot" || true
    fi
  else
    log "    = nothing new to commit"
  fi

  if git -C "$p" remote get-url origin >/dev/null 2>&1; then
    log "    > push to $(git -C "$p" remote get-url origin)"
    (( DRY )) || { git -C "$p" push -u origin HEAD -q && ok=$((ok+1)) || failed+=("$p"); }
  else
    slug=$(slug_for "$p")
    log "    > CREATE private repo $GH_USER/$slug and push"
    if (( ! DRY )); then
      if gh repo create "$GH_USER/$slug" --private --source="$p" --remote=origin --push; then
        ok=$((ok+1)); created+=("$slug")
      else
        failed+=("$p")
      fi
    fi
  fi
done

step "Done"
(( DRY )) && { log "DRY RUN — nothing was changed."; exit 0 }
log "Pushed OK:      $ok"
(( ${#created} )) && log "New repos:      ${created[*]}"
(( ${#failed}  )) && log "\033[31mFAILED:         ${failed[*]}\033[0m"
log "\nSee them at: https://github.com/$GH_USER?tab=repositories"
