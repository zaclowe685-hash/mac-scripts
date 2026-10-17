#!/usr/bin/env python3
"""Checks the runner's reading of REAL Claude Code messages (copied from the SUBNORTICA night, 13 Oct 2026)."""
import json, sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

on = SourceFileLoader('overnight', str(Path(__file__).resolve().parent.parent / 'overnight')).load_module()
fails = 0


def check(name, ok):
    global fails
    print(('PASS  ' if ok else 'FAIL  ') + name)
    fails += not ok


def result(text, err):
    return json.dumps({'duration_api_ms': 0, 'type': 'result', 'subtype': 'success', 'is_error': err, 'result': text})


real_limit = result("You've hit your session limit · resets 5:40am (Australia/Sydney)", True)
lines = [json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 'abc'}), real_limit]
check('real limit message is not a clean end', not on.clean_end(lines))
check('real limit message is found', bool(on.limit_text(lines)))
t, weekly = on.reset_time(on.limit_text(lines))
t = t and t - on.RESET_PAD  # the safety pad is configurable; check the time Claude gave
check('reset time read as 5:40am', t is not None and (t.hour, t.minute) == (5, 40) and not weekly)

t, weekly = on.reset_time("You've hit your session limit · resets 12:40am (Australia/Sydney)")
t = t and t - on.RESET_PAD
check('12:40am read as 00:40', t is not None and (t.hour, t.minute) == (0, 40))

t, weekly = on.reset_time("You've hit your weekly limit · resets Oct 22, 5am (Australia/Sydney)")
check('weekly limit recognised', weekly)

summary = result('Round 32 is done and committed (e15cf06).\n\n- **What happened overnight:** the 5-hour session '
                 'limit stopped everything from 02:16 until 05:40', False)
check('a summary that talks about the limit is a clean end', on.clean_end([summary]))

check('session id read from init line', on.session_id(lines) == 'abc')
check('assistant text about limits is ignored', not on.limit_text(
    [json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'usage limit reached'}]}})]))
sys.exit(1 if fails else 0)
