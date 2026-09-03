#!/usr/bin/env python3
"""Prune throwaway Claude Code sessions so `claude --resume` stays readable.

Sessions live as .jsonl transcripts under ~/.claude/projects/. Most of the
clutter is not chat Zac had -- it is robots: the 3am solve-gaps launchd job,
Night Shift's own foreman/report runs, smoke tests. Those regenerate nightly.

Nothing is deleted outright. Junk is MOVED to ~/.claude/projects-trash/,
and trash older than KEEP_TRASH_DAYS is swept on the next run.

    prune-sessions.py --dry-run        # show what would go, change nothing
    prune-sessions.py                  # do it
    prune-sessions.py --empty          # also sweep old trash immediately
    prune-sessions.py --before 2026-08-25   # ALSO cull everything older than a date

--before is the big broom, for when the list has grown past reading. It ignores
how good a session was and goes purely on age -- the reasoning worth keeping is
already written into each project's GAME.md / HANDOFF.md, not into the chat log.
"""

import json
import os
import shutil
import sys
import time

PROJECTS = os.path.expanduser("~/.claude/projects")
TRASH = os.path.expanduser("~/.claude/projects-trash")

# A session touched more recently than this might still be running. Never touch it.
SAFE_HOURS = 48
KEEP_TRASH_DAYS = 30

# Opening prompts that mean "a machine started this, not Zac".
ROBOT_PROMPTS = (
    "use the solve-gaps skill for gap map",
    "# you are writing the morning report",
    "# you are the night shift foreman",
    "reply with exactly: ok",
    "say ok and nothing else",
)


def read_session(path):
    """Return (real_user_prompt_count, tool_use_count, first_prompt)."""
    prompts = 0
    tools = 0
    first = ""
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            kind = d.get("type")

            if kind == "user":
                content = msg.get("content")
                if isinstance(content, list):
                    # A tool_result is the harness talking back, not Zac.
                    if any(
                        isinstance(x, dict) and x.get("type") == "tool_result"
                        for x in content
                    ):
                        continue
                    text = " ".join(
                        x.get("text", "")
                        for x in content
                        if isinstance(x, dict) and x.get("type") == "text"
                    )
                elif isinstance(content, str):
                    text = content
                else:
                    continue
                text = text.strip()
                # Leading '<' is a system-reminder or similar injected block.
                if not text or text.startswith("<"):
                    continue
                prompts += 1
                if not first:
                    first = text

            elif kind == "assistant":
                for x in msg.get("content") or []:
                    if isinstance(x, dict) and x.get("type") == "tool_use":
                        tools += 1

    return prompts, tools, first


def verdict(prompts, tools, first):
    """Why this session is junk, or None to keep it."""
    head = first[:120].lower()
    for pattern in ROBOT_PROMPTS:
        if head.startswith(pattern):
            return "robot run"
    if prompts == 0:
        return "no real prompt"
    if prompts <= 2 and tools <= 1:
        return "abandoned (%dp/%dt)" % (prompts, tools)
    return None


def sweep_trash(dry):
    if not os.path.isdir(TRASH):
        return 0
    cutoff = time.time() - KEEP_TRASH_DAYS * 86400
    gone = 0
    for name in os.listdir(TRASH):
        path = os.path.join(TRASH, name)
        if os.path.getmtime(path) < cutoff:
            print("  sweep %s" % name)
            if not dry:
                os.remove(path)
            gone += 1
    return gone


def real_last_activity(path):
    """When the conversation actually ended, from the transcript's own timestamps.

    The file's mtime is NOT this. Claude Code rewrites transcripts in bulk (a
    migration on startup, for instance), which resets mtime on old chats -- on
    2026-09-01 that made 85 of 144 sessions look like they happened that day.
    Every jsonl line carries an ISO timestamp; the last one is the truth.
    """
    last = None
    try:
        with open(path, errors="ignore") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("timestamp"):
                    last = d["timestamp"]
    except OSError:
        return None
    if not last:
        return None
    # "2026-08-31T19:56:42.089Z" -> epoch seconds, UTC.
    from calendar import timegm

    return timegm(time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S"))


def parse_before():
    if "--before" not in sys.argv:
        return None
    stamp = sys.argv[sys.argv.index("--before") + 1]
    return time.mktime(time.strptime(stamp, "%Y-%m-%d"))


def main():
    dry = "--dry-run" in sys.argv
    before = parse_before()
    cutoff = time.time() - SAFE_HOURS * 3600
    doomed = []

    for root, _dirs, files in os.walk(PROJECTS):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(root, name)
            # Only mtime can tell us a file is being written THIS INSTANT (the
            # live session). It cannot tell us how old the chat is -- a bulk
            # rewrite resets it -- so the age question is answered below, from
            # the transcript itself. Guarding age on mtime protected July chats
            # that had merely been rewritten tonight.
            if time.time() - os.path.getmtime(path) < 300:
                continue
            age = real_last_activity(path)
            if age is None:
                continue
            if age > cutoff:
                continue
            # Age cull wins outright -- no need to score a session we're binning.
            if before is not None and age < before:
                doomed.append((path, "older than cutoff", ""))
                continue
            try:
                prompts, tools, first = read_session(path)
            except OSError:
                continue
            why = verdict(prompts, tools, first)
            if why:
                doomed.append((path, why, first[:60].replace("\n", " ")))

    if not doomed:
        print("nothing to prune")
    else:
        os.makedirs(TRASH, exist_ok=True)
        freed = 0
        for path, why, first in doomed:
            freed += os.path.getsize(path)
            project = os.path.basename(os.path.dirname(path))
            print("%-22s %s  %s" % (why, project[:30], first or "(empty)"))
            if not dry:
                # Flatten the project name into the filename so two sessions
                # with the same uuid-ish name in different projects can coexist.
                dest = os.path.join(TRASH, "%s__%s" % (project, os.path.basename(path)))
                shutil.move(path, dest)
                # shutil.move keeps the original mtime, so an old session would
                # be swept on this very run. Stamp it with the move time instead,
                # which is what KEEP_TRASH_DAYS is actually counting from.
                os.utime(dest, None)
        verb = "would move" if dry else "moved"
        print("\n%s %d sessions (%.1f MB) to %s" % (verb, len(doomed), freed / 1e6, TRASH))

    if not dry or "--empty" in sys.argv:
        print("\ntrash older than %d days:" % KEEP_TRASH_DAYS)
        if sweep_trash(dry) == 0:
            print("  (none)")


if __name__ == "__main__":
    main()
