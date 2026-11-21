"""Routing log: one JSON line per Ducky Auto step, on this PC only (prompts never stored).

summary() turns it into what a person (or an agent tuning the rules) needs: error rates per
model and task, time and tokens per task, and what the routing saved.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict

_MAX_BYTES = 4 * 1024 * 1024  # ponytail: one rotated file; a real store if people need weeks of history


class StepLog:
    def __init__(self, folder: str) -> None:
        self.path = os.path.join(folder, "steps.jsonl")
        self._lock = threading.Lock()
        os.makedirs(folder, exist_ok=True)

    def add(self, row: dict) -> None:
        line = json.dumps({"ts": round(time.time(), 3), **row}, default=str)
        with self._lock:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) > _MAX_BYTES:
                    os.replace(self.path, self.path + ".1")
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass  # analytics never breaks a chat

    def rows(self, limit: int = 200, chat: str = "") -> list[dict]:
        out: list[dict] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not chat or row.get("chat") == chat:
                        out.append(row)
        except OSError:
            return []
        return out[-max(1, int(limit or 200)):]

    def clear(self) -> None:
        with self._lock:
            for p in (self.path, self.path + ".1"):
                try:
                    os.remove(p)
                except OSError:
                    pass


def tokens_of(usage: dict) -> tuple[int, int, int]:
    """(input, output, cached input) from any gateway's usage dict."""
    u = {str(k).lower(): v for k, v in (usage or {}).items() if isinstance(v, (int, float))}

    def pick(*names: str) -> int:
        return int(next((u[n] for n in names if n in u), 0))

    cached = pick("cache_read_input_tokens", "cached_tokens", "cache_read_tokens", "cached_input_tokens")
    return pick("input_tokens", "prompt_tokens", "prompt_token_count"), pick(
        "output_tokens", "completion_tokens", "candidates_token_count"), cached


def cost_usd(usage: dict, prices: tuple | None) -> float | None:
    """Estimated cost of one step; None when the gateway has no prices for the model."""
    if not prices or prices[0] is None or prices[1] is None:
        return None
    tin, tout, tcached = tokens_of(usage)
    p_in, p_out, p_cached = prices
    p_cached = p_in * 0.1 if p_cached is None else p_cached
    return round(((tin - tcached) * p_in + tcached * p_cached + tout * p_out) / 1_000_000, 6)


def _rate(bad: int, total: int) -> float:
    return round(bad / total, 3) if total else 0.0


def switch_audit(rows: list[dict], prices_of) -> dict:
    """Did each model switch actually pay for itself? Rows oldest first.

    A switch re-reads the chat on the new model (its uncached input on that step). From the switch
    until the chat moves again, each step's real cost is set against the same tokens on the model it
    left, with that step's input read from cache as staying would have (the old model's cache was warm).
    ``prices_of("gateway:model")`` → (in, out, cached_in) or None.
    """
    open_: dict[str, dict] = {}
    done: list[dict] = []  # in the order the switches happened
    for r in rows:
        chat = str(r.get("chat") or "")
        here = f"{r.get('gateway', '')}:{r.get('model', '')}"
        seg = open_.get(chat)
        if seg and (seg["model"] != here or r.get("decision") == "switched"):
            open_.pop(chat)
            seg = None
        if r.get("decision") == "switched" and r.get("previous"):
            tin, _out, tcached = tokens_of(r.get("usage") or {})
            seg = open_[chat] = {"chat": chat, "from": r["previous"], "model": here, "why": r.get("why", ""),
                                 "reread_tokens": max(0, tin - tcached), "steps": 0, "actual": 0.0,
                                 "stay": 0.0, "priced": True, "_old": prices_of(r["previous"])}
            done.append(seg)
        if not seg:
            continue
        u = r.get("usage") or {}
        tin, tout, tcached = tokens_of(u)
        # Step 1 on the old model would have been cached; later steps get the cache share it really had.
        stay_u = {"input_tokens": tin, "output_tokens": tout,
                  "cache_read_tokens": tin if seg["steps"] == 0 else tcached}
        stay = cost_usd(stay_u, seg["_old"])
        cost = r.get("cost_usd")
        seg["steps"] += 1
        if stay is None or not isinstance(cost, (int, float)):
            seg["priced"] = False
        else:
            seg["actual"] += cost
            seg["stay"] += stay
    out = []
    for s in done:
        s.pop("_old")
        s["net_usd"] = round(s["stay"] - s["actual"], 6) if s["priced"] else None
        s["actual"], s["stay"] = round(s["actual"], 6), round(s["stay"], 6)
        out.append(s)
    priced = [s for s in out if s["net_usd"] is not None]
    return {"switches": out, "count": len(out), "priced": len(priced),
            "paid_off": sum(1 for s in priced if s["net_usd"] > 0),
            "net_usd": round(sum(s["net_usd"] for s in priced), 6) if priced else None,
            "reread_tokens": sum(s["reread_tokens"] for s in out)}


