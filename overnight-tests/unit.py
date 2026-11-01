#!/usr/bin/env python3
"""Checks the runner's reading of REAL Claude Code messages (copied from the SUBNORTICA night, 13 Oct 2026)."""
import json, os, sys, tempfile
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

os.environ.setdefault('OVERNIGHT_HOME', tempfile.mkdtemp(prefix='overnight-unit.'))  # never touch the real jobs
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

# ---- helpers (Zac's rule 13, 1 Nov 2026): cheap helpers on, except in games
home = Path.home()
check('helpers on in taskify', on.helpers_allowed(home / 'taskify'))
check('helpers on in subnortica (12 Oct exception)', on.helpers_allowed(home / 'subnortica'))
check('helpers off in peninsula', not on.helpers_allowed(home / 'peninsula'))
check('helpers off deep inside a game', not on.helpers_allowed(home / 'escape-rooms/rooms/aphelion'))
check('helpers off in old-peninsula', not on.helpers_allowed(home / 'old-peninsula'))
check('a name that only starts like a game is not one', on.helpers_allowed(home / 'peninsula-notes'))


def call(i, kind):
    return json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'id': f't{i}', 'name': 'Agent', 'input': {'subagent_type': kind} if kind else {}}]}})


def refused(i):
    return json.dumps({'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': f't{i}', 'is_error': True, 'content': 'blocked by hook'}]}})


log = Path(on.HOME) / 'unit-helpers.jsonl'
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text('\n'.join([call(1, 'haiku-scout'), call(2, 'haiku-scout'), call(3, 'sonnet-helper'), call(4, None),
                          refused(4), 'not json {tool_use']) + '\n')
check('helpers counted from the log', on.helper_counts(log) == ({'haiku-scout': 2, 'sonnet-helper': 1,
                                                                 'general-purpose': 1}, 1))
check('no log = no helpers', on.helper_counts(log.parent / 'missing.jsonl') == ({}, 0))


class FakeProc:
    pid = 999999


def launched(project):
    """The command the runner would start Claude with for a job in `project`."""
    name = 'unit-' + Path(project).name
    d = on.JOBS / name
    d.mkdir(parents=True, exist_ok=True)
    (d / 'job.json').write_text(json.dumps({'project': str(project), 'claude': 'claude', 'model': 'm',
                                            'effort': 'high', 'until': datetime.now().isoformat(),
                                            'created': datetime.now().isoformat()}))
    seen = {}
    real = on.subprocess.Popen
    on.subprocess.Popen = lambda cmd, **kw: seen.update(cmd=cmd) or FakeProc()
    try:
        job = on.Job(name)
        job.launch(on.PROMPT_FIRST.format(**job.paths), None)
    finally:
        on.subprocess.Popen = real
    return seen['cmd']


cmd = launched(home / 'taskify')
blocked = cmd[cmd.index('--disallowedTools') + 1:]
prompt = cmd[cmd.index('-p') + 1]
check('taskify: Agent not blocked, Workflow and questions still are',
      'Agent' not in blocked and 'Workflow' in blocked and 'AskUserQuestion' in blocked)
check('taskify: prompt names the three helpers', all(h in prompt for h in ('Explore', 'haiku-scout', 'sonnet-helper')))
check('taskify: prompt has no unfilled {slots}', '{' not in prompt)
check('taskify: prompt points at the real progress file', str(on.JOBS / 'unit-taskify' / 'PROGRESS.md') in prompt)
cmd = launched(home / 'peninsula')
blocked = cmd[cmd.index('--disallowedTools') + 1:]
prompt = cmd[cmd.index('-p') + 1]
check('peninsula: Agent, Task and Workflow blocked', {'Agent', 'Task', 'Workflow'} <= set(blocked))
check('peninsula: prompt says Opus only, names no helper', 'Opus only' in prompt and 'haiku-scout' not in prompt)

# ---- the helper hook: overnight its asks become a no; cheap helpers outside games still go straight through
import subprocess
HOOK =home / '.claude/hooks/ask-before-helper.sh'


def hook(kind, cwd, overnight, model=''):
    env = dict(os.environ)
    env.pop('OVERNIGHT_JOB_DIR', None)
    if overnight:
        env['OVERNIGHT_JOB_DIR'] = '/tmp/x'
    out = subprocess.run(['sh', str(HOOK)], input=json.dumps({'cwd': str(cwd), 'tool_name': 'Agent', 'tool_input': {
        'subagent_type': kind, 'model': model}}), capture_output=True, text=True, env=env).stdout.strip()
    return json.loads(out)['hookSpecificOutput']['permissionDecision'] if out else 'allow'


check('hook: haiku-scout overnight in taskify runs', hook('haiku-scout', home / 'taskify', True) == 'allow')
check('hook: general-purpose overnight is refused', hook('general-purpose', home / 'taskify', True) == 'deny')
check('hook: sonnet-helper forced onto Opus overnight is refused',
      hook('sonnet-helper', home / 'taskify', True, 'opus') == 'deny')
check('hook: daytime general-purpose still asks Zac', hook('general-purpose', home / 'taskify', False) == 'ask')
check('hook: daytime game helper still asks Zac', hook('haiku-scout', home / 'peninsula', False) == 'ask')
sys.exit(1 if fails else 0)
