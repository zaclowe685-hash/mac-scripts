#!/bin/zsh
# tidy.sh — sort ~/Downloads and ~/Desktop into type-based folders.
# SAFE: never deletes anything, skips files touched in the last hour,
# skips .app bundles (your Block launchers), handles name clashes, logs every move.
# Usage: tidy.sh            (do the moves)
#        tidy.sh --dry-run  (just print what WOULD move)

set -u
setopt null_glob

HOME_DIR="$HOME"
LOG="$HOME_DIR/scripts/tidy.log"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

# --- destinations ---
SHOTS="$HOME_DIR/Pictures/Screenshots"
CAMERA="$HOME_DIR/Pictures/Camera Roll"
PICS="$HOME_DIR/Pictures/From Downloads"
VIDS="$HOME_DIR/Movies"
MUSIC="$HOME_DIR/Music"
PDFS="$HOME_DIR/Documents/PDFs"
SCHOOL="$HOME_DIR/Documents/School"
INSTALLERS="$HOME_DIR/Documents/Installers"
ARCHIVES="$HOME_DIR/Documents/Archives"
NOTES="$HOME_DIR/Documents/Notes"
DESKSTUFF="$HOME_DIR/Documents/Desktop Stuff"

mkdir -p "$SHOTS" "$CAMERA" "$PICS" "$VIDS" "$MUSIC" "$PDFS" "$SCHOOL" "$INSTALLERS" "$ARCHIVES" "$NOTES" "$DESKSTUFF"

ts()      { date "+%Y-%m-%d %H:%M:%S"; }
logline() { echo "$(ts) $1" >> "$LOG"; }
MOVED=0

# move "$1" into dir "$2", auto-renaming on collision
move_to() {
  local src="$1" destdir="$2"
  local base="${src##*/}"
  local dest="$destdir/$base"
  if [[ -e "$dest" ]]; then
    local name="${base%.*}" ext="${base##*.}"
    [[ "$name" == "$base" ]] && ext=""
    local i=1
    while [[ -e "$dest" ]]; do
      if [[ -n "$ext" ]]; then dest="$destdir/${name} ${i}.${ext}"; else dest="$destdir/${base} ${i}"; fi
      ((i++))
    done
  fi
  if [[ $DRY -eq 1 ]]; then
    echo "WOULD MOVE: ${src/#$HOME_DIR/~}  ->  ${dest/#$HOME_DIR/~}"
  else
    mv "$src" "$dest" && { logline "moved: ${src/#$HOME_DIR/~} -> ${dest/#$HOME_DIR/~}"; ((MOVED++)); }
  fi
}

# echo destination dir for a filename by extension, empty = leave alone
dest_for() {
  local base="$1"
  local ext="${base##*.}"; ext="${ext:l}"
  local lower="${base:l}"

  # name-based rules win over extension, so screenshots and camera photos
  # always land in one predictable place no matter where they came from
  case "$lower" in
    screenshot*|screen\ shot*|cleanshot*) echo "$SHOTS"; return ;;
    img_[0-9]*|dsc[_0-9]*|pxl_[0-9]*)    echo "$CAMERA"; return ;;
  esac

  case "$ext" in
    heic|heif|jpg|jpeg|png|gif|webp|tiff|bmp)  echo "$PICS" ;;
    mp4|mov|m4v|avi|mkv|webm)                  echo "$VIDS" ;;
    mp3|wma|m4a|wav|flac|aac|aiff)             echo "$MUSIC" ;;
    pdf)                                       echo "$PDFS" ;;
    pptx|ppt|docx|doc|xlsx|xls|key|pages|numbers|odt|csv) echo "$SCHOOL" ;;
    dmg|pkg|tar|iso)                           echo "$INSTALLERS" ;;
    zip|rar|7z|gz|tgz)                         echo "$ARCHIVES" ;;
    md|txt|rtf)                                echo "$NOTES" ;;
    *)                                         echo "" ;;
  esac
}

process_dir() {
  local dir="$1" is_desktop="$2"
  # A protected folder that we cannot read looks EMPTY rather than erroring.
  # That is how this script quietly moved 0 files for weeks under launchd, so
  # shout about it instead of reporting success.
  local entries=("$dir"/*)
  if (( ${#entries} == 0 )); then
    logline "WARNING: ${dir/#$HOME_DIR/~} looks empty — if it is not, this run lacks Full Disk Access"
    echo "WARNING: ${dir/#$HOME_DIR/~} looks empty (possible Full Disk Access problem)"
  fi
  for f in "$dir"/*; do
    local base="${f##*/}"
    if [[ -d "$f" ]]; then
      # on the Desktop, sweep stray folders aside but keep .app launchers
      if [[ "$is_desktop" == "1" && "$base" != *.app ]]; then
        move_to "$f" "$DESKSTUFF"
      fi
      continue
    fi
    # leave anything modified in the last hour (mid-download / mid-install)
    [[ -n "$(find "$f" -maxdepth 0 -mmin -60 2>/dev/null)" ]] && continue
    local d="$(dest_for "$base")"
    [[ -z "$d" ]] && continue
    move_to "$f" "$d"
  done
}

[[ $DRY -eq 0 ]] && logline "=== tidy run start ==="
process_dir "$HOME_DIR/Downloads" 0
process_dir "$HOME_DIR/Desktop"   1
[[ $DRY -eq 0 ]] && logline "=== tidy run end (moved $MOVED) ==="
[[ $DRY -eq 1 ]] && echo "(dry-run — nothing was moved)"
echo "Moved $MOVED file(s)."
exit 0
