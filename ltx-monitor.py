#!/usr/bin/env python3
"""Live monitor for LTX Desktop local generation on a 24GB Mac.

Shows available RAM against the ~13 GB the pipeline needs, and whether the
generation is actually advancing or has silently stalled.
"""
import json, os, subprocess, sys, time, urllib.request, glob, re

NEED = 13.0                      # GB the streaming pipeline needs while running
PORT = None
STALL_AFTER = 240                # seconds with no step change = probably stalled
LOGDIR = os.path.expanduser("~/Library/Application Support/LTXDesktop/logs")

C = dict(r="\033[0m", b="\033[1m", dim="\033[2m", grn="\033[32m",
         yel="\033[33m", red="\033[31m", cyn="\033[36m", clr="\033[2J\033[H")

def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=6).stdout.strip()
    except Exception: return ""

def backend():
    """Find the backend port + auth token (both change when LTX restarts)."""
    pid = sh("lsof -tiTCP -sTCP:LISTEN -P 2>/dev/null | xargs -I{} sh -c 'ps -p {} -o comm= | grep -qi python && echo {}' 2>/dev/null | head -1")
    if not pid: return None, None
    port = sh(f"lsof -a -p {pid} -iTCP -sTCP:LISTEN -P 2>/dev/null | tail -1 | sed -n 's/.*:\\([0-9]*\\) .*/\\1/p'")
    env = sh(f"ps eww -p {pid} 2>/dev/null | tr ' ' '\\n' | grep '^LTX_AUTH_TOKEN=' | cut -d= -f2-")
    return (port or None), (env or None)

def progress(port, tok):
    if not port: return None
    try:
        r = urllib.request.Request(f"http://localhost:{port}/api/generation/progress")
        if tok: r.add_header("Authorization", f"Bearer {tok}")
        with urllib.request.urlopen(r, timeout=4) as f:
            return json.load(f)
    except Exception:
        return None

def mem():
    try:
        import psutil
        v = psutil.virtual_memory()
        return v.available / 1024**3, v.used / 1024**3
    except Exception:
        out = sh("vm_stat")
        ps = 16384; free = inact = 0
        for line in out.splitlines():
            n = re.sub(r"[^0-9]", "", line.split(":")[-1]) or "0"
            if "Pages free" in line: free = int(n)
            elif "Pages inactive" in line: inact = int(n)
        return (free + inact) * ps / 1024**3, 0.0

def swap():
    m = re.search(r"used = ([0-9.]+)M", sh("sysctl -n vm.swapusage"))
    return float(m.group(1)) if m else 0.0

def route():
    """LOCAL or API, straight from the log."""
    try:
        f = max(glob.glob(os.path.join(LOGDIR, "*.log")), key=os.path.getmtime)
        txt = open(f, errors="ignore").read()
        started = re.findall(r"Generation \S+ started \((gpu|api)\)", txt)
        mode = re.findall(r"local_generations_mode=(\w+)", txt)
        if started: return ("LOCAL (gpu)" if started[-1] == "gpu" else "API (cloud)")
        if mode: return "LOCAL ready" if mode[-1] != "unsupported" else "API only"
    except Exception: pass
    return "unknown"


def heartbeat():
    """The backend logs a heartbeat every ~15s while working. This - NOT the step
    counter - is the real liveness signal: the step counter legitimately freezes
    during the VAE decode phase at the end of a generation."""
    try:
        f = max(glob.glob(os.path.join(LOGDIR, "*.log")), key=os.path.getmtime)
        last = None
        for line in open(f, errors="ignore"):
            if "[heartbeat]" in line:
                last = line
        if not last: return None
        m = re.search(r"\[heartbeat\] (\S+) (\w+) (\d+)s \| torch=([\d.]+)GiB driver=([\d.]+)GiB max=([\d.]+)GiB", last)
        ts = re.match(r"([\d-]+ [\d:,]+)", last)
        age = None
        if ts:
            import datetime
            t = datetime.datetime.strptime(ts.group(1).split(",")[0], "%Y-%m-%d %H:%M:%S")
            age = (datetime.datetime.now() - t).total_seconds()
        if m:
            return dict(kind=m.group(1), phase=m.group(2), secs=int(m.group(3)),
                        torch=float(m.group(4)), driver=float(m.group(5)),
                        mx=float(m.group(6)), age=age)
    except Exception:
        pass
    return None

def bar(frac, w=22, ch="#"):
    n = max(0, min(w, int(frac * w)))
    return ch * n + "." * (w - n)