def summary(rows: list[dict], baseline_prices: tuple | None = None, baseline_model: str = "",
            prices_of=None) -> dict:
    """Totals, per model, per task, savings and (with ``prices_of``) the switch audit.

    ``baseline_prices``: the best-quality model's prices; the same steps on it, with the same cache
    hits, is the "without Ducky Auto" figure. None = no dollar savings (no prices known).
    """
    by_model: dict[str, dict] = defaultdict(lambda: {"steps": 0, "errors": 0, "input": 0, "output": 0,
                                                       "cached": 0, "cost_usd": 0.0, "ms": 0})
    by_task: dict[str, dict] = defaultdict(lambda: {"steps": 0, "errors": 0, "input": 0, "output": 0,
                                                      "tool_calls": 0, "ms": 0, "first_token_ms": 0, "ft_n": 0})
    totals = {"steps": len(rows), "switches": 0, "kept": 0, "stayed": 0, "probe_failures": 0, "errors": 0,
              "cost_usd": 0.0, "priced_steps": 0}
    savings = {"cached_tokens": 0, "input_tokens": 0, "kept_reread_tokens": 0, "stayed_tool_steps": 0,
               "baseline_model": baseline_model, "baseline_cost_usd": None, "actual_cost_usd": None, "saved_usd": None}
    base_cost, actual_cost, priced = 0.0, 0.0, 0
    for r in rows:
        tin, tout, tcached = tokens_of(r.get("usage") or {})
        err = 1 if r.get("error") else 0
        m = by_model[f"{r.get('gateway', '')}:{r.get('model', '')}"]
        t = by_task[str(r.get("task") or "general")]
        for bucket in (m, t):
            bucket["steps"] += 1
            bucket["errors"] += err
            bucket["input"] += tin
            bucket["output"] += tout
            bucket["ms"] += int(r.get("ms") or 0)
        m["cached"] += tcached
        t["tool_calls"] += int(r.get("tool_calls") or 0)
        if r.get("first_token_ms"):
            t["first_token_ms"] += int(r["first_token_ms"])
            t["ft_n"] += 1
        cost = r.get("cost_usd")
        if isinstance(cost, (int, float)):
            m["cost_usd"] = round(m["cost_usd"] + cost, 6)
            totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
            totals["priced_steps"] += 1
        decision = str(r.get("decision") or "")
        totals["switches"] += decision == "switched"
        totals["kept"] += decision == "kept"
        totals["stayed"] += decision.startswith("stayed")
        totals["probe_failures"] += len(r.get("failed") or [])
        totals["errors"] += err
        savings["cached_tokens"] += tcached
        savings["input_tokens"] += tin
        if decision == "kept":
            savings["kept_reread_tokens"] += int(r.get("context_tokens") or 0)
        if decision.startswith("stayed"):
            savings["stayed_tool_steps"] += 1
        if baseline_prices and isinstance(cost, (int, float)):
            b = cost_usd(r.get("usage") or {}, baseline_prices)
            if b is not None:
                base_cost += b
                actual_cost += cost
                priced += 1
    for m in by_model.values():
        m["error_rate"] = _rate(m["errors"], m["steps"])
        m["avg_ms"] = m["ms"] // m["steps"] if m["steps"] else 0
    for t in by_task.values():
        n = t["steps"] or 1
        t["error_rate"] = _rate(t["errors"], t["steps"])
        t["avg_ms"] = t["ms"] // n
        t["avg_first_token_ms"] = t["first_token_ms"] // t["ft_n"] if t["ft_n"] else 0
        t["avg_input"] = t["input"] // n
        t["avg_output"] = t["output"] // n
        t["avg_tool_calls"] = round(t["tool_calls"] / n, 2)
        del t["ft_n"], t["first_token_ms"]
    totals["error_rate"] = _rate(totals["errors"], totals["steps"])
    savings["cache_share"] = _rate(savings["cached_tokens"], savings["input_tokens"])
    if priced:
        savings["baseline_cost_usd"] = round(base_cost, 6)
        savings["actual_cost_usd"] = round(actual_cost, 6)
        savings["saved_usd"] = round(base_cost - actual_cost, 6)
        savings["priced_steps"] = priced
    out = {"totals": totals, "by_model": dict(by_model), "by_task": dict(by_task), "savings": savings}
    if prices_of:
        out["switch_audit"] = switch_audit(rows, prices_of)
    return out
