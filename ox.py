#!/usr/bin/env python3
"""ox - talk to Ox Alpha, the free models on OpenRouter, and your own GLM plan.

  ox key                             paste ANY api key - it works out the rest
  ox "your question"                 ask Ox Alpha
  cat file.py | ox "review this"     pipe a file in
  ox -f a.js -f b.js "find the bug"  attach files
  ox -i photo.png "what is this"     attach an image
  ox -m glm/glm-5.3 "hi"             use your GLM subscription
  ox --race "prompt"                 Ox Alpha vs GLM side by side, timed
  ox --models                        list everything you can reach

Model ids starting with `glm/` go to your Z.ai plan; everything else goes to
OpenRouter. Keys live in ~/.config and never leave this machine.
"""
import sys, os, json, time, base64, urllib.request, urllib.error, argparse, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oxkeys

DEFAULT = "stealth/ox-alpha"


def route(model):
    """-> (base_url, key_name, upstream_model_id)"""
    if model.startswith("glm/"):
        return oxkeys.read_zai_config()["base"], "zai", model[4:]
    return oxkeys.OPENROUTER_API, "openrouter", model


def need_key(which):
    k = oxkeys.read_key(which)
    if not k:
        sys.exit(f"No {which} key yet. Run:  ox key")
    return k


def rival():
    """What --race puts up against Ox Alpha: your real GLM if it's set up."""
    if not oxkeys.read_key("zai"):
        return "z-ai/glm-5.2:free"
    models = oxkeys.read_zai_config().get("models") or ["glm-5.3"]
    best = next((m for m in models if m.startswith("glm-5.3")), models[0])
    return "glm/" + best


# ------------------------------------------------------------------ key setup
def add_key(pasted=None):
    print("Paste an API key and press enter. Any of these work:\n")
    print("  OpenRouter (free models + Ox Alpha)   https://openrouter.ai/keys")
    print("  Z.ai / GLM subscription               https://z.ai/manage-apikey/apikey-list")
    print("\n  (that Z.ai link is the DEVELOPER site - the chat site has no keys anywhere)\n")

    key = pasted
    if not key:
        try:
            key = input("key> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\ncancelled")

    print()
    result = oxkeys.accept_key(key, log=print)
    print()

    if result["ok"]:
        print("  " + result["message"])
        print("  saved to " + result["saved"])
        if result.get("models"):
            print("  models: " + ", ".join("glm/" + m for m in result["models"][:8]))
        print("\n  Reload http://localhost:5500 and it will pick this up.")
        return

    print("  Didn't work: " + result["error"])
    for line in result.get("tried", []):
        print("    - " + line)
    print("\n  If every line above says 401, the key itself is being rejected -")
    print("  make a fresh one and check nothing was cut off when copying.")
    sys.exit(1)


def list_models():
    print("== OpenRouter (free) ==")
    if not oxkeys.read_key("openrouter"):
        print("  no key yet - run:  ox key")
    try:
        with urllib.request.urlopen(f"{oxkeys.OPENROUTER_API}/models", timeout=20) as r:
            data = json.load(r)["data"]
        rows = []
        for m in data:
            p = m.get("pricing", {}) or {}
            if (m["id"].startswith("stealth/") or ":free" in m["id"]
                    or str(p.get("prompt", "1")) in ("0", "0.0")):
                rows.append((m["id"], m.get("context_length", 0)))
        rows.sort(key=lambda r: (r[0] != DEFAULT, -r[1]))
        for mid, ctx in rows:
            print(f"  {mid:<52} ctx {ctx}")
    except Exception as e:
        print("  (couldn't reach OpenRouter:", e, ")")

    print("\n== Your GLM subscription ==")
    if not oxkeys.read_key("zai"):
        return print("  no key yet - run:  ox key")
    cfg = oxkeys.read_zai_config()
    print(f"  via {cfg.get('label') or cfg['base']}")
    for m in cfg.get("models") or ["glm-5.3"]:
        print(f"  glm/{m}")