def main():
    port, tok = backend()
    last_step, last_change, peak, started_at = None, time.time(), 0.0, None
    while True:
        a, u = mem(); peak = max(peak, u)
        p = progress(port, tok)
        if p is None:
            port, tok = backend()
            p = progress(port, tok)
        st = (p or {}).get("status", "?")
        cur = (p or {}).get("currentStep") or 0
        tot = (p or {}).get("totalSteps") or 0
        pct = (p or {}).get("progress") or 0
        phase = (p or {}).get("phase") or ""

        if st == "running":
            if started_at is None: started_at = time.time()
            if cur != last_step: last_step, last_change = cur, time.time()
        else:
            started_at, last_step = None, None

        ok = a >= NEED
        col = C["grn"] if ok else (C["yel"] if a >= NEED * 0.7 else C["red"])
        verdict = f"OK  (above {NEED:.0f})" if ok else f"LOW (below {NEED:.0f})"

        out = [C["clr"], f"{C['b']}  LTX MONITOR{C['r']}{C['dim']}          {time.strftime('%H:%M:%S')}{C['r']}", ""]
        out += [f"  {C['b']}MEMORY{C['r']}   {col}{a:5.1f} GB{C['r']} available   [{col}{bar(min(a/24,1))}{C['r']}]",
                f"           {col}{verdict}{C['r']}",
                f"{C['dim']}           peak used {peak:.1f} GB   swap {swap():.0f} MB{C['r']}", ""]

        hb = heartbeat()
        alive = hb is not None and hb.get("age") is not None and hb["age"] < 60
        if st == "running" or alive:
            el = hb["secs"] if hb else (int(time.time() - started_at) if started_at else 0)
            since = int(time.time() - last_change)
            phase_txt = hb["phase"] if hb else phase
            # decode phase reports no steps - that is normal, not a stall
            decoding = bool(tot) and cur >= tot or (hb and hb["phase"] != "inference") or (st == "running" and not tot)
            stalled = (not alive) and since > STALL_AFTER
            scol = C["red"] if stalled else C["cyn"]
            out += [f"  {C['b']}STATUS{C['r']}   {scol}GENERATING{C['r']}  {C['dim']}{phase_txt}{C['r']}"]
            if tot and cur < tot:
                out += [f"  {C['b']}STEP{C['r']}     {cur} / {tot}   [{bar(cur/tot)}]  {pct}%"]
            elif tot:
                out += [f"  {C['b']}STEP{C['r']}     {cur} / {tot}  {C['grn']}denoising done{C['r']} - now decoding to video+audio"]
            else:
                out += [f"  {C['b']}PROGRESS{C['r']} {pct}%   {C['dim']}(no step count in this phase){C['r']}"]
            out += [f"  {C['b']}ELAPSED{C['r']}  {el//60}m {el%60:02d}s"]
            if hb:
                out += [f"  {C['b']}GPU MEM{C['r']}  torch {hb['torch']:.2f} GiB   driver {hb['driver']:.2f} / {hb['mx']:.1f} GiB"]
                a2 = int(hb["age"] or 0)
                hcol = C["grn"] if a2 < 45 else C["red"]
                out += [f"  {C['b']}ALIVE{C['r']}    {hcol}heartbeat {a2}s ago{C['r']}   {C['dim']}(ticks every 15s while working){C['r']}"]
            if stalled:
                out += ["", f"  {C['red']}{C['b']}** HEARTBEAT STOPPED - GENUINELY STALLED **{C['r']}",
                        f"  {C['red']}  Quit LTX Desktop, run ~/scripts/ltx-local.sh,{C['r']}",
                        f"  {C['red']}  retry with a shorter / smaller clip.{C['r']}"]
            elif decoding:
                out += ["", f"  {C['dim']}  Decode is the slow part. Leave it alone.{C['r']}"]
        elif st in ("complete", "idle"):
            out += [f"  {C['b']}STATUS{C['r']}   {C['grn'] if st=='complete' else C['dim']}{st.upper()}{C['r']}"]
        else:
            out += [f"  {C['b']}STATUS{C['r']}   {C['dim']}{st}{C['r']}"]

        out += ["", f"  {C['b']}MODE{C['r']}     {route()}", "",
                f"{C['dim']}  Ctrl-C to stop. Safe to leave running.{C['r']}"]
        sys.stdout.write("\n".join(out) + "\n"); sys.stdout.flush()
        time.sleep(2)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\n")
