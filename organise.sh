#!/bin/bash
# File Organiser for Zac's Mac
# Handles clear-cut cases automatically, then calls Claude for anything fuzzy.

OD="$HOME/Library/CloudStorage/OneDrive-ThePittwaterHouseSchool/Documents/Year 11"
OD_ROOT="$HOME/Library/CloudStorage/OneDrive-ThePittwaterHouseSchool"
DL="$HOME/Downloads"
UNKNOWN=()

# Detect current school term by month
month=$(date +%-m)
if   [[ $month -ge 2 && $month -le 4 ]]; then TERM="Term 1"
elif [[ $month -ge 5 && $month -le 7 ]]; then TERM="Term 2"
elif [[ $month -ge 8 && $month -le 9 ]]; then TERM="Term 3"
else                                           TERM="Term 4"
fi

echo "=============================="
echo " File Organiser  —  $TERM"
echo "=============================="
echo ""

# ── 1. Delete DMG installers for installed apps ──────────────────────────────
echo "[ DMG Installers ]"
found_dmg=false
for dmg in "$DL"/*.dmg; do
  [[ -f "$dmg" ]] || continue
  found_dmg=true
  appname=$(basename "$dmg" | sed 's/-arm64//g; s/-darwin-universal//g; s/Setup//g; s/\.[0-9].*//g; s/\.dmg//g')
  if ls /Applications/ 2>/dev/null | grep -qi "$appname"; then
    rm "$dmg"
    echo "  Deleted: $(basename "$dmg")"
  else
    echo "  Skipped: $(basename "$dmg") — app not found in /Applications"
  fi
done
$found_dmg || echo "  None found."
echo ""

# ── Helper: move a file and report it ───────────────────────────────────────
move() {
  local file="$1" dest="$2"
  [[ -f "$file" ]] || return
  mv "$file" "$dest/"
  echo "  $(basename "$file")  →  $dest"
}

# ── 2. Sort Downloads by subject ─────────────────────────────────────────────
echo "[ Downloads → OneDrive $TERM ]"
for f in "$DL"/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  namel="${name,,}"  # lowercase for matching

  case "$namel" in
    yr11*|*suvat*|*inclined*plane*|*ticker*timer*|*newton*|\
    *"year 11 phys"*|*physics*|*kinematics*|*dynamics*|\
    *motion*|*"sound wave"*|*vectors*|*forces*)
      move "$f" "$OD/Physics/$TERM" ;;

    *nelsonnet*|*permut*|*combinat*|*"extension 1"*|\
    *factorial*|*pascal*|*"counting tech"*)
      move "$f" "$OD/Maths Ex/$TERM" ;;

    *"maths ad"*|*"math ad"*|*"advanced task"*|*"advanced atb"*)
      move "$f" "$OD/Maths Ad/$TERM" ;;

    *"software trial"*|*"programming theory"*|*sdlc*|\
    *"control struct"*|*"software w"*|*"software 1."*|\
    *"software quiz"*|*"development approach"*)
      move "$f" "$OD/Software/$TERM" ;;

    *.apkg|*french*|*vocab*)
      move "$f" "$OD/French/$TERM" ;;

    *discursive*|*"english"*|*"bridegroom"*|*reflection*|\
    *"creative writ"*|*homework*|*"revision support"*)
      move "$f" "$OD/English/$TERM" ;;

    *chem*)
      move "$f" "$OD/Chem/$TERM" ;;

    *)
      UNKNOWN+=("$f") ;;
  esac
done
echo ""

# ── 3. Tidy OneDrive root ────────────────────────────────────────────────────
echo "[ OneDrive Root ]"
for f in "$OD_ROOT"/*.docx "$OD_ROOT"/*.pdf "$OD_ROOT"/*.pptx; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  namel="${name,,}"

  case "$namel" in
    *english*|*discursive*|*essay*|*reflection*|*bridegroom*|*creative*)
      move "$f" "$OD/English/$TERM" ;;
    *french*|*vocab*|*speaking*)
      move "$f" "$OD/French/$TERM" ;;
    *software*|*development*|*programming*|*algorithm*)
      move "$f" "$OD/Software/$TERM" ;;
    *physics*|*force*|*motion*|*wave*)
      move "$f" "$OD/Physics/$TERM" ;;
    *maths*|*math*)
      move "$f" "$OD/Maths Ex/$TERM" ;;
    *chem*)
      move "$f" "$OD/Chem/$TERM" ;;
    *)
      UNKNOWN+=("$f") ;;
  esac
done
echo ""

# ── 4. Pass unknowns to Claude ───────────────────────────────────────────────
if [[ ${#UNKNOWN[@]} -gt 0 ]]; then
  echo "[ Asking Claude about ${#UNKNOWN[@]} unrecognised file(s) ]"
  FILE_LIST=$(printf '%s\n' "${UNKNOWN[@]}" | xargs -I{} basename "{}")
  PROMPT="You are organising files on Zac's Mac (Year 11, The Pittwater House School).

Unrecognised files found in Downloads or OneDrive root that couldn't be auto-classified:
$FILE_LIST

OneDrive Year 11 subject folders available (all have a '$TERM' subfolder):
  Physics, Maths Ex, Maths Ad, Software, English, French, Chem

Base OneDrive path: $HOME/Library/CloudStorage/OneDrive-ThePittwaterHouseSchool/Documents/Year 11

For each file, move it to the right subject/$TERM folder using Bash mv commands.
If you genuinely can't tell, say so and leave it — don't guess blindly.
Do not delete anything without asking."

  claude -p "$PROMPT"
else
  echo "[ No unknown files — all sorted! ]"
fi

echo ""
echo "=============================="
echo " Done."
echo "=============================="
