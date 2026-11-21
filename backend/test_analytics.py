"""Run: py -3 -I backend/test_analytics.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from analytics import summary, switch_audit  # noqa: E402

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
    # Each step on Opus with the same cache hits: 20k * $5 + 80k * $0.5 + 1k * $25 per 1M = $0.165.
    assert sv["baseline_cost_usd"] == 0.66 and sv["actual_cost_usd"] == 0.12 and sv["saved_usd"] == 0.54


def test_no_prices_no_dollar_claims() -> None:
    s = summary([step("coding", "flash", "first")], None)
    assert s["savings"]["saved_usd"] is None and s["savings"]["baseline_cost_usd"] is None
    assert summary([], None)["totals"]["error_rate"] == 0.0


def test_switch_audit() -> None:
    """A switch counts as paid off only when its steps cost less than staying cached on the old model."""
    prices = {"a:opus": OPUS, "a:haiku": (1.0, 5.0, 0.1)}
    cold = {"input_tokens": 100_000, "output_tokens": 1_000, "cache_read_tokens": 0}
    warm = {"input_tokens": 100_000, "output_tokens": 1_000, "cache_read_tokens": 95_000}

    def row(model, decision, usage, cost, chat="c1", previous=""):
        return {"chat": chat, "gateway": "a", "model": model, "decision": decision, "usage": usage,
                "cost_usd": cost, "previous": previous}

    rows = [row("opus", "first", cold, 0.525),
            # haiku re-reads 100k uncached ($0.105), then 2 cached steps ($0.0195 each).
            row("haiku", "switched", cold, 0.105, previous="a:opus"),
            row("haiku", "same", warm, 0.0195), row("haiku", "same", warm, 0.0195),
            # A second chat: one step on haiku right after a switch, then back to opus.
            row("haiku", "switched", cold, 0.105, chat="c2", previous="a:opus"),
            row("opus", "switched", warm, 0.07, chat="c2", previous="a:haiku")]
    a = switch_audit(rows, prices.get)
    assert a["count"] == 3 and a["reread_tokens"] == 205_000, a
    c1 = a["switches"][0]
    # Staying on opus: step 1 all cached 100k*0.5+1k*25 = $0.075; steps 2-3 = 5k*5+95k*0.5+1k*25 = $0.0975 each.
    assert c1["chat"] == "c1" and c1["steps"] == 3 and c1["stay"] == 0.27 and c1["actual"] == 0.144
    assert c1["net_usd"] == 0.126
    c2 = a["switches"][1]
    assert c2["steps"] == 1 and c2["net_usd"] == round(0.075 - 0.105, 6)  # lost money: left too soon
    # Back to opus: staying on haiku cached = $0.015 vs $0.07 actual.
    assert a["switches"][2]["net_usd"] == -0.055
    assert a["paid_off"] == 1 and a["priced"] == 3 and a["net_usd"] == round(0.126 - 0.03 - 0.055, 6)
    assert switch_audit(rows, lambda _r: None)["net_usd"] is None  # no prices, no dollar claim


if __name__ == "__main__":
    test_rates_effort_and_savings()
    test_switch_audit()
    test_no_prices_no_dollar_claims()
    print("analytics ok")
