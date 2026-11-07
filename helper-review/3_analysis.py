#!/usr/bin/env python3
"""A savings per helper run, B Opus context-size spread, C missed chances, D cost-state vs transcript, E Zac's helper comments."""
import json, os, glob, collections, datetime as dt, re
HERE = os.environ.get("HR_OUT", "/tmp/helper-review")
ROOT = os.path.expanduser("~/.claude/projects")
START = os.environ["HR_START"]  # UTC ISO, set by ./run
SYD = dt.timezone(dt.timedelta(hours=11))
calls = json.load(open(f"{HERE}/calls.json")); runs = json.load(open(f"{HERE}/runs.json"))
O_W1, O_R, O_OUT = 8.0, 0.20, 20.0   # Opus 1h write, cache read, output ($/M)

# ---------- A: savings per run, three assumptions ----------
SC = {"low": (1/3, 0.25, 0.0), "mid": (0.5, 0.4, 0.225), "high": (1.0, 0.6, 0.5)}
# (share of helper's reading Opus would pull in, Opus turns per helper turn, Sonnet saving as share of Opus-equivalent)
tot = collections.defaultdict(lambda: collections.defaultdict(float))
per_type = collections.defaultdict(lambda: collections.defaultdict(float))
for r in runs:
    if r["kind"] != "nongame": continue
    H = r["cost"]; after = min(r["parent_after"], 150); ctx = r["parent_ctx_k"] * 1000
    rep = max(r["final_k"], 0.3) * 1000; brief = r["brief_k"] * 1000
    overhead = brief * O_OUT / 1e6 + rep * (O_W1 + after * O_R) / 1e6
    for s, (f, tf, sv) in SC.items():
        if r["model"] == "haiku":
            content = f * r["read_k"] * 1000
            opus = content * (O_W1 + after * O_R) / 1e6 + max(1, round(r["turns"] * tf)) * ctx * O_R / 1e6
            net = opus - H - overhead
        else:  # sonnet build/audit piece: Opus doing the same piece costs H/(1-sv)
            opus = H / (1 - sv) if sv < 1 else H
            net = opus - H - overhead
        tot[s][r["when"][:10]] += net; per_type[s][r["type"]] += net
print("A. NET SAVED by day (low/mid/high):")
for d in sorted(tot["mid"], key=lambda x: dt.datetime.strptime(x + " 2026", "%a %d %b %Y")):
    print(f"  {d}: " + " / ".join(f"${tot[s][d]:.2f}" for s in SC))
print("  total: " + " / ".join(f"${sum(tot[s].values()):.2f}" for s in SC))
print("  by type (mid):", {k: round(v, 2) for k, v in per_type["mid"].items()})
print("  by type (low):", {k: round(v, 2) for k, v in per_type["low"].items()})
print("  helper spend:", round(sum(r["cost"] for r in runs if r["kind"] == "nongame"), 2))

# ---------- B: Opus main non-game calls by context size ----------
bands = [(0, 100e3), (100e3, 200e3), (200e3, 300e3), (300e3, 400e3), (400e3, 2e6)]
bc = collections.defaultdict(float); bn = collections.Counter()
for c in calls:
    if c["sub"] or c["fam"] != "opus" or c["kind"] != "nongame": continue
    for lo, hi in bands:
        if lo <= c["tin"] < hi: bc[(lo, hi)] += c["cost"]; bn[(lo, hi)] += 1
T = sum(bc.values())
print("\nB. Opus non-game main calls by context size:")
for b in bands: print(f"  {int(b[0]/1e3)}-{int(b[1]/1e3)}k: {bn[b]} calls, ${bc[b]:.2f} ({bc[b]/T*100:.0f}%)")
print(f"  total ${T:.2f}, {sum(bn.values())} calls, avg ctx {sum(c['tin'] for c in calls if not c['sub'] and c['fam']=='opus' and c['kind']=='nongame')/max(1,sum(bn.values()))/1e3:.0f}k")

# ---------- C + D + E: scan main session files ----------
GAMES = [l.strip() for l in open(os.path.expanduser("~/.claude/game-folders.txt")) if l.strip() and not l.startswith("#")]
big = []; costdiff = []; comments = []
mains = sorted({c["file"] for c in calls if not c["sub"] and c["kind"] == "nongame" and c["fam"] == "opus"})
sess_cost = collections.defaultdict(float)
for c in calls:
    sess_cost[c["file"].split("/subagents/")[0].replace(".jsonl", "")] += c["cost"]
