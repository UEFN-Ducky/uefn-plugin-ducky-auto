"""Run: py -3 -I backend/test_analytics.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from analytics import summary  # noqa: E402

OPUS = (5.0, 25.0, 0.5)
U = {"input_tokens": 100_000, "output_tokens": 1_000, "cache_read_tokens": 80_000}


def step(task: str, model: str, decision: str, *, error: str = "", cost=None, ctx=50_000, ms=2000) -> dict:
    return {"task": task, "gateway": "anthropic", "model": model, "decision": decision, "usage": U, "error": error,
            "cost_usd": cost, "context_tokens": ctx, "ms": ms, "first_token_ms": ms // 2, "tool_calls": 1}


def test_rates_effort_and_savings() -> None:
    rows = [step("coding", "haiku", "first", cost=0.03), step("coding", "haiku", "stayed (tool step)", cost=0.03),
            step("coding", "haiku", "kept", cost=0.03, ctx=120_000), step("quick", "haiku", "same", error="429", cost=0.03)]
    s = summary(rows, OPUS, "anthropic:opus")
    assert s["totals"]["errors"] == 1 and s["totals"]["error_rate"] == 0.25
    assert s["by_task"]["coding"]["error_rate"] == 0.0 and s["by_task"]["quick"]["error_rate"] == 1.0
    assert s["by_task"]["coding"]["avg_ms"] == 2000 and s["by_task"]["coding"]["avg_first_token_ms"] == 1000
    assert s["by_model"]["anthropic:haiku"]["error_rate"] == 0.25
    sv = s["savings"]
    assert sv["cache_share"] == 0.8 and sv["kept_reread_tokens"] == 120_000 and sv["stayed_tool_steps"] == 1
    # Each step on Opus uncached: 100k * $5 + 1k * $25 per 1M = $0.525; 4 steps = $2.10.
    assert sv["baseline_cost_usd"] == 2.1 and sv["actual_cost_usd"] == 0.12 and sv["saved_usd"] == 1.98


def test_no_prices_no_dollar_claims() -> None:
    s = summary([step("coding", "flash", "first")], None)
    assert s["savings"]["saved_usd"] is None and s["savings"]["baseline_cost_usd"] is None
    assert summary([], None)["totals"]["error_rate"] == 0.0


if __name__ == "__main__":
    test_rates_effort_and_savings()
    test_no_prices_no_dollar_claims()
    print("analytics ok")
