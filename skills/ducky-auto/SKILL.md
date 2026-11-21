---
name: ducky-auto
description: Ducky Auto model router — its editable rules (task order, keywords, Auto tier, model per task), model checks, switch-cost rule, and routing analytics for troubleshooting
---

# Ducky Auto

Ducky Auto is an LLM gateway with no key of its own. Pick **Ducky Auto** in a chat's model
picker and every step goes to the model its rules choose. The chat shows `via <model>`
beside the ducky (Ducky builds with `routed_model` support).

The rules are edited in **Settings → LLMs → Ducky Auto** (or Settings → Plugins → Ducky Auto):
drag the rule cards to reorder, add/remove keyword chips, set each task's Auto tier, pick each
task's model with the app's model picker, and type in **Try a message** to see the result.

## How it decides (in order)

1. A step right after a tool returned is **Tool steps**: stays on the turn's model (Auto
   tier `stay`), unless a model or another tier is set for Tool steps.
2. Rules top to bottom; the first rule with a keyword in the latest user message wins.
   `word*` matches any ending (`plan*` = plan, planning). Default order: 3D modeling & art,
   Coding & Verse, Planning & design, Research, Writing, Quick questions.
3. No keyword: a question shorter than `short_question_chars` (90) is Quick; else Everything else.
4. The task's picked model runs it; on Auto the newest model of its tier (fast / balanced /
   best) from the gateways with a key. A pick whose gateway has no key is skipped (the
   panel says so on the card) and Auto runs instead.
5. Each model answers a one-word check first (kept 6 h; passing failures retried after
   30 min, dead ones after 24 h). Gateways with no key are never asked.
6. A chat moves to a cheaper model only when re-reading the whole chat there plus
   `steps_ahead` (3) steps costs less than staying (gateway prices; no prices → only under
   `small_context` tokens, 8000). Moving to a stronger tier always happens.

## Set it up for the person, then keep it tuned

When the person asks to set up / configure / optimise Ducky Auto:

1. `ducky_auto_setup()` — checks which models answer and pins one per task (best for planning,
   fast for quick questions, balanced for the rest; tool steps stay on the turn's model). Keeps
   models the person picked that still run (`keep_my_picks=False` replaces them too);
   `prefer_gateway="anthropic"` tries that gateway first; `apply=False` only shows the plan.
   Pinning also stops each step probing models that fail.
2. Later, `ducky_auto_tune()` reads the analytics and lists what to change (a model erroring
   on a task ≥30 % over ≥5 steps, a pick that can't run, steps slowed by failed checks, slow
   tasks); `ducky_auto_tune(apply=True)` makes the changes. Show the person what changed.
3. One task by hand: `ducky_auto_set_model(task, "gateway:model", why)` ("" = Auto);
   `ducky_auto_set_gateway("anthropic")` for the gateway Auto tries first.

Every change (by the person, an agent, setup or the tuner) is logged with before, after and
why: `ducky_auto_analytics()["adjustments"]` and Analytics → Changes in the panel.
Never turn on usage sharing for the person; only they do.

## Tools

- `ducky_auto_route(prompt)` — task, the rule that matched, where the model came from, the checked model.
- `ducky_auto_get_rules()` / `ducky_auto_save_rules(rules_patch)` / `ducky_auto_reset_rules()` (asks first).
  `rules_patch`: `order` (tasks), `keywords` ({task: [words]}), `auto_tier` ({task: fast|balanced|best|stay}),
  `short_question_chars`, `small_context`, `steps_ahead`. Models per task are the person's picks in the panel.
- `ducky_auto_check_routes()` — every task's model, checked.
- `ducky_auto_analytics(limit, chat)` / `ducky_auto_analytics_clear()` (asks first).

## Sharing anonymous usage (opt-in)

The **Share anonymous usage** toggle (top right of the Ducky Auto panel, off by default) sends
a stripped-down event per step to uefnducky.org's analytics (`plugin_usage`): task type,
decision, gateway and public model name (local models = "local", unknown gateways = "other"),
chat size in 10k buckets, token counts, time, number of failed checks, an error *type*, and a
random install id. Never: messages, keywords, chat keys, error text, paths, account, email or
PC names. Only the person turns it on; `ducky_auto_share_status()` shows its state and a
preview of exactly what one step sends.

## Troubleshooting (analytics)

`ducky_auto_analytics()` returns `summary` with `totals` (steps, `error_rate`, switches, kept,
stayed, failed checks, cost), `by_task` (steps, `error_rate`, `avg_ms`, `avg_first_token_ms`,
avg tokens in/out, tool calls per step), `by_model` (steps, `error_rate`, `avg_ms`, tokens, cost)
and `savings` (`cache_share` and cached tokens, `kept_reread_tokens` a switch would have
re-read, `stayed_tool_steps`, and — only when the gateways publish prices — `saved_usd` against
the priciest best-tier model you have); plus `adjustments` (the change log) and `steps`.

One row per step: `chat` key, `task`, `matched` (the rule), `model`, `decision`
(first / same / switched / kept / stayed), `why` / `note`, `pick_skipped`, `failed` (models
whose check failed and why), `context_tokens`, `usage`, `cost_usd`, `ms`, `first_token_ms`,
`tool_calls`, `error`. Prompt text is never stored.

Common answers: slow first step → many `failed` checks (fix keys or pick a model);
`kept` → the switch would have cost more; `pick_skipped` → the picked gateway has no key;
`error` → the routed gateway's own error.
