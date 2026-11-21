"""Order Auto's candidates by how they did before: pure rules, no host imports.

Each (task, model) gets a score from the step log: the chance a step succeeds (a Beta posterior
mean, so a model with few steps stays near the prior) minus a little for a slow first word.
Deterministic on purpose: a chat that flips models between steps loses its cache.
"""

from __future__ import annotations

PRIOR_OK = 4.0          # an unseen model counts as 4 good steps...
PRIOR_BAD = 1.0         # ...and 1 bad one (score 0.8)
SLOW_MS = 20_000        # first word slower than this costs up to...
SLOW_PENALTY = 0.15     # ...this much score


def scores(rows: list[dict], task: str) -> dict[str, float]:
    """"gateway:model" → score 0..1 for ``task`` from logged steps."""
    seen: dict[str, list[int]] = {}
    slow: dict[str, list[int]] = {}
    for r in rows:
        if str(r.get("task") or "") != task or not r.get("model"):
            continue
        key = f"{r.get('gateway', '')}:{r['model']}"
        ok_bad = seen.setdefault(key, [0, 0])
        ok_bad[1 if r.get("error") else 0] += 1
        if r.get("first_token_ms"):
            slow.setdefault(key, []).append(int(r["first_token_ms"]))
    out = {}
    for key, (ok, bad) in seen.items():
        score = (ok + PRIOR_OK) / (ok + bad + PRIOR_OK + PRIOR_BAD)
        times = slow.get(key)
        if times:
            avg = sum(times) / len(times)
            score -= SLOW_PENALTY * min(1.0, max(0.0, (avg - SLOW_MS / 2) / SLOW_MS))
        out[key] = round(score, 4)
    return out


def rank(cands: list[tuple[str, str]], rows: list[dict], task: str, keep_first: int = 0) -> list[tuple[str, str]]:
    """``cands`` best first by past results; the first ``keep_first`` (the person's pick) never move.
    Ties keep Auto's own order, so with no history nothing changes."""
    prior = PRIOR_OK / (PRIOR_OK + PRIOR_BAD)
    s = scores(rows, task)
    head, tail = cands[:keep_first], cands[keep_first:]
    order = {c: i for i, c in enumerate(tail)}
    tail = sorted(tail, key=lambda c: (-s.get(f"{c[0]}:{c[1]}", prior), order[c]))
    return head + tail
