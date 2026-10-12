"""W11-alpha step 1.1 — provider availability probe, CODING side.

Read-only: one tiny LLM call (max 32 tokens) + a docker CLI check.
Writes its report into the WIKI workspace (the caller's repo), never into the coding repo.
Never prints API keys — only presence booleans.

Run from the coding repo root:
    D:\\CodexPython312\\python.exe "D:\\AI project\\Arknights LLM Wiki\\output\\_w11_probe\\probe_coding_provider.py"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

CODING = r"D:\AI project\Knowledge-Augmented Autonomous Coding Agent"
OUT = Path(r"D:\AI project\Arknights LLM Wiki\output\_w11_probe")
OUT.mkdir(parents=True, exist_ok=True)
res: dict = {"side": "coding", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

sys.path.insert(0, CODING)
os.chdir(CODING)

from agent.llm import (  # noqa: E402
    LLM_PROVIDERS,
    FALLBACK_PROVIDER,
    PROVIDER_PREFERENCE,
    OpenAICompatClient,
    _resolve_provider_name,
)

res["resolved_provider"] = _resolve_provider_name(os.environ)
res["provider_preference"] = list(PROVIDER_PREFERENCE)
res["fallback_provider"] = FALLBACK_PROVIDER
res["env_keys_present"] = {
    conf["key_env"]: bool(os.environ.get(conf["key_env"]))
    for conf in LLM_PROVIDERS.values()
}


def load_dotenv_keys() -> list[str]:
    """Best-effort .env load; returns the key NAMES that were filled (never values)."""
    filled: list[str] = []
    env_path = Path(CODING) / ".env"
    if not env_path.exists():
        return filled
    wanted = {conf["key_env"] for conf in LLM_PROVIDERS.values()}
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k in wanted and v and not os.environ.get(k):
            os.environ[k] = v
            filled.append(k)
    return filled


def probe_call() -> None:
    client = OpenAICompatClient()
    res["client"] = {
        "model": client.model,
        "base_url_host": (client.base_url or "").split("/")[2],
        "has_key": bool(client.api_key),
    }
    t0 = time.monotonic()
    msg = client.chat([{"role": "user", "content": "Reply with the single word: pong"}], [])
    res["call"] = {
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "content_head": (msg.content or "")[:40],
        "tokens": dict(client.tokens_total),
        "reasoning_head": (getattr(msg, "reasoning", None) or "")[:40],
    }


try:
    probe_call()
except Exception as e:  # noqa: BLE001
    res["call_error"] = f"{type(e).__name__}: {e}"[:300]
    filled = load_dotenv_keys()
    res["dotenv_keys_filled"] = filled
    if filled:
        res["resolved_provider_after_dotenv"] = _resolve_provider_name(os.environ)
        try:
            probe_call()
            res.pop("call_error", None)
            res["call_ok_after_dotenv"] = True
        except Exception as e2:  # noqa: BLE001
            res["call_error_after_dotenv"] = f"{type(e2).__name__}: {e2}"[:300]

try:
    d = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True, text=True, timeout=60,
    )
    res["docker"] = {
        "rc": d.returncode,
        "server_version": (d.stdout or "").strip()[:40],
        "stderr_head": (d.stderr or "").strip()[:120],
    }
except Exception as e:  # noqa: BLE001
    res["docker"] = {"error": f"{type(e).__name__}: {e}"[:160]}

(OUT / "probe_coding.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=2))
