# overnight — Claude keeps working while you sleep

**Problem:** an app session that hits the 5-hour usage limit stops and waits for someone to tick
"restart after usage resets". At 2am nobody ticks it, so the night is wasted.

**Fix:** overnight work never runs in an app session. It runs under `~/scripts/overnight`, a plain
Python script that uses **no AI and no usage**. It's an alarm clock:

1. It starts Claude headless (`claude -p`) in the project folder with a brief.
2. Claude hits the limit and prints something like `You've hit your session limit · resets 5:40am`.
3. The script reads "5:40am" (ordinary text matching, not AI) and waits.
4. At 5:41 it resumes **the same conversation**: "the usage limit has reset, carry on".
5. At the deadline (default 06:00) Claude gets one "wrap up now" turn, then `REPORT.md` is written.

## Using it

Normally you just tell Claude "do this overnight" and the `/overnight` skill does all of this.

```
overnight start <project-folder> <brief.md> --name <name> [--until 06:00 | --hours 8] [--effort high]
overnight status            # every job: RUNNING / HOLDING (waiting for the limit) / FINISHED
overnight log <name>        # its timeline
overnight stop <name>
```

Everything for a job is in `~/.overnight/jobs/<name>/`:
`BRIEF.md` · `PROGRESS.md` (Claude's running notes) · `DONE` (Claude writes it when finished) ·
`REPORT.md` (the morning summary) · `events.log` (timeline) · `session.jsonl` (Claude's raw output).

## What it handles by itself

| Goes wrong | What the runner does |
|---|---|
| 5-hour limit, with a reset time | waits until that time + 1 min, resumes the same conversation |
| limit message it doesn't recognise / Claude dies within 3 min | treats it as the limit: waits 10 min, tries again (free if still limited), until the deadline |
| Claude stuck retrying a 429/overloaded error for 4+ min | stops it, treats it as the limit |
| Claude goes silent 30 min (frozen) | stops it, resumes it |
| Claude crashes after working a while | resumes it (up to 8 crashes) |
| Claude ends its turn early / asks a question | "Zac's asleep, make the call yourself, keep going" (up to 30 times; stops if it ends straight away 3 times in a row) |
| resume says the conversation is gone | starts a fresh session that reads PROGRESS.md and git log first |
| weekly limit | stops for the night, says so in the report (nothing can fix this one) |
| still working at the deadline | 30 min grace, then a "wrap up now" turn (20 min max), then the report |
| Claude Desktop quits (model mode) | nothing happens: the runner doesn't belong to the app |
| the runner itself crashes / the Mac reboots | launchd agent `com.zac.overnight` revives unfinished jobs every 2 min and at login; a running Claude is taken over, not restarted |
| Mac idle sleep | `caffeinate` holds it awake while a job is running |

**It can't fix** a closed lid (the Mac sleeps no matter what), a flat battery (`start` warns if
it's unplugged), or the weekly limit.

The overnight Claude is told: never ask questions, keep PROGRESS.md current, commit at milestones,
never push/deploy/publish/message/spend unless the brief says so, no subagents (blocked with
`--disallowedTools`), and write DONE only when everything is finished and checked.

## Testing

```
zsh ~/scripts/overnight-tests/run-tests.sh
```

This takes about 3 minutes and spends no usage. A fake Claude (`overnight-tests/fake-claude.py`) acts out every
row of the table above, plus the runner being killed mid-job, and checks each one ends the way it
should. Run it after any change to the runner.

Settings for testing are environment variables (`OVERNIGHT_TICK`, `OVERNIGHT_HOLD_SECS`,
`OVERNIGHT_SILENT_MINS`, … listed at the top of the script). `OVERNIGHT_HOME` moves the jobs folder.

Built 18 Oct 2026, generalised from the SUBNORTICA night dispatcher (`~/subnortica/night/run.py`),
which survived real limits on 13 Oct.
