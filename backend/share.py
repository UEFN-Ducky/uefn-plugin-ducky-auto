"""Opt-in, anonymous usage for the UEFN Ducky site: what Ducky Auto routed, never who or what about.

Only the allow-listed numbers and fixed words below leave the PC. Never sent: prompts, chat keys,
keywords (which rule matched), error text, file paths, account, email, machine or project names.
"""

from __future__ import annotations

import re

ENDPOINT_PATH = "/api/v1/plugins/analytics/collect/events"
EVENT_NAME = "plugin_usage"
MAX_BATCH = 50  # the site's limit per request

_TASKS = {"planning", "coding", "modeling", "execution", "research", "writing", "quick", "general"}
_DECISIONS = {"first", "same", "switched", "kept", "stayed (tool step)", "kept (nothing else answered)"}
# Public gateways keep their name; anything else (a self-hosted URL gateway) is "other".
_GATEWAYS = {"anthropic", "openai", "gemini", "google", "spacexai", "kimi", "cursor", "ollama", "uefn_ducky", "opencode"}
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_INSTALL_ID = re.compile(r"^[0-9a-f]{32}$")


def error_kind(text: str) -> str:
    """A fixed word for an error; its text (which may hold paths or names) never leaves."""
    t = (text or "").lower()
    if not t:
        return ""
    for kind, rx in (("timeout", r"timed?\s?out"), ("rate_limit", r"\b429\b|rate.?limit|quota"),
                     ("auth", r"\b40[13]\b|unauthori|forbidden|api key|sign.?in|login"),
                     ("not_found", r"\b404\b|not.?found|no longer available"),
                     ("network", r"connection|network|unreachable|reset"),
                     ("server", r"\b50[0-9]\b|overload|unavailable|busy")):
        if re.search(rx, t):
            return kind
    return "other"


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _tokens(usage: dict) -> tuple[int, int, int]:
    u = {str(k).lower(): v for k, v in (usage or {}).items()}
    pick = lambda *names: _int(next((u[n] for n in names if n in u), 0))  # noqa: E731
    return (pick("input_tokens", "prompt_tokens", "prompt_token_count"),
            pick("output_tokens", "completion_tokens", "candidates_token_count"),
            pick("cache_read_input_tokens", "cached_tokens", "cache_read_tokens", "cached_input_tokens"))


def event_for(row: dict, *, version: str, install_id: str, custom_rules: bool) -> dict | None:
    """One site event for one logged step, or None when it can't be made safe."""
    if not _INSTALL_ID.match(install_id or ""):
        return None
    gateway = str(row.get("gateway") or "").lower()
    model = str(row.get("model") or "").lower()
    if gateway not in _GATEWAYS:
        gateway, model = "other", ""
    if gateway == "ollama" or not _MODEL_ID.match(model):
        model = "local" if gateway == "ollama" else ""  # local model names are the person's own
    tin, tout, tcached = _tokens(row.get("usage") or {})
    cost = row.get("cost_usd")
    props = {
        "plugin": "ducky-auto",
        "v": str(version)[:16],
        # A rule the person added has their own name: it only ever leaves as "custom".
        "task": row.get("task") if row.get("task") in _TASKS else "custom" if str(row.get("task") or "").startswith("my_") else "general",
        "decision": row.get("decision") if row.get("decision") in _DECISIONS else "",
        "gateway": gateway,
        "model": model,
        "context_k": _int(row.get("context_tokens")) // 10_000 * 10,  # 10k buckets
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_cached": tcached,
        "tool_calls": _int(row.get("tool_calls")),
        "failed_checks": len(row.get("failed") or []),
        "pick_skipped": bool(row.get("pick_skipped")),
        "thinking_dropped": bool(row.get("thinking_dropped")),
        "custom_rules": bool(custom_rules),
        "ms": _int(row.get("ms")),
        "first_token_ms": _int(row.get("first_token_ms")),
        "cost_usd": round(float(cost), 6) if isinstance(cost, (int, float)) else None,
        "error": error_kind(str(row.get("error") or "")),
    }
    return {"visitorId": install_id, "sessionId": "", "name": EVENT_NAME, "path": "/plugins/ducky-auto",
            "props": props}
