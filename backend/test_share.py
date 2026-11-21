"""Run: py -3 -I backend/test_share.py — nothing personal may leave in a shared event."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from share import error_kind, event_for  # noqa: E402

ID = "0123456789abcdef0123456789abcdef"
ROW = {
    "chat": "aaf5c54579ed", "task": "coding", "base_task": "coding", "matched": 'matched "secretproject"',
    "context_tokens": 45_321, "messages": 9, "tools": 13, "previous": "gemini:gemini-3.8-flash",
    "failed": [{"gateway": "gemini", "model": "x", "why": "C:/Users/alice/key.txt"}],
    "gateway": "gemini", "model": "gemini-3.8-flash", "decision": "same", "note": "kept alice's model",
    "why": "cheaper", "wanted": "anthropic:claude-opus-5-5", "pick_skipped": "anthropic: no key for bob@example.com",
    "tool_calls": 3, "stop": "tool_calls", "usage": {"input_tokens": 55793, "output_tokens": 131, "cache_read_tokens": 0},
    "cost_usd": None, "ms": 3545, "first_token_ms": 3540,
    "error": "Couldn't open C:\\Users\\alice\\Documents\\Fortnite Projects\\MovieTheater: connection reset",
}


def test_only_allowed_fields_leave() -> None:
    ev = event_for(ROW, version="1.4.0", install_id=ID, custom_rules=True)
    text = json.dumps(ev)
    for secret in ("alice", "bob@", "example.com", "Users", "MovieTheater", "secretproject", "aaf5c54579ed",
                   "claude-opus", "key.txt", "kept alice"):
        assert secret not in text, secret
    p = ev["props"]
    assert set(p) == {"plugin", "v", "task", "decision", "gateway", "model", "context_k", "tokens_in", "tokens_out",
                      "tokens_cached", "tool_calls", "failed_checks", "pick_skipped", "thinking_dropped",
                      "custom_rules", "ms", "first_token_ms", "cost_usd", "error"}
    assert p["error"] == "network" and p["context_k"] == 40 and p["failed_checks"] == 1 and p["pick_skipped"] is True
    assert ev["name"] == "plugin_usage" and ev["visitorId"] == ID and len(text) < 4096


def test_custom_names_are_hidden() -> None:
    local = event_for({**ROW, "gateway": "ollama", "model": "alice-secret-model"}, version="1", install_id=ID,
                      custom_rules=False)
    assert local["props"]["model"] == "local"
    proxy = event_for({**ROW, "gateway": "my_company_proxy", "model": "x"}, version="1", install_id=ID,
                      custom_rules=False)
    assert proxy["props"]["gateway"] == "other" and proxy["props"]["model"] == ""
    odd = event_for({**ROW, "model": "Model With Spaces/alice"}, version="1", install_id=ID, custom_rules=False)
    assert odd["props"]["model"] == ""
    assert event_for(ROW, version="1", install_id="alice@example.com", custom_rules=False) is None
    mine = event_for({**ROW, "task": "my_alices_secret_game"}, version="1", install_id=ID, custom_rules=True)
    assert mine["props"]["task"] == "custom" and "alice" not in json.dumps(mine)


def test_error_kinds() -> None:
    assert error_kind("") == "" and error_kind("429 Too Many Requests") == "rate_limit"
    assert error_kind("404 NOT_FOUND models/x") == "not_found" and error_kind("Request timed out") == "timeout"
    assert error_kind("something odd at C:/Users/alice") == "other"


if __name__ == "__main__":
    test_only_allowed_fields_leave()
    test_custom_names_are_hidden()
    test_error_kinds()
    print("share ok")