# ------------------------------------------------------------------ streaming
def stream(model, messages, sink, quiet=False):
    base, key_name, upstream_model = route(model)
    key = need_key(key_name)
    body = json.dumps({"model": upstream_model, "messages": messages, "stream": True}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if key_name == "openrouter":
        headers["HTTP-Referer"] = "https://localhost"
        headers["X-Title"] = "zac-ox-cli"

    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(f"{base}/chat/completions", data=body, headers=headers), timeout=900)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{key_name}: {oxkeys._why(e)}")

    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        bit = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
        if bit:
            sink.append(bit)
            if not quiet:
                sys.stdout.write(bit)
                sys.stdout.flush()


def build_messages(prompt, files, images, piped):
    parts = []
    for path in files:
        try:
            parts.append(f"--- {os.path.basename(path)} ---\n{open(path).read()}")
        except OSError as e:
            sys.exit(f"Can't read {path}: {e}")
    if piped:
        parts.append(piped)
    text = ("\n\n".join(parts) + "\n\n" + prompt).strip() if parts else prompt

    if not images:
        return [{"role": "user", "content": text}]
    content = [{"type": "text", "text": text}]
    for img in images:
        ext = os.path.splitext(img)[1].lstrip(".").lower() or "png"
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        b64 = base64.b64encode(open(img, "rb").read()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}})
    return [{"role": "user", "content": content}]


class TimedSink(list):
    """Records when the first token landed, without disturbing the text."""
    def __init__(self, backing, first, t0):
        super().__init__()
        self._b, self._f, self._t0 = backing, first, t0

    def append(self, item):
        if self._f[0] is None:
            self._f[0] = time.time() - self._t0
        self._b.append(item)


def race(messages, models):
    results = {}

    def run(model):
        t0 = time.time()
        text, first = [], [None]
        try:
            stream(model, messages, TimedSink(text, first, t0), quiet=True)
        except SystemExit as e:
            text.append(str(e))
        results[model] = (time.time() - t0, first[0], "".join(text))

    print(f"Racing {models[0]}  vs  {models[1]} ...\n", flush=True)
    threads = [threading.Thread(target=run, args=(m,)) for m in models]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    finished = [(m, results[m][0]) for m in models if results[m][1] is not None]
    winner = min(finished, key=lambda r: r[1])[0] if finished else None
    for model in models:
        total, ttft, text = results[model]
        print("=" * 72)
        print(f"{model}{'   <- FASTEST' if model == winner else ''}")
        print(f"  first token {ttft:.2f}s | total {total:.2f}s | {len(text)} chars"
              if ttft is not None else "  (failed)")
        print("=" * 72)
        print(text.strip() + "\n")


def main():
    # `ox key` / `ox setup` before argparse gets a chance to be clever about it
    if len(sys.argv) > 1 and sys.argv[1] in ("key", "keys", "setup", "login"):
        return add_key(sys.argv[2] if len(sys.argv) > 2 else None)

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("prompt", nargs="*")
    ap.add_argument("-m", "--model", default=DEFAULT)
    ap.add_argument("-f", "--file", action="append", default=[])
    ap.add_argument("-i", "--image", action="append", default=[])
    ap.add_argument("--race", action="store_true")
    ap.add_argument("--vs", default=None, help="what --race runs against")
    ap.add_argument("--key", "--setup", "--setup-glm", dest="key", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()

    if a.key:
        return add_key()
    if a.models:
        return list_models()
    if a.help or (not a.prompt and sys.stdin.isatty()):
        return print(__doc__)

    piped = "" if sys.stdin.isatty() else sys.stdin.read()
    messages = build_messages(" ".join(a.prompt), a.file, a.image, piped)

    if a.race:
        return race(messages, [a.model, a.vs or rival()])

    t0 = time.time()
    sink = []
    stream(a.model, messages, sink)
    print(f"\n\n\033[2m[{a.model} - {time.time() - t0:.1f}s, {len(''.join(sink))} chars]\033[0m")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
