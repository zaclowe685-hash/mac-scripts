#!/bin/bash
# Am I running LTX locally or through the API?
L=$(ls -t "$HOME/Library/Application Support/LTXDesktop/logs"/*.log 2>/dev/null | head -1)
M=$(grep -h "local_generations_mode" "$L" 2>/dev/null | tail -1 | sed -n 's/.*mode=\([a-z_]*\).*/\1/p')
R=$(grep -h "local_generations_mode" "$L" 2>/dev/null | tail -1 | sed -n 's/.*available_ram_gb=\([0-9]*\).*/\1/p')
echo
case "$M" in
  unsupported) echo "  API MODE - generations cost money (it saw ${R} GB, needed 15)";;
  streaming_models_loading) echo "  LOCAL, streaming from SSD (saw ${R} GB). Free, slower.";;
  full_models_loading)      echo "  LOCAL, fully resident (saw ${R} GB). Free, fastest.";;
  *) echo "  Can't tell - is LTX Desktop running?";;
esac
echo
