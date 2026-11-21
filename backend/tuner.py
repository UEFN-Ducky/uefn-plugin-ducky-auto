"""Read the routing log and say what to change: pure rules, no host imports.

Each suggestion names the task, why (with the numbers), and an action the plugin can apply:
  replace  — pick another working model for this task (its model errors too often / can't run)
  pin      — run setup: pin a checked model per task so steps stop probing models that fail
  info     — worth knowing, nothing applied automatically (e.g. a slow task)
"""

from __future__ import annotations

from collections import defaultdict

MIN_STEPS = 5          # never judge a model or task on fewer steps
ERROR_RATE = 0.3       # this share of steps erroring → replace the model
SKIPPED_PICKS = 3      # a picked model skipped this often → replace it
FAILED_PER_STEP = 3.0  # average failed checks per step → pin working models
SLOW_FIRST_TOKEN_MS = 20_000


def skipped_pick(row: dict, pick: str) -> bool:
    """The step skipped ``pick`` (logged as "gateway:model: reason")."""
    return bool(pick) and str(row.get("pick_skipped") or "").startswith(pick + ":")


def suggest(rows: list[dict], picks: dict[str, str]) -> list[dict]:
    """``rows``: logged steps (oldest first); ``picks``: task → "gateway:model" ("" = Auto)."""
    out: list[dict] = []
    by_task_model: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        task = str(r.get("task") or "general")
        by_task_model[(task, f"{r.get('gateway', '')}:{r.get('model', '')}")].append(r)
        by_task[task].append(r)

    for (task, model), steps in sorted(by_task_model.items()):
        errs = sum(1 for s in steps if s.get("error"))
        if len(steps) >= MIN_STEPS and errs / len(steps) >= ERROR_RATE:
            out.append({"kind": "high_error", "task": task, "model": model, "action": "replace",
                        "why": f"{model} failed {errs} of its last {len(steps)} {task} steps"})

    for task, steps in sorted(by_task.items()):
        # Only the current pick counts: steps skipping an older pick say nothing about this one.
        skipped = sum(1 for s in steps if skipped_pick(s, picks.get(task, "")))
        if picks.get(task) and skipped >= SKIPPED_PICKS:
            out.append({"kind": "pick_cant_run", "task": task, "model": picks[task], "action": "replace",
                        "why": f"your pick {picks[task]} couldn't run in {skipped} {task} steps"})
        timed = [int(s["first_token_ms"]) for s in steps if s.get("first_token_ms")]
        if len(timed) >= MIN_STEPS and sum(timed) / len(timed) > SLOW_FIRST_TOKEN_MS:
            out.append({"kind": "slow", "task": task, "action": "info",
                        "why": f"{task} steps wait {sum(timed) // len(timed) // 1000}s on average for the first word; "
                               "a faster model or tier would answer sooner"})

    # A working pin is asked first and answers, so failed checks mean Auto (or a pick that can't
    # run) is probing models that fail: pinning a checked model per task skips them.
    # Tasks now pinned to a model that runs no longer probe, so their old rows don't count.
    def still_probes(r: dict) -> bool:
        pick = picks.get(str(r.get("task") or "general"))
        return not pick or skipped_pick(r, pick)
    live = [r for r in rows if still_probes(r)]
    if len(live) >= MIN_STEPS:
        failed = sum(len(r.get("failed") or []) for r in live) / len(live)
        tasks = sorted({str(r.get("task") or "general") for r in live if r.get("failed")})
        if failed >= FAILED_PER_STEP:
            out.append({"kind": "slow_checks", "task": ",".join(tasks), "action": "pin",
                        "why": f"each step checks {failed:.0f} models that don't answer before one that does; "
                               "pinning a checked model per task skips them"})
    return out
