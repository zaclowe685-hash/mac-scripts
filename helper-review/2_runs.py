#!/usr/bin/env python3
"""One row per helper run since 3 Nov: type, job, cost, content read, report size, problems, parent context + turns after."""
import json, os, glob, sys, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
ROOT = os.path.expanduser("~/.claude/projects")
START = os.environ["HR_START"]  # UTC ISO, set by ./run
SYD = dt.timezone(dt.timedelta(hours=11))
calls = json.load(open(os.path.join(os.environ.get("HR_OUT", "/tmp/helper-review"), "calls.json")))
by_file = {}
for c in calls: by_file.setdefault(c["file"], []).append(c)

def tlen(x):
    if isinstance(x, str): return len(x)
    if isinstance(x, list): return sum(tlen(i.get("text", "") if isinstance(i, dict) else i) for i in x)
    return 0

def parent_info(parent_file, tool_use_id):
    """brief chars, report chars, parent ctx tokens at result, parent API calls after result (until compact/end), first ts"""
    brief = report = 0; ctx = 0; after = 0; seen = False; ts0 = None; seen_ids = set()
    if not os.path.exists(parent_file): return None
    for line in open(parent_file, errors="ignore"):
        try: d = json.loads(line)
        except Exception: continue
        m = d.get("message")
        if d.get("type") == "system" and d.get("subtype") == "compact_boundary" and seen: break
        if not isinstance(m, dict): continue
        cont = m.get("content")
        if isinstance(cont, list):
            for b in cont:
                if not isinstance(b, dict): continue
                if b.get("type") == "tool_use" and b.get("id") == tool_use_id:
                    brief = len(json.dumps(b.get("input", {}))); ts0 = d.get("timestamp")
                if b.get("type") == "tool_result" and b.get("tool_use_id") == tool_use_id:
                    report = max(report, tlen(b.get("content")))
                    seen = True
        if seen and d.get("type") == "assistant" and m.get("usage"):
            if m.get("id") in seen_ids: continue
            seen_ids.add(m.get("id"))
            u = m["usage"]
            tot = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
            if not ctx: ctx = tot
            after += 1
    return dict(brief=brief, report=report, ctx=ctx, after=after, ts0=ts0)

rows = []
for f in sorted(glob.glob(ROOT + "/**/subagents/*.jsonl", recursive=True)):
    cs = by_file.get(f)
    if not cs: continue
    meta = {}
    mp = f[:-6] + ".meta.json"
    if os.path.exists(mp): meta = json.load(open(mp))
    read_chars = 0; turns = len(cs); problems = set(); final = ""; compacts = 0; tools = 0
    for line in open(f, errors="ignore"):
        try: d = json.loads(line)
        except Exception: continue
        s = line.lower()
        if "thrashing" in s: problems.add("thrash")
        if d.get("type") == "system" and d.get("subtype") == "compact_boundary": compacts += 1
        m = d.get("message")
        if not isinstance(m, dict): continue
        cont = m.get("content")
        if isinstance(cont, list):
            for b in cont:
                if isinstance(b, dict) and b.get("type") == "tool_result": read_chars += tlen(b.get("content"))
                if isinstance(b, dict) and b.get("type") == "tool_use": tools += 1
                if d.get("type") == "assistant" and isinstance(b, dict) and b.get("type") == "text" and len(b.get("text", "")) > 200: final = b.get("text", "")
    sess_dir = os.path.dirname(os.path.dirname(f))
    parent = sess_dir + ".jsonl"
    pi = parent_info(parent, meta.get("toolUseId")) or {}
    ts = min(c["ts"] for c in cs)
    rows.append(dict(
        when=dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(SYD).strftime("%a %d %b %H:%M"),
        type=meta.get("agentType"), desc=meta.get("description"), kind=cs[0]["kind"],
        project=os.path.basename(os.path.dirname(sess_dir)).replace("-Users-zac09-", "~/").replace("-Users-zac09", "~"),
        session=os.path.basename(sess_dir)[:8], cost=round(sum(c["cost"] for c in cs), 4),
        model=cs[0]["fam"], turns=turns, tools=tools, read_k=round(read_chars / 4000, 1),
        max_in_k=round(max(c["tin"] for c in cs) / 1000, 1), out_k=round(sum(c["out"] for c in cs) / 1000, 1),
        compacts=compacts, problems=",".join(sorted(problems)), finished=meta.get("finished"),
        bg=meta.get("requestShape"), report_k=round(pi.get("report", 0) / 4000, 2), brief_k=round(pi.get("brief", 0) / 4000, 2),
        parent_ctx_k=round(pi.get("ctx", 0) / 1000, 1), parent_after=pi.get("after", 0),
        final_k=round(len(final) / 4000, 2), final_head=final[:220].replace("\n", " ")))
json.dump(rows, open(os.path.join(os.environ.get("HR_OUT", "/tmp/helper-review"), "runs.json"), "w"), indent=1)
for r in rows:
    print(f"{r['when']} | {r['type']} | {r['kind']} | {r['project']} {r['session']} | {r['desc']} | ${r['cost']:.3f} | turns {r['turns']} tools {r['tools']} | read {r['read_k']}k maxin {r['max_in_k']}k out {r['out_k']}k | compacts {r['compacts']} {r['problems']} | fin {r['finished']} | report {r['report_k']}k brief {r['brief_k']}k | parent ctx {r['parent_ctx_k']}k after {r['parent_after']}")
