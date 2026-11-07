#!/usr/bin/env python3
"""Helper review 3-7 Nov 2026: cost of every API call by day/model/kind, plus per-helper-run detail."""
import json, os, glob, sys, collections, datetime as dt

ROOT = os.path.expanduser("~/.claude/projects")
START = os.environ["HR_START"]  # UTC ISO, set by ./run
SYD = dt.timezone(dt.timedelta(hours=11))
GAMES = [l.strip() for l in open(os.path.expanduser("~/.claude/game-folders.txt")) if l.strip() and not l.startswith("#")]
HOME = os.path.expanduser("~")

# $ per million: in, out, cache read, cache write 5m, cache write 1h
P = {
    "opus":   (4.0, 20.0, 0.20, 5.0, 8.0),
    "sonnet": (2.0, 10.0, 0.10, 2.5, 4.0),
    "haiku":  (0.10, 0.50, 0.01, 0.125, 0.20),
}
if len(sys.argv) > 1:  # optional price override json
    P.update({k: tuple(v) for k, v in json.load(open(sys.argv[1])).items()})

def fam(model):
    m = (model or "").lower()
    for k in ("opus", "sonnet", "haiku", "fable"):
        if k in m: return k
    return "other"

def cost(model, u):
    f = fam(model)
    if f not in P: f = "opus"
    pi, po, pr, pw5, pw1 = P[f]
    cc = u.get("cache_creation") or {}
    w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
    w5 = cc.get("ephemeral_5m_input_tokens", 0) or 0
    if not cc: w5 = u.get("cache_creation_input_tokens", 0) or 0
    inp = u.get("input_tokens", 0) or 0
    cr = u.get("cache_read_input_tokens", 0) or 0
    out = u.get("output_tokens", 0) or 0
    c = (inp*pi + out*po + cr*pr + w5*pw5 + w1*pw1) / 1e6
    total_in = inp + cr + w5 + w1
    if f == "haiku" and total_in > 100_000: c *= 5   # Haiku's >100k price line
    return c, total_in, out

def kind_of(cwd, path):
    if "model-duel-arena" in path: return "duel"
    if cwd.startswith("/private/tmp") or cwd.startswith("/tmp"): return "test"
    rel = os.path.relpath(cwd, HOME) if cwd.startswith(HOME) else cwd
    first = rel.split(os.sep)[0]
    if first in GAMES or "subnortica" == first: return "game" if first != "subnortica" else "game-subnortica"
    return "nongame"

def day(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(SYD).strftime("%a %d %b")

calls = {}   # msg id -> record
files = [f for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True) if os.path.getmtime(f) > dt.datetime.fromisoformat(START.replace("Z", "+00:00")).timestamp()]
for f in files:
    sub = "/subagents/" in f
    atype = None
    if sub:
        mp = f[:-6] + ".meta.json"
        if os.path.exists(mp):
            try: atype = json.load(open(mp)).get("agentType")
            except Exception: pass
    cwd = ""
    for line in open(f, errors="ignore"):
        try: d = json.loads(line)
        except Exception: continue
        cwd = d.get("cwd") or cwd
        m = d.get("message")
        if not isinstance(m, dict) or not m.get("usage") or d.get("type") != "assistant": continue
        ts = d.get("timestamp", "")
        if ts < START: continue
        mid = m.get("id") or d.get("uuid")
        c, tin, out = cost(m.get("model"), m["usage"])
        rec = dict(ts=ts, model=m.get("model"), fam=fam(m.get("model")), cost=c, tin=tin, out=out,
                   sub=sub, atype=atype or ("main" if not sub else "unknown"), kind=kind_of(cwd, f), file=f)
        old = calls.get(mid)
        if not old or out >= old["out"]: calls[mid] = rec

json.dump(list(calls.values()), open(os.path.join(os.environ.get("HR_OUT", "/tmp/helper-review"), "calls.json"), "w"))

agg = collections.defaultdict(float)
for r in calls.values():
    who = r["atype"] if r["sub"] else "main"
    agg[(day(r["ts"]), r["kind"], r["fam"], who)] += r["cost"]
days = sorted({k[0] for k in agg}, key=lambda s: dt.datetime.strptime(s + " 2026", "%a %d %b %Y"))
print("DAY | kind | model | who | $")
for d_ in days:
    for k in sorted(k for k in agg if k[0] == d_):
        if agg[k] >= 0.01: print(f"{d_} | {k[1]} | {k[2]} | {k[3]} | {agg[k]:.2f}")
print("\nTOTALS by kind/who:")
t = collections.defaultdict(float)
for k, v in agg.items(): t[(k[1], k[3] if k[3] == "main" else "helper:" + k[3], k[2])] += v
for k in sorted(t): print(k, f"{t[k]:.2f}")
