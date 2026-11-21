"""Run: py -3 -I backend/test_learn.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from learn import rank, scores  # noqa: E402


def step(model: str, error: str = "", ms: int = 2000, task: str = "coding") -> dict:
    return {"task": task, "gateway": "g", "model": model, "error": error, "first_token_ms": ms}


def test_rank() -> None:
    cands = [("g", "mine"), ("g", "a"), ("g", "b"), ("g", "c")]
    rows = [step("a", "429")] * 4 + [step("a")] + [step("b")] * 6 + [step("c", ms=60_000)] * 6
    s = scores(rows, "coding")
    assert s["g:a"] < 0.8 < s["g:b"], s  # 4 of 5 errors drops below an unseen model's 0.8
    assert s["g:c"] < s["g:b"]  # slow first word costs score
    # The person's pick stays first; unseen "mine" doesn't matter. b, then c (slow but fine), then a.
    assert rank(cands, rows, "coding", keep_first=1) == [("g", "mine"), ("g", "b"), ("g", "c"), ("g", "a")]
    # Other tasks' steps don't count, and no history keeps Auto's own order.
    assert rank(cands, rows, "writing") == cands
    assert rank(cands, [], "coding") == cands


if __name__ == "__main__":
    test_rank()
    print("learn ok")
