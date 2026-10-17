#!/bin/zsh
# Test ~/scripts/overnight against a fake Claude — every way a night can go wrong. No usage spent.
# Takes about 3 minutes. Prints PASS/FAIL per scenario.
HERE=${0:A:h}
export OVERNIGHT_HOME=$(mktemp -d /tmp/overnight-test.XXXX)
export OVERNIGHT_NO_LAUNCHD=1 OVERNIGHT_SKIP_PREFLIGHT=1
export CLAUDE_BIN=$HERE/fake-claude.py
export OVERNIGHT_TICK=1 OVERNIGHT_HOLD_SECS=5 OVERNIGHT_SILENT_MINS=0.1 OVERNIGHT_RETRY_LOOP_SECS=5
export OVERNIGHT_QUICK_EXIT_SECS=4 OVERNIGHT_GRACE_MINS=0.1 OVERNIGHT_WRAPUP_MINS=0.5 OVERNIGHT_MAX_NUDGES=5
export OVERNIGHT_STUCK_RUN_SECS=5 OVERNIGHT_RESET_PAD_SECS=1
chmod +x $CLAUDE_BIN
ON=$HERE/../overnight
python3 $HERE/unit.py || UNIT_FAIL=1
PROJ=$(mktemp -d /tmp/overnight-proj.XXXX)
cd $PROJ && git init -q && git commit -q --allow-empty -m start && cd - >/dev/null

typeset -A EXPECT
EXPECT=(
  done                     'done — Claude finished'
  limit-clock              'done — Claude finished'
  limit-epoch              'done — Claude finished'
  unknown-fast             'done — Claude finished'
  hang                     'done — Claude finished'
  retry-loop               'done — Claude finished'
  nudge                    'done — Claude finished'
  never                    'kept stopping straight away'
  weekly                   'WEEKLY usage limit'
  crash-slow               'done — Claude finished'
  lost                     'done — Claude finished'
  deadline                 'done — Claude finished'
  slow-done                'done — Claude finished'
  summary-mentions-limit   'done — Claude finished'
  stopme                   'stopped by you'
)
for s in ${(k)EXPECT}; do
  echo "$s" > $PROJ/brief-$s.md
  secs=900; [[ $s == deadline ]] && secs=6
  $ON start $PROJ $PROJ/brief-$s.md --name $s --seconds $secs >/dev/null || echo "start failed: $s"
done

# supervisor crash: kill slow-done's supervisor, then let "revive" (what launchd runs) take over
sleep 4
pkill -f "_supervise slow-done"
sleep 1
$ON revive
# stop command
$ON stop stopme >/dev/null

# wait for everything to end (max 4 min)
for i in {1..240}; do
  left=0
  for s in ${(k)EXPECT}; do
    st=$(python3 -c "import json;print(json.load(open('$OVERNIGHT_HOME/jobs/$s/state.json')).get('status'))" 2>/dev/null)
    [[ $st == finished || $st == stopped ]] || left=1
  done
  (( left == 0 )) && break
  sleep 1
done

fail=0
for s in ${(ok)EXPECT}; do
  reason=$(python3 -c "import json;print(json.load(open('$OVERNIGHT_HOME/jobs/$s/state.json')).get('end_reason'))" 2>/dev/null)
  runs=$(cat $OVERNIGHT_HOME/jobs/$s/fake-runs 2>/dev/null)
  if [[ $reason == *${EXPECT[$s]}* && -f $OVERNIGHT_HOME/jobs/$s/REPORT.md ]]; then
    echo "PASS  $s  (runs: $runs)  $reason"
  else
    echo "FAIL  $s  (runs: $runs)  got: $reason"; fail=1
    sed 's/^/        /' $OVERNIGHT_HOME/jobs/$s/events.log 2>/dev/null
  fi
done
# extra checks
[[ $(cat $OVERNIGHT_HOME/jobs/slow-done/fake-runs) == 1 ]] && echo "PASS  revive took over the running Claude (no second launch)" || { echo "FAIL  revive relaunched Claude"; fail=1; }
grep -q 'limit has reset' $OVERNIGHT_HOME/jobs/limit-clock/fake-prompts.log && echo "PASS  resumed with 'the usage limit has reset'" || { echo "FAIL  limit resume prompt"; fail=1; }
grep -q 'resume=fake-' $OVERNIGHT_HOME/jobs/limit-clock/fake-prompts.log && echo "PASS  resumed the SAME conversation" || { echo "FAIL  same-conversation resume"; fail=1; }
grep -q 'LIMIT' $OVERNIGHT_HOME/jobs/summary-mentions-limit/events.log && { echo "FAIL  a summary mentioning limits was mistaken for the limit"; fail=1; } || echo "PASS  a summary mentioning limits is not mistaken for the limit"
grep -q 'TIME IS UP' $OVERNIGHT_HOME/jobs/deadline/fake-prompts.log && echo "PASS  deadline wrap-up turn sent" || { echo "FAIL  wrap-up"; fail=1; }
sleep 2
LEFT="fake-claude.py|_supervise (${(kj:|:)EXPECT})\$"
pgrep -f "$LEFT" >/dev/null && { echo "FAIL  processes left running:"; pgrep -fl "$LEFT"; pkill -f "$LEFT"; fail=1; } || echo "PASS  nothing left running"
(( UNIT_FAIL )) && fail=1
echo "test home: $OVERNIGHT_HOME"
(( fail )) && echo "SOME TESTS FAILED" || echo "ALL PASSED"
exit $fail
