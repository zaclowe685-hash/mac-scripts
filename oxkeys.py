#!/usr/bin/env python3
"""Shared key handling for OX LAB and the `ox` CLI.

One job: take whatever key the user pastes, work out who it belongs to and
which endpoint actually answers, then write that down so nothing has to be
configured by hand ever again.

  ~/.config/openrouter/key      the OpenRouter key, plain text
  ~/.config/zai/key             the Z.ai / BigModel key, plain text
  ~/.config/zai/config.json     {base, models[]} - whichever endpoint actually worked
"""
import os, json, urllib.request, urllib.error

CONFIG_DIR = os.path.expanduser("~/.config")
KEY_FILES = {
    "openrouter": os.path.join(CONFIG_DIR, "openrouter", "key"),
    "zai": os.path.join(CONFIG_DIR, "zai", "key"),
}
ZAI_CONFIG = os.path.join(CONFIG_DIR, "zai", "config.json")
ENV_KEYS = {"openrouter": "OPENROUTER_API_KEY", "zai": "ZAI_API_KEY"}

OPENROUTER_API = "https://openrouter.ai/api/v1"

# Tried in order. The coding endpoints draw on a Coding Plan subscription;
# the paas ones bill pay-as-you-go credits, so they are the fallback.
ZAI_ENDPOINTS = [
    ("https://api.z.ai/api/coding/paas/v4", "Z.ai Coding Plan"),
    ("https://open.bigmodel.cn/api/coding/paas/v4", "BigModel Coding Plan"),
    ("https://api.z.ai/api/paas/v4", "Z.ai pay-as-you-go"),
    ("https://open.bigmodel.cn/api/paas/v4", "BigModel pay-as-you-go"),
]
ZAI_CANDIDATE_MODELS = ["glm-5.3", "glm-5-turbo", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5"]

DEFAULT_ZAI_BASE = ZAI_ENDPOINTS[0][0]


# ─────────────────────────────── storage ───────────────────────────────
def read_key(which):
    env = os.environ.get(ENV_KEYS[which])
    if env and env.strip():
        return env.strip()
    path = KEY_FILES[which]
    if os.path.exists(path):
        k = open(path).read().strip()
        if k:
            return k
    return None


def write_key(which, key):
    path = KEY_FILES[which]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.chmod(os.path.dirname(path), 0o700)
    with open(path, "w") as f:
        f.write(key.strip())
    os.chmod(path, 0o600)
    return path


def read_zai_config():
    if os.path.exists(ZAI_CONFIG):
        try:
            c = json.load(open(ZAI_CONFIG))
            if c.get("base"):
                return c
        except (json.JSONDecodeError, OSError):
            pass
    return {"base": DEFAULT_ZAI_BASE, "models": [], "label": ""}


def write_zai_config(base, models, label=""):
    os.makedirs(os.path.dirname(ZAI_CONFIG), exist_ok=True)
    json.dump({"base": base, "models": models, "label": label}, open(ZAI_CONFIG, "w"), indent=2)
    os.chmod(ZAI_CONFIG, 0o600)


# ─────────────────────────────── http ───────────────────────────────
def _req(url, key, body=None, timeout=25):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def _why(e):
    """Turn an HTTPError into something a human can act on."""
    try:
        raw = e.read().decode("utf-8", "replace")[:400]
    except Exception:
        raw = ""
    msg = raw
    try:
        j = json.loads(raw)
        msg = ((j.get("error") or {}).get("message")
               or j.get("message") or (j.get("error") or {}).get("code") or raw)
    except Exception:
        pass
    hint = {
        401: "the key was rejected - wrong key, or copied with a character missing",
        403: "the key is valid but not allowed here - the plan may not cover this endpoint",
        404: "no such endpoint",
        429: "rate limited or out of quota",
    }.get(e.code, "")
    return f"HTTP {e.code}{' - ' + hint if hint else ''}{': ' + msg if msg else ''}"


# ─────────────────────────────── probes ───────────────────────────────
def probe_openrouter(key):
    """-> {'ok':bool, 'error':str, 'models':[...]}"""
    try:
        data = _req(f"{OPENROUTER_API}/key", key)
        return {"ok": True, "error": "", "label": "OpenRouter",
                "detail": data.get("data", {}).get("label", "")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": _why(e), "label": "OpenRouter"}
    except Exception as e:
        return {"ok": False, "error": str(e), "label": "OpenRouter"}


def probe_zai(key, log=None):
    """Find an endpoint that actually answers with this key.

    -> {'ok':bool, 'base':str, 'models':[...], 'label':str, 'error':str, 'tried':[...]}
    """
    say = log or (lambda *_: None)
    tried = []

    for base, label in ZAI_ENDPOINTS:
        say(f"  trying {label} ...")

        # 1. ask the endpoint what it offers
        try:
            data = _req(f"{base}/models", key, timeout=15)
            ids = [m["id"] for m in data.get("data", []) if m.get("id")]
            if ids:
                say(f"    works - {len(ids)} models")
                return {"ok": True, "base": base, "models": ids, "label": label,
                        "error": "", "tried": tried}
            tried.append(f"{label}: model list came back empty")
        except urllib.error.HTTPError as e:
            reason = _why(e)
            tried.append(f"{label}: {reason}")
            # a rejected key will be rejected everywhere - don't hammer the rest
            if e.code == 401 and base == ZAI_ENDPOINTS[0][0]:
                say(f"    {reason}")
        except Exception as e:
            tried.append(f"{label}: {e}")

        # 2. some endpoints don't expose /models - try an actual tiny completion
        for model in ZAI_CANDIDATE_MODELS[:3]:
            try:
                _req(f"{base}/chat/completions", key, timeout=25, body={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                })
                say(f"    works - {model} answered")
                return {"ok": True, "base": base, "models": [model], "label": label,
                        "error": "", "tried": tried}
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    tried.append(f"{label}/{model}: {_why(e)}")
                    break                       # key problem, not a model problem
                tried.append(f"{label}/{model}: {_why(e)}")
            except Exception as e:
                tried.append(f"{label}/{model}: {e}")

    return {"ok": False, "base": "", "models": [], "label": "",
            "error": "No Z.ai endpoint accepted this key.", "tried": tried}


# ─────────────────────────────── the one entry point ───────────────────────────────
def accept_key(key, log=None):
    """Take a pasted key, work out what it is, save it. -> result dict."""
    say = log or (lambda *_: None)
    key = (key or "").strip().strip('"').strip("'")
    if not key:
        return {"ok": False, "kind": "", "error": "Nothing pasted."}
    if any(c.isspace() for c in key):
        key = "".join(key.split())
        say("  (stripped whitespace out of the pasted key)")

    # OpenRouter keys are unmistakable
    if key.startswith("sk-or-"):
        say("Looks like an OpenRouter key. Checking...")
        r = probe_openrouter(key)
        if r["ok"]:
            path = write_key("openrouter", key)
            return {"ok": True, "kind": "openrouter", "saved": path,
                    "message": "OpenRouter key saved and working."}
        return {"ok": False, "kind": "openrouter", "error": r["error"]}

    # otherwise assume Z.ai / BigModel, and find the endpoint that answers
    say("Checking this against Z.ai...")
    r = probe_zai(key, log=say)
    if r["ok"]:
        path = write_key("zai", key)
        write_zai_config(r["base"], r["models"], r["label"])
        return {"ok": True, "kind": "zai", "saved": path, "base": r["base"],
                "models": r["models"], "label": r["label"],
                "message": f"GLM key saved and working via {r['label']}."}

    # last resort: maybe it IS an OpenRouter key without the usual prefix
    say("Z.ai said no. Trying OpenRouter just in case...")
    o = probe_openrouter(key)
    if o["ok"]:
        path = write_key("openrouter", key)
        return {"ok": True, "kind": "openrouter", "saved": path,
                "message": "That turned out to be an OpenRouter key. Saved and working."}

    return {"ok": False, "kind": "", "error": r["error"], "tried": r["tried"]}
