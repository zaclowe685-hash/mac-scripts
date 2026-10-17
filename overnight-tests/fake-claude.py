#!/usr/bin/env python3
"""Stand-in for `claude` when testing ~/scripts/overnight (no usage spent).
The scenario is the first word of the job's BRIEF.md. Run counts live in the job folder."""
import json, os, sys, time, uuid
from datetime import datetime, timedelta
from pathlib import Path

args = sys.argv[1:]
prompt = args[args.index('-p') + 1]
resume = args[args.index('--resume') + 1] if '--resume' in args else None
job = Path(os.environ['OVERNIGHT_JOB_DIR'])
scenario = (job / 'BRIEF.md').read_text().split()[0]
marks = job / 'fake-runs'
run = int(marks.read_text()) + 1 if marks.exists() else 1
marks.write_text(str(run))
with open(job / 'fake-prompts.log', 'a') as f:
    f.write(f'run {run} resume={resume} :: {prompt[:70]!r}\n')

sid = resume or f'fake-{uuid.uuid4().hex[:8]}'


def out(o):
    print(json.dumps(o), flush=True)


def result(text, err=False, code=0):
    out({'type': 'result', 'subtype': 'success' if not err else 'error', 'is_error': err, 'result': text,
         'session_id': sid})
    sys.exit(code)


def done(text='all done'):
    (job / 'DONE').write_text(f'{scenario}: {text} (run {run})\n')
    result('Finished. I wrote DONE.')


if scenario == 'lost' and run == 2:
    print(f'Error: No conversation found with session ID: {resume}', flush=True)
    sys.exit(1)

out({'type': 'system', 'subtype': 'init', 'session_id': sid})
out({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Reading the brief. Note to self: fix the rate limit bug in api.js'}]}})
time.sleep(1)

if 'TIME IS UP' in prompt:
    done('wrapped up at the deadline')

if scenario == 'done':
    done()
elif scenario == 'limit-clock':      # "resets 3:41am" style, about a minute away
    if run == 1:
        t = datetime.now() + timedelta(minutes=1)
        h = t.strftime('%I').lstrip('0')
        result(f"You've hit your session limit · resets {h}:{t:%M}{t:%p}".lower().replace('you', 'You'), err=True, code=1)
    done()
elif scenario == 'limit-epoch':      # "Claude AI usage limit reached|<unix time>"
    if run == 1:
        result(f'Claude AI usage limit reached|{int(time.time()) + 8}', err=False, code=0)
    done()
elif scenario == 'unknown-fast':     # never-seen wording, dies fast -> treated as a limit
    if run == 1:
        print('Some brand new error wording', flush=True)
        sys.exit(1)
    done()
elif scenario == 'hang':             # goes silent -> stopped and resumed
    if run == 1:
        time.sleep(600)
    done()
elif scenario == 'retry-loop':       # keeps retrying a 429 forever -> treated as the limit
    if run == 1:
        for i in range(300):
            out({'type': 'system', 'subtype': 'api_retry', 'attempt': i, 'error': 'rate_limit', 'status': 429})
            time.sleep(1)
    done()
elif scenario == 'nudge':            # ends its turn with a question -> told to keep going
    if run == 1:
        result('Should I use blue or red for the button? Let me know and I will continue.')
    done()
elif scenario == 'never':            # never finishes -> runner gives up cleanly
    result('I think that is everything for now.')
elif scenario == 'weekly':           # weekly limit -> stop for the night, no waiting
    if run == 1:
        result("You've hit your weekly limit · resets Oct 22, 5am", err=True, code=1)
    done()
elif scenario == 'crash-slow':       # crashes after working a while (not a limit) -> resumed
    if run == 1:
        time.sleep(8)
        print('Error: something exploded', flush=True)
        sys.exit(1)
    done()
elif scenario == 'lost':             # resume says the conversation is gone -> fresh session
    if run == 1:
        result("You've hit your session limit · resets 99:99xx", err=True, code=1)  # unparseable -> fallback hold
    done('fresh session after a lost one')   # run 3
elif scenario == 'deadline':         # works past the deadline -> stopped, wrap-up turn, report
    for i in range(600):
        out({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': f'working {i}'}]}})
        time.sleep(1)
elif scenario == 'slow-done':        # used for the supervisor-crash test: works 20 s, talking as it goes
    for i in range(20):
        out({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': f'working {i}'}]}})
        time.sleep(1)
    done()
elif scenario == 'summary-mentions-limit':  # a normal finish that TALKS about limits must not count as a limit
    if run == 1:
        result('Done with part 1. I added a usage limit warning banner and rate limit handling. Part 2 next.')
    done()
else:
    result(f'unknown scenario {scenario}', err=True, code=1)