HELPER_WORDS = re.compile(r"\b(haiku|sonnet|helper|subagent|sub-agent|scout|explore agent)\b", re.I)
for f in mains:
    entries = []
    for line in open(f, errors="ignore"):
        try: entries.append(json.loads(line))
        except Exception: pass
    # API calls index for carry
    api_ts = sorted({(e.get("timestamp"), (e.get("message") or {}).get("id")) for e in entries if e.get("type") == "assistant" and isinstance(e.get("message"), dict) and e["message"].get("usage")})
    compacts = [e.get("timestamp") for e in entries if e.get("type") == "system" and e.get("subtype") == "compact_boundary"]
    tool_uses = {}; edited = set()
    for e in entries:
        m = e.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("content"), list): continue
        for b in m["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tool_uses[b["id"]] = (b.get("name"), b.get("input", {}))
                if b.get("name") in ("Edit", "Write", "MultiEdit"): edited.add(b.get("input", {}).get("file_path"))
    for e in entries:
        ts = e.get("timestamp") or ""
        if ts < START: continue
        m = e.get("message")
        if e.get("type") == "user" and isinstance(m, dict):
            cont = m.get("content")
            txt = cont if isinstance(cont, str) else " ".join(b.get("text", "") for b in cont if isinstance(b, dict) and b.get("type") == "text") if isinstance(cont, list) else ""
            if txt and not txt.startswith("<") and HELPER_WORDS.search(txt) and len(txt) < 3000:
                comments.append((ts[:16], os.path.basename(f)[:8], txt[:260].replace("\n", " ")))
            if isinstance(cont, list):
                for b in cont:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        c_ = b.get("content"); n = len(c_) if isinstance(c_, str) else sum(len(x.get("text", "")) for x in c_ if isinstance(x, dict)) if isinstance(c_, list) else 0
                        if n >= 8000:
                            name, inp = tool_uses.get(b.get("tool_use_id"), ("?", {}))
                            nxt = min([c for c in compacts if c > ts] or ["9999"])
                            after = sum(1 for t, _ in api_ts if t and ts < t < nxt)
                            tok = n / 4
                            carry = tok * (O_W1 + min(after, 150) * O_R) / 1e6
                            target = inp.get("file_path") or inp.get("url") or inp.get("command", "")[:90] or inp.get("prompt", "")[:60]
                            keep = name == "Read" and inp.get("file_path") in edited
                            if name in ("Agent", "Task", "SendMessage"): continue
                            big.append(dict(ts=ts[:16], sess=os.path.basename(f)[:8], proj=os.path.basename(os.path.dirname(f)).replace("-Users-zac09", "~"), tool=name, tok=int(tok), after=after, cost=round(carry, 3), keep=keep, target=str(target)[:90]))
    # D cost-state
    cs = [e for e in entries if e.get("type") == "cost-state"]
    if cs:
        costdiff.append((os.path.basename(f)[:8], cs[-1].get("totalCostUSD", 0), sess_cost.get(f.replace(".jsonl", ""), 0)))
print("\nC. Big reads (>=2k tok) Opus pulled into non-game main sessions since 3 Nov:")
print(f"  {len(big)} reads, carry cost ${sum(b['cost'] for b in big):.2f}; read-then-edited (keep with Opus): {sum(1 for b in big if b['keep'])} ${sum(b['cost'] for b in big if b['keep']):.2f}")
bt = collections.defaultdict(lambda: [0, 0.0])
for b in big:
    if not b["keep"]: bt[b["tool"]][0] += 1; bt[b["tool"]][1] += b["cost"]
print("  not-edited by tool:", {k: (v[0], round(v[1], 2)) for k, v in sorted(bt.items(), key=lambda x: -x[1][1])})
for b in sorted([b for b in big if not b["keep"]], key=lambda b: -b["cost"])[:28]:
    print(f"  {b['ts']} {b['proj']} {b['sess']} {b['tool']} {b['tok']//1000}k x{b['after']} ${b['cost']:.2f} :: {b['target']}")
print("\nD. cost-state total vs transcript sum (sessions with both):")
for s, a, b in costdiff:
    if a > 1: print(f"  {s}: cost-state ${a:.2f} vs transcripts ${b:.2f}")
print("\nE. Zac's messages mentioning helpers since 3 Nov:")
for c in comments[:40]: print(" ", c)
json.dump(big, open(f"{HERE}/big.json", "w"), indent=1)
