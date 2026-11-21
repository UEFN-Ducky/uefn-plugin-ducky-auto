"""Run: py -3 -I backend/test_tuner.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from tuner import suggest  # noqa: E402


def row(task="coding", model="flash", error="", failed=0, skipped="", ft=1000) -> dict:
    return {"task": task, "gateway": "gemini", "model": model, "error": error, "failed": [{}] * failed,
            "pick_skipped": skipped, "first_token_ms": ft}


def kinds(out: list[dict]) -> set[str]:
    return {s["kind"] for s in out}


def test_quiet_when_healthy_or_too_few_steps() -> None:
    assert suggest([row() for _ in range(10)], {}) == []
    assert suggest([row(error="500") for _ in range(4)], {}) == []  # 4 steps: too few to judge


def test_each_rule() -> None:
    errs = [row(error="429") for _ in range(3)] + [row() for _ in range(5)]  # 3 of 8 = 37 %
    out = suggest(errs, {})
    assert kinds(out) == {"high_error"} and out[0]["action"] == "replace" and "3 of its last 8" in out[0]["why"]

    picks = {"coding": "anthropic:claude-opus-5-5"}
    out = suggest([row(skipped="anthropic:claude-opus-5-5: no key") for _ in range(3)], picks)
    assert kinds(out) == {"pick_cant_run"}
    # Old steps that skipped a previous pick don't blame the new one.
    assert suggest([row(skipped="anthropic:claude-opus-5-5: no key") for _ in range(3)], {"coding": "gemini:flash"}) == []

    out = suggest([row(failed=17) for _ in range(6)], {})
    assert kinds(out) == {"slow_checks"} and out[0]["action"] == "pin"
    # A pick that can't run still makes every step probe: still worth pinning.
    opus = [row(failed=17, skipped="anthropic:opus: no key") for _ in range(6)]
    assert kinds(suggest(opus, {"coding": "anthropic:opus"})) == {"slow_checks", "pick_cant_run"}
    # Once pinned to a model that runs, the old probing steps stop counting.
    assert suggest(opus, {"coding": "gemini:flash"}) == []
    assert suggest([row(failed=0) for _ in range(6)], {"coding": "gemini:flash"}) == []  # a working pin

    out = suggest([row(ft=30_000) for _ in range(5)], {})
    assert kinds(out) == {"slow"} and out[0]["action"] == "info"


if __name__ == "__main__":
    test_quiet_when_healthy_or_too_few_steps()
    test_each_rule()
    print("tuner ok")
