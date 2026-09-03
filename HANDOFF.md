# Handoff — LTX-2.5 local video (LTX Desktop) — 2026-08-18

**Where things stand:** LTX-2.5 generates video LOCALLY on the 24GB M5 — proven once
(`streaming_models_loading`, mps, 16GB). But NO clip has finished yet, and the app has
since restarted back into API-only mode. Re-run `ltx-local.sh` to get local back.

**Just done:** cleared 50GB (deleted a dead March ComfyUI/LTX-2.3 attempt), installed
LTX Desktop v1.2.0, downloaded 73GB of weights, found why local mode was blocked, and
wrote 4 helper scripts. **Tested by Zac: partly** — he reached local mode and started a
10s/720p clip, then stopped it ~15 min in during decode. Zero completed videos so far.

**The key fact:** the app gates local mode on `psutil available >= 15GB`
(`runtime_policy.py: DARWIN_STREAMING_FLOOR_GB`). macOS hides reclaimable RAM in the
file cache, so **`sudo purge` is the fix** — closing apps does nothing, rebooting makes
it worse (Adobe auto-starts, Spotlight reindexes).

**Next up:**
1. `~/scripts/ltx-local.sh` to re-enter local mode (currently API-only)
2. First real test: SHORTEST duration + LOWEST resolution — prove one clip completes
   end to end and time it. Don't retry 10s/720p until a small one works.
3. Scale up gradually from there
4. Optional space back: ~22GB in `~/.cache/huggingface` (unrelated Qwen MLX models),
   31GB `Z-Image-Turbo` if he only wants video
5. Rotate the LTX API key — it was printed to terminal this session

**Start it:** `~/scripts/ltx-local.sh` — now does the WHOLE run in one command
(password, closes everything incl. Claude, purges, launches, prints the verdict, then
waits for ENTER and hands the window to the live monitor). Check mode:
`~/scripts/ltx-check.sh`. Monitor on its own: `~/scripts/ltx-monitor.sh`.
Cancel a run: `~/scripts/ltx-stop.sh`.

**Files that matter:** `~/scripts/ltx-{local,monitor,check,stop}.sh`,
`/Applications/LTX Desktop.app/Contents/Resources/backend/runtime_config/runtime_policy.py`,
`~/Library/Application Support/LTXDesktop/logs/` (the `[heartbeat]` lines).

**Watch out:**
- Nothing but Terminal open while generating — the pipeline needs ~13GB, Claude is ~3GB.
- The step counter FREEZES during decode. That is normal, not a stall. Watch the
  heartbeat (ticks every 15s). `ltx-monitor.sh` was already fixed for this.
- `~/scripts` is UNCOMMITTED and on branch `fix/downloads-none-found`, not main. The
  6 new ltx-*.sh files plus a modified backup-all.sh. **mac-scripts is a PUBLIC repo.**
- `ltx-watch.sh` is superseded by `ltx-monitor.sh` — delete it.
