tell application "Terminal"
    activate
    do script "~/scripts/organise.sh; echo ''; echo 'Press any key to close...'; read -n 1"
end tell
