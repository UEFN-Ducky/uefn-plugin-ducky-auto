"""Ducky Auto: an LLM gateway that hands each step to the model set for its task.

The rules (task order, keywords, Auto tier per task, model per task, cost numbers) are the
person's, edited in Settings → LLMs → Ducky Auto (ui/settings.js draws that page in the provider's
ducky:llm-slot). A model is used only after it answered a tiny
check prompt, a chat moves to another model only when that is cheaper than staying (the new model
re-reads the whole chat uncached), and every step is logged (this PC only, never prompt text).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import re
import threading
import time
import uuid

from .analytics import StepLog, cost_usd, summary, tokens_of
from .learn import rank as learned_order
from .share import ENDPOINT_PATH, MAX_BATCH, event_for
from .tuner import suggest
from .router import (
    TASKS, TIER_RANK, all_tasks, cache_rules, custom_id, explain_task, fits_window, login_offering, merged_rules,
    parse_route, pick_tier, rank_tier, tier_count, tier_of, worth_switching,
)

SELF = "ducky_auto"
MODEL_ID = "ducky-auto"
VERSION = "1.14.1"
_SHARE_EVERY = 10  # steps per upload
_SHARE_MAX_WAIT_S = 300.0  # or this long after the first one waiting
_SHARE_QUEUE_MAX = 200  # offline: keep at most this many, oldest dropped
_MODELS_TTL_S = 600.0
_HEALTH_OK_TTL_S = 6 * 3600.0
_HEALTH_BAD_TTL_S = 1800.0  # a passing failure (timeout, rate limit, network): ask again soon
_HEALTH_DEAD_TTL_S = 24 * 3600.0  # 404 / not allowed / wrong API: ask again tomorrow
_PASSING = re.compile(r"time[d ]?out|connection|network|\b429\b|rate.?limit|quota|\b50[0-9]\b|overload|busy|unavailable", re.I)
_PROBE_TIMEOUT_S = 30.0
_PER_GATEWAY = 3  # Auto candidates tried per tier on each gateway
_TIER_WORDS = {"fast": "the newest fast model", "balanced": "the newest balanced model",
               "best": "the newest best-quality model", "stay": "the model the turn started on"}


def register(api) -> None:
    from backend.agent.model_fetch import ModelInfo
    from backend.agent.providers.base import ProviderMessage, StreamEvent, StreamEventKind

    log = StepLog(api.local_dir("analytics"))
    model_cache: dict[str, tuple[float, list[str]]] = {}
    health: dict[tuple[str, str], tuple[float, bool, str]] = {}
    # ponytail: chat identity = hash of the system prompt head + first message; the factory
    # gets no conv_id. Upgrade to conv_id if make_provider ever passes it on.
    chat_model: dict[str, tuple[str, str]] = {}
    lock = threading.Lock()

    def _identity_current():
        """The chat this step runs for (bound by the agent runner; None outside a chat)."""
        try:
            from backend.workspace import identity

            return identity.current()
        except Exception:
            return None

    def routed_status(text: str, routed: str):
        """STATUS naming the model (Ducky 1.2.4xx+ shows it beside the ducky); older apps: text only."""
        try:
            return StreamEvent(kind=StreamEventKind.STATUS, text=text, routed_model=routed)
        except TypeError:
            return StreamEvent(kind=StreamEventKind.STATUS, text=text)

    def settings() -> dict:
        try:
            from frontend.ui_web.plugin_host_api import prefs_plugin_get

            return dict(prefs_plugin_get(api.plugin_id) or {})
        except Exception:
            return {}

    def rules() -> dict:
        try:
            return merged_rules(api.data.get("rules"))
        except Exception:
            return merged_rules(None)

    def routes_doc() -> dict:
        """The model per task ("gateway:model", "" = Auto) and the gateway Auto tries first.
        One record the panel, agents and the tuner all read and write."""
        doc = api.data.get("routes")
        if isinstance(doc, dict):
            return doc
        s = settings()  # 1.0–1.5 kept picks in Settings prefs: carry them over once
        doc = {"name": "Ducky Auto models per task", "gateway": str(s.get("gateway") or "")}
        for t in TASKS:
            g, m = parse_route(str(s.get(f"route_{t}") or ""))
            doc[t] = f"{g}:{m}" if g and m else ""
        try:
            api.data.put("routes", doc)
        except Exception:
            pass
        return doc

    def config() -> dict:
        d = routes_doc()
        return {"gateway": str(d.get("gateway") or ""), **{f"route_{t}": str(d.get(t) or "") for t in all_tasks(rules())}}

    cred_cache: dict[str, tuple[float, str]] = {}

    def credential(gateway: str) -> str:
        # ponytail: 30 s cache; a key added in Settings shows up within that.
        hit = cred_cache.get(gateway)
        if hit and time.time() - hit[0] < 30:
            return hit[1]
        from backend.uefn_plugins.plugin_host.gateways import resolve_gateway_credential

        try:
            key = resolve_gateway_credential(gateway)
        except Exception:
            key = ""
        cred_cache[gateway] = (time.time(), key)
        return key

    def gateways() -> list[str]:
        """Gateways that can answer: a key, a sign-in or a local URL (no key = skipped, never probed)."""
        from backend.agent.providers import gateway_providers

        return [g for g in gateway_providers() if g != SELF and credential(g)]

    def models_of(gateway: str) -> list[str]:
        hit = model_cache.get(gateway)
        if hit and time.time() - hit[0] < _MODELS_TTL_S:
            return hit[1]
        from backend.agent.model_fetch import fetch_models

        try:
            ids = [m.id for m in fetch_models(gateway, credential(gateway))]
        except Exception:
            ids = []
        model_cache[gateway] = (time.time(), ids)
        return ids

    def model_info(gateway: str, model: str):
        from backend.agent.model_fetch import get_model_info

        try:
            return get_model_info(gateway, model)
        except Exception:
            return None

    def prices(gateway: str, model: str) -> tuple | None:
        info = model_info(gateway, model)
        if info is None:
            return None
        return (info.price_in, info.price_out, info.price_cached_in)

    def cache_of(gateway: str, model: str) -> dict:
        info = model_info(gateway, model)
        return cache_rules(gateway, getattr(info, "price_in", None), getattr(info, "price_cache_write", None))

    def window_of(gateway: str, model: str) -> int | None:
        return getattr(model_info(gateway, model), "context_limit", None)

    recent: dict = {"t": 0.0, "rows": []}

    def recent_rows() -> list[dict]:
        """The last 500 logged steps, read at most once a minute (learning and cache hit rates)."""
        if time.time() - recent["t"] > 60:
            recent.update(t=time.time(), rows=log.rows(limit=500))
        return recent["rows"]

    def hit_rate(gateway: str, model: str) -> float:
        """Share of input this model really read from cache lately; 0.9 until it has 3 steps."""
        tin = tcached = n = 0
        for r in recent_rows():
            if r.get("gateway") == gateway and r.get("model") == model:
                i, _o, c = tokens_of(r.get("usage") or {})
                tin, tcached, n = tin + i, tcached + c, n + 1
        return round(tcached / tin, 3) if n >= 3 and tin else 0.9

    # (chat, gateway, model) → when that model last ran a step of the chat: its cache is warm until
    # the gateway's cache timer runs out.
    last_used: dict[tuple[str, str, str], float] = {}

    def warmth(chat: str, gateway: str, model: str, ctx: int) -> tuple[float, float]:
        """(share of the chat the model reads from cache now, seconds since it last ran here)."""
        idle = time.time() - last_used.get((chat, gateway, model), 0.0)
        rule = cache_of(gateway, model)
        if idle > rule["ttl_s"] or ctx < rule["min_prefix"]:
            return 0.0, idle
        return hit_rate(gateway, model), idle

    def build(gateway: str, model: str, effort: str = "off"):
        from backend.uefn_plugins.plugin_host.gateways import get_llm_provider_registration

        reg = get_llm_provider_registration(gateway) or {}
        factory = reg.get("factory")
        if not callable(factory):
            raise ValueError(f"{gateway} gateway is not loaded")
        key = credential(gateway)
        try:
            return factory(key, model, thinking_effort=effort)
        except TypeError:
            return factory(key, model)

    async def probe(gateway: str, model: str) -> tuple[bool, str]:
        """One tiny prompt; True when the model answered. Cached so each model is asked rarely."""
        hit = health.get((gateway, model))
        if hit:
            ttl = _HEALTH_OK_TTL_S if hit[1] else _HEALTH_BAD_TTL_S if _PASSING.search(hit[2]) else _HEALTH_DEAD_TTL_S
            if time.time() - hit[0] < ttl:
                return hit[1], hit[2]
        ok, detail = False, "no answer"
        try:
            inner = build(gateway, model)

            async def ask() -> tuple[bool, str]:
                got = ""
                async for ev in inner.stream_turn(
                    system="Reply with the single word OK.",
                    messages=[ProviderMessage(role="user", content="OK?")],
                    tools=[],
                ):
                    if ev.kind == StreamEventKind.ERROR:
                        return False, str(ev.error or "error")[:200]
                    if ev.kind == StreamEventKind.TEXT_DELTA:
                        got += ev.text or ""
                return bool(got.strip()), "answered" if got.strip() else "empty answer"

            ok, detail = await asyncio.wait_for(ask(), _PROBE_TIMEOUT_S)
        except asyncio.TimeoutError:
            detail = "timed out"
        except Exception as exc:
            detail = str(exc)[:200]
        health[(gateway, model)] = (time.time(), ok, detail)
        return ok, detail

    def picked(s: dict, task: str) -> tuple[str, str]:
        g, m = parse_route(str(s.get(f"route_{task}") or ""))
        return (g, m) if g and g != SELF and m else ("", "")

    def candidates(task: str, s: dict, r: dict, ctx: int = 0) -> list[tuple[str, str]]:
        """The person's model for this task first (when set), then Auto's ranked picks, ordered by how
        they did before when Learn from results is on. Models whose window can't hold the chat are left out."""
        out: list[tuple[str, str]] = []
        gateway, model = picked(s, task)
        if gateway and gateway in gateways():
            models_of(gateway)  # loads its prices
            out.append((gateway, model))
        mine = len(out)
        tier = r["auto_tier"].get(task, "balanced")
        tier = "balanced" if tier == "stay" else tier
        wanted = str(s.get("gateway") or "").strip().lower()
        ranked = sorted(gateways(), key=lambda g: -tier_count(models_of(g)))
        for g in ([wanted] if wanted in ranked else []) + [g for g in ranked if g != wanted]:
            out += [(g, m) for m in rank_tier(models_of(g), tier, _PER_GATEWAY) if (g, m) not in out]
        if ctx:
            out = [c for c in out if fits_window(ctx, window_of(*c))]
            mine = min(mine, len(out)) if out[:1] == [(gateway, model)] else 0
        if r.get("learn"):
            out = learned_order(out, recent_rows(), task, keep_first=mine)
        return out

    async def first_healthy(task: str, s: dict, r: dict, ctx: int = 0) -> tuple[str, str, str, list[dict]]:
        """(gateway, model, note, failed); gateway "" when nothing answered."""
        failed: list[dict] = []
        for g, m in await asyncio.to_thread(candidates, task, s, r, ctx):
            ok, detail = await probe(g, m)
            if ok:
                return g, m, f"skipped {len(failed)} that didn't answer" if failed else "", failed
            failed.append({"gateway": g, "model": m, "why": detail[:160]})
        last = failed[-1] if failed else None
        why = f"{last['gateway']}:{last['model']} said {last['why']}" if last else "no gateway has models"
        return "", "", f"no model answered the check ({len(failed)} tried; last {why})", failed

    def chat_key(system: str, messages: list) -> str:
        first = str(getattr(messages[0], "content", "") or "")[:1000] if messages else ""
        return hashlib.sha1((str(system or "")[:4000] + "\n" + first).encode("utf-8", "ignore")).hexdigest()[:12]

    def context_tokens(system: str, messages: list) -> int:
        return (len(system or "") + sum(len(getattr(m, "content", "") or "") for m in messages)) // 4

    def last_user_text(messages: list) -> str:
        for m in reversed(messages or []):
            if getattr(m, "role", "") == "user":
                return str(getattr(m, "content", "") or "")
        return ""

    def stays_on_turn_model(s: dict, r: dict) -> bool:
        return not picked(s, "execution")[0] and r["auto_tier"].get("execution", "stay") == "stay"

    class AutoProvider:
        def __init__(self, thinking_effort: str = "off") -> None:
            self.thinking_effort = thinking_effort

        async def stream_turn(self, *, system, messages, tools, cancel_event=None, cache=None):
            started = time.time()
            messages = list(messages or [])
            s = await asyncio.to_thread(config)
            r = await asyncio.to_thread(rules)
            last_role = getattr(messages[-1], "role", "user") if messages else "user"
            key = chat_key(system, messages)
            ctx = context_tokens(system, messages)
            base_task, base_why = explain_task(last_user_text(messages), "user", r, context_tokens=ctx)
            task = "execution" if last_role == "tool" else base_task
            with lock:
                current = chat_model.get(key)
            row: dict = {"chat": key, "task": task, "base_task": base_task, "matched": base_why,
                         "context_tokens": ctx, "messages": len(messages), "tools": len(tools or []),
                         "previous": f"{current[0]}:{current[1]}" if current else "", "failed": []}

            note, decision = "", "first" if not current else "same"
            # A turn whose task is picked on a login (Claude Code…) runs there whole: a login is an
            # agent that runs its own steps, not an API that answers one step at a time.
            login = await asyncio.to_thread(login_pick, s, base_task) if last_role == "user" else None
            conv_id = getattr(_identity_current(), "conv_id", "") if login else ""
            if login and conv_id and time.time() - handed.get(conv_id, 0) > 60:
                agent, model = login
                handed[conv_id] = time.time()
                from backend.agent.run_context import current_mode

                hand_off(conv_id, agent, model, current_mode(), efforts().get(base_task, ""))
                where = f"{agent_label(agent)} · {model}"
                log.add({**row, "gateway": agent, "model": model, "decision": f"handed to {agent}",
                         "ms": int((time.time() - started) * 1000)})
                yield routed_status(f"🦆 Ducky Auto → {where} ({task})", f"{agent}:{model}")
                yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=f"Ducky Auto: this turn runs on {where}.")
                yield StreamEvent(kind=StreamEventKind.DONE, stop_reason="end_turn")
                return
            if task == "execution" and stays_on_turn_model(s, r) and current:
                gateway, model = current  # tool steps stay on the turn's model, its cache warm
                decision = "stayed (tool step)"
            else:
                route_task = task if task != "execution" or not stays_on_turn_model(s, r) else base_task
                pg, pm = picked(s, route_task)
                if pg and (blocked := pick_problem(pg, pm)):
                    row["pick_skipped"] = f"{pg}:{pm}: {blocked}"
                gateway, model, note, row["failed"] = await first_healthy(route_task, s, r, ctx)
                if not gateway and current:
                    gateway, model, decision = current[0], current[1], "kept (nothing else answered)"
                if not gateway:
                    err = f"Ducky Auto: {note}. Pick a model under Settings → LLMs → Ducky Auto."
                    log.add({**row, "error": err, "ms": int((time.time() - started) * 1000)})
                    yield StreamEvent(kind=StreamEventKind.ERROR, error=err)
                    return
                if current and current != (gateway, model) and decision == "same":
                    upgrade = TIER_RANK[tier_of(model)] > TIER_RANK[tier_of(current[1])]
                    target = (gateway, model)
                    stay_warm, idle = warmth(key, *current, ctx)
                    new_warm, _ = warmth(key, *target, ctx)
                    row.update(stay_warm=stay_warm, new_warm=new_warm)
                    if await asyncio.to_thread(
                        lambda: worth_switching(
                            ctx, prices(*current), prices(*target), upgrade=upgrade, steps=r["steps_ahead"],
                            small_context=r["small_context"], stay_warm=stay_warm, new_warm=new_warm,
                            stay_write=cache_of(*current)["write"], new_write=cache_of(*target)["write"],
                            hit=hit_rate(*target))
                    ):
                        decision = "switched"
                        row["why"] = ("upgrade for quality" if upgrade
                                      else f"{current[1]}'s cache had gone cold ({int(idle // 60)} min idle)" if not stay_warm
                                      else f"{model}'s cache was still warm" if new_warm
                                      else "cheaper even after re-reading the chat")
                    else:
                        decision = "kept"
                        row["wanted"] = f"{gateway}:{model}"
                        note = f"kept {current[1]}: re-reading {ctx // 1000}k tokens on {model} costs more"
                        gateway, model = current

            effort = (await asyncio.to_thread(efforts)).get(task) or self.thinking_effort
            if current and current != (gateway, model) and any(getattr(m, "thinking_blocks", None) for m in messages):
                # Signed thinking from another model can't be replayed: drop it, and thinking for this step.
                messages = [dataclasses.replace(m, thinking_blocks=[]) for m in messages]
                effort = "off"
                row["thinking_dropped"] = True
            with lock:
                chat_model[key] = (gateway, model)
                last_used[(key, gateway, model)] = time.time()
            row.update({"gateway": gateway, "model": model, "decision": decision, "note": note})
            yield routed_status(f"🦆 Ducky Auto → {model} ({task})" + (f" · {note}" if note else ""),
                                f"{gateway}:{model}")
            usage: dict = {}
            first_token = None
            try:
                inner = build(gateway, model, effort)
                async for event in inner.stream_turn(
                    system=system, messages=messages, tools=tools, cancel_event=cancel_event, cache=cache
                ):
                    if first_token is None and event.kind in (StreamEventKind.TEXT_DELTA, StreamEventKind.TOOL_CALLS):
                        first_token = time.time()
                    if getattr(event, "usage", None):
                        usage = dict(event.usage)
                    if event.kind == StreamEventKind.TOOL_CALLS:
                        row["tool_calls"] = row.get("tool_calls", 0) + len(event.tool_calls or [])
                    if event.kind == StreamEventKind.ERROR:
                        row["error"] = str(event.error or "")[:300]
                    if event.kind == StreamEventKind.DONE:
                        row["stop"] = event.stop_reason
                    yield event
            except Exception as exc:
                row["error"] = str(exc)[:300]
                yield StreamEvent(kind=StreamEventKind.ERROR, error=f"Ducky Auto: {exc}")
            finally:
                row["usage"] = usage
                row["cost_usd"] = cost_usd(usage, prices(gateway, model))
                row["ms"] = int((time.time() - started) * 1000)
                row["first_token_ms"] = int((first_token - started) * 1000) if first_token else None
                log.add(row)
                share_step(row)

        async def test_connection(self):
            g, m, note, _failed = await first_healthy("general", config(), rules())
            if not g:
                return False, f"Ducky Auto: {note}."
            return True, f"Ready: everyday turns go to {m} on {g}."

    def factory(_key: str, _model: str, thinking_effort: str = "off", **_kw):
        return AutoProvider(thinking_effort)

    def fetch(_key: str = "", **_kw) -> list:
        return [ModelInfo(id=MODEL_ID, display_name="Ducky Auto", supports_tools=True, supports_vision=True)]

    # No key of its own: billing="account" hides the API key table, and normalize_secret hands the
    # host a fixed non-secret credential so chats count it as connected. Each step is paid by the
    # gateway it is routed to.
    api.register_llm_provider(
        SELF, factory, fetch_models=fetch, key_optional=True, test_key_model=MODEL_ID, model_ids=[MODEL_ID],
        billing="account", normalize_secret=lambda _raw="": "ducky-auto",
    )

    def run(coro, default=("", "", "timed out", [])):
        """Run a coroutine from a sync tool/RPC, whether or not this thread has a loop."""
        box: dict = {}
        t = threading.Thread(target=lambda: box.setdefault("r", asyncio.run(coro)), daemon=True)
        t.start()
        t.join(_PROBE_TIMEOUT_S * 6)
        return box.get("r", default)

    def explain(prompt: str = "", check: bool = True) -> dict:
        """Which task a message is, why, and the model it goes to, in plain words."""
        if not str(prompt or "").strip():
            return {"ok": False, "error": "Type a message to try."}
        s, r = config(), rules()
        task, why = explain_task(prompt, "user", r)
        pg, pm = picked(s, task)
        tier = r["auto_tier"].get(task, "balanced")
        auto_words = f"Auto: {_TIER_WORDS.get(tier if tier != 'stay' else 'balanced', tier)}"
        blocked = pick_problem(pg, pm)
        source = (f"your pick ({pm}) can't run here: {blocked}, so {auto_words}" if blocked
                  else f"your pick for this task ({pm})" if pg else auto_words)
        out = {"ok": True, "task": task, "why": why, "source": source, "picked": f"{pg}:{pm}" if pg else ""}
        if lp := login_pick(s, task):
            return {**out, "source": f"your pick, on your {agent_label(lp[0])} login (the whole turn runs there)",
                    "gateway": lp[0], "model": lp[1], "note": "", "failed": []}
        if check:
            g, m, note, failed = run(first_healthy(task, s, r))
            if pg and not blocked and (g, m) != (pg, pm):
                out["source"] = f"your pick ({pm}) didn't answer its check, so {auto_words}"
            out.update({"gateway": g, "model": m, "note": note, "failed": failed[:8]})
            if not g:
                out["ok"] = False
                out["error"] = f"Ducky Auto: {note}."
        return out

    # --- Logins (Claude Code, Codex, Cursor…): most people pay through one, not an API key ----------
    def agent_of(gateway: str) -> str:
        """The coding-agent id when a pick's prefix names one (claude_code:…), else ""."""
        try:
            from backend.agent.coding_agents.base import normalize_coding_agent

            aid = normalize_coding_agent(gateway)
        except Exception:
            return ""
        return aid if aid != "ducky" and aid == gateway else ""

    ready_cache: dict[str, tuple[float, bool]] = {}

    def agent_ready(aid: str) -> bool:
        # detect() can start the agent's CLI; the panel and every turn ask, so keep the answer a minute.
        hit = ready_cache.get(aid)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        ok = agent_ready_now(aid)
        ready_cache[aid] = (time.time(), ok)
        return ok

    def agent_ready_now(aid: str) -> bool:
        # The app's own cached detect (Settings → LLMs reads the same): never starts a CLI.
        try:
            from backend.agent.coding_agents import detect_all

            for a in (detect_all() or {}).get("agents") or []:
                if a.get("id") == aid:
                    return bool(a.get("enabled") and a.get("available") and a.get("logged_in") is not False)
        except Exception:
            pass
        try:
            from backend.agent.coding_agents.base import get_adapter
            from frontend.settings import PanelSettings

            adapter = get_adapter(aid)
            info = adapter.detect(PanelSettings.load()) if adapter is not None else None
            return bool(info and info.enabled and info.available)
        except Exception:
            return False

    def agent_models(aid: str) -> list[str]:
        try:
            from backend.agent.coding_agents import detect_all  # cached: no CLI start here

            row = next((a for a in (detect_all() or {}).get("agents") or [] if a.get("id") == aid), {})
            return [str(m.get("id")) for m in row.get("models") or [] if isinstance(m, dict)]
        except Exception:
            return []

    def login_for(gateway: str, model: str = "") -> str:
        """A signed-in coding agent from the gateway's own plugin (Claude Code for Anthropic) that
        offers ``model``: Google has two (Gemini CLI, Antigravity) with different model names."""
        try:
            from backend.agent.coding_agents.base import listed_external_coding_agents
            from backend.uefn_plugins.plugin_host.gateways import (
                get_coding_agent_registration, get_llm_provider_registration,
            )

            pid = (get_llm_provider_registration(gateway) or {}).get("plugin_id")
            ready = [(a, agent_models(a)) for a in listed_external_coding_agents()
                     if pid and (get_coding_agent_registration(a) or {}).get("plugin_id") == pid and agent_ready(a)]
            return login_offering(ready, model)
        except Exception:
            return ""

    def login_pick(s: dict, task: str) -> tuple[str, str] | None:
        """(agent, model) when this task's pick runs on a login: picked under a coding agent, or under
        a gateway with no API key whose plugin's agent is signed in. None = an API runs it."""
        g, m = picked(s, task)
        if not g:
            return None
        if aid := agent_of(g):
            return (aid, m) if agent_ready(aid) else None
        if credential(g):
            return None
        aid = login_for(g, m)
        return (aid, m) if aid else None

    def agent_label(aid: str) -> str:
        return aid.replace("_", " ").title()

    handed: dict[str, float] = {}  # chat id → when its turn went to a login

    def hand_off(conv_id: str, agent: str, model: str, mode: str, effort: str = "") -> None:
        """Run this chat's turn on the login, then put the chat back on Ducky Auto. The chat's own
        turn ends first (its save would undo the switch); the turn resumes from the person's message."""
        from frontend.ui_web.agent_turns.routing import run_message
        from frontend.ui_web.agent_turns.state import is_agent_running
        from frontend.ui_web.chats.conversations import load_conversation
        from frontend.ui_web.chats.saves import save_conversation

        def wait(running: bool, limit_s: float) -> None:
            end = time.time() + limit_s
            while is_agent_running(conv_id) is running and time.time() < end:
                time.sleep(0.5)

        def go() -> None:
            try:
                wait(True, 120)  # this Ducky Auto turn closes
                conv = load_conversation(conv_id)
                if conv is None:
                    return
                chat_effort = getattr(conv, "thinking_effort", "")
                conv.coding_agent, conv.model, conv.provider = agent, model, SELF
                if effort:
                    conv.thinking_effort = effort
                save_conversation(conv)
                run_message(conv_id, "", mode, model, resume=True, queue_if_busy=True)
                wait(False, 30)  # it starts
                wait(True, 6 * 3600)  # it ends
                conv = load_conversation(conv_id)
                # ponytail: a Ducky restart mid-turn leaves the chat on the login; picking Ducky Auto again fixes it.
                if conv is not None and conv.coding_agent == agent and conv.model == model:
                    conv.coding_agent, conv.model, conv.provider = "ducky", MODEL_ID, SELF
                    if effort:
                        conv.thinking_effort = chat_effort
                    save_conversation(conv)
            except Exception as exc:
                api.log(f"Ducky Auto hand-off to {agent} failed: {exc}")

        threading.Thread(target=go, daemon=True, name="ducky-auto-handoff").start()

    def pick_problem(gateway: str, model: str = "") -> str:
        """Why a picked model's gateway can't run here ("" = it can)."""
        if not gateway:
            return ""
        if aid := agent_of(gateway):
            return "" if agent_ready(aid) else f"{agent_label(aid)} isn't installed or signed in"
        if not credential(gateway) and login_for(gateway, model):
            return ""  # runs on the person's login
        from backend.agent.providers import gateway_providers

        if gateway not in gateway_providers():
            return f"the {gateway} gateway isn't installed or is turned off"
        if not credential(gateway):
            return f"{gateway} has no API key or sign-in here"
        return ""

    def route_for(prompt: str = "") -> dict:
        out = explain(prompt)
        if out.get("ok"):
            out["route"] = {k: out.get(k) for k in ("task", "why", "source", "gateway", "model", "note")}
        return out

    def check_routes() -> dict:
        s, r = config(), rules()
        rows, lines = [], []
        for task in all_tasks(r):
            if task == "execution" and stays_on_turn_model(s, r):
                rows.append({"task": task, "picked": "", "model": "same as the turn", "ok": True})
                continue
            if lp := login_pick(s, task):
                note = f"the whole turn runs on your {agent_label(lp[0])} login"
                rows.append({"task": task, "picked": f"{lp[0]}:{lp[1]}", "gateway": lp[0], "model": lp[1],
                             "ok": True, "note": note, "failed": []})
                lines.append(f"{task}: {lp[1]} ({note})")
                continue
            g, m, note, failed = run(first_healthy(task, s, r))
            pg, pm = picked(s, task)
            rows.append({"task": task, "picked": f"{pg}:{pm}" if pg else "", "gateway": g, "model": m,
                         "ok": bool(g), "note": note, "failed": failed[:8]})
            lines.append(f"{task}: {m or 'none'}{' (' + note + ')' if note else ''}")
        bad = [x["task"] for x in rows if not x["ok"]]
        detail = ("All set. " if not bad else f"No working model for {', '.join(bad)}. ") + " · ".join(lines)
        return {"ok": not bad, "connected": not bad, "detail": detail[:600], "routes": rows}

    def app_version() -> str:
        try:
            from frontend import __version__

            return str(__version__)
        except Exception:
            return ""

    def get_rules() -> dict:
        s, r = config(), rules()
        picks = {t: picked(s, t) for t in all_tasks(r)}
        return {"ok": True, "rules": r, "defaults": merged_rules(None), "gateway": str(s.get("gateway") or ""),
                "picked": {t: f"{g}:{m}" if g else "" for t, (g, m) in picks.items()}, "effort": efforts(),
                "logins": {t: f"{lp[0]}:{lp[1]}" for t in picks if (lp := login_pick(s, t))},
                "app_version": app_version(), "version": VERSION,
                "pick_problems": {t: p for t, (g, _m) in picks.items() if (p := pick_problem(g, _m))}}

    def rule_changes(old: dict, new: dict) -> list[tuple[str, str, str]]:
        """(what, before, after) in plain words, one per changed part, for the History log."""
        out: list[tuple[str, str, str]] = []
        name = lambda t: (new.get("custom", {}).get(t) or old.get("custom", {}).get(t) or {}).get("label") or t  # noqa: E731
        if old["order"] != new["order"]:
            out.append(("order", " › ".join(map(name, old["order"])), " › ".join(map(name, new["order"]))))
        for t in sorted(set(old["custom"]) | set(new["custom"])):
            if t not in old["custom"]:
                out.append((t, "", f"new rule “{name(t)}”"))
            elif t not in new["custom"]:
                out.append((t, f"rule “{name(t)}”", "deleted"))
        for t in sorted(set(old["keywords"]) & set(new["keywords"])):
            a, b = old["keywords"][t], new["keywords"][t]
            if a != b:
                added, gone = [w for w in b if w not in a], [w for w in a if w not in b]
                out.append((f"{t} keywords", ", ".join(gone) or "–", ", ".join(added) or "–"))
        for t, tier in new["auto_tier"].items():
            if old["auto_tier"].get(t, tier) != tier:
                out.append((f"{t} auto", old["auto_tier"][t], tier))
        for t in sorted(set(old["examples"]) & set(new["examples"])):
            a, b = old["examples"][t], new["examples"][t]
            if a != b:
                added, gone = [w for w in b if w not in a], [w for w in a if w not in b]
                out.append((f"{t} examples", " | ".join(gone) or "–", " | ".join(added) or "–"))
        for k in ("short_question_chars", "small_context", "steps_ahead", "long_context", "match_confidence", "learn"):
            if old[k] != new[k]:
                out.append((k, str(old[k]), str(new[k])))
        return out

    def store_rules(merged: dict, by: str, why: str = "") -> dict:
        old = rules()
        try:
            api.data.put("rules", {"name": "Ducky Auto rules", **merged})
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        for what, before, after in rule_changes(old, merged):
            log_adjust(by, what, before, after, why)
        return {"ok": True, "rules": merged}

    def save_rules(rules_patch: dict | None = None, by: str = "you", why: str = "") -> dict:
        if not isinstance(rules_patch, dict):
            return {"ok": False, "error": "Send the rules as an object (order, keywords, auto_tier, numbers)."}
        saved = dict(api.data.get("rules") or {})
        for k, v in rules_patch.items():
            # keywords / examples / auto_tier patch one task at a time: the other tasks keep theirs.
            # "custom" is the whole set of the person's rules, so it replaces.
            deep = k != "custom" and isinstance(v, dict) and isinstance(saved.get(k), dict)
            saved[k] = {**saved[k], **v} if deep else v
        return store_rules(merged_rules(saved), by, why)

    def add_rule(label: str = "", keywords: list | None = None, by: str = "you", why: str = "") -> dict:
        """A new rule of the person's own (e.g. "Sound & music"), checked first."""
        r = rules()
        cid = custom_id(label)
        if not cid:
            return {"ok": False, "error": "Give the rule a name with letters or numbers."}
        if cid in r["custom"]:
            return {"ok": False, "error": f"There is already a rule called {r['custom'][cid]['label']}."}
        custom = {**r["custom"], cid: {"label": str(label).strip()[:60], "hint": ""}}
        words = [str(w).strip().lower() for w in (keywords or []) if str(w).strip()]
        out = store_rules(merged_rules({**r, "custom": custom, "order": [cid, *r["order"]],
                                        "keywords": {**r["keywords"], cid: words}}), by, why)
        return {**out, "task": cid} if out.get("ok") else out

    def delete_rule(task: str = "", by: str = "you", why: str = "") -> dict:
        r = rules()
        if task not in r["custom"]:
            return {"ok": False, "error": "Only rules you added can be deleted; built-in ones can be emptied."}
        custom = {k: v for k, v in r["custom"].items() if k != task}
        out = store_rules(merged_rules({**r, "custom": custom}), by, why)
        doc = dict(routes_doc())
        if doc.pop(task, None) is not None:
            api.data.put("routes", doc)
        return out

    def reset_rules(by: str = "you") -> dict:
        return store_rules(merged_rules(None), by, "reset to the defaults")

    # --- Opt-in sharing (Settings toggle "Share anonymous usage", off by default) ---------------
    share = {"queue": [], "first_wait": 0.0, "sent": 0, "last_sent": 0.0, "last_error": "", "busy": False}
    share_lock = threading.Lock()

    def site_base() -> str:
        """The UEFN Ducky site the app talks to (its account / update base)."""
        try:
            from frontend.duckyos_account import resolve_base_url

            return str(resolve_base_url()).rstrip("/")
        except Exception:
            return "https://uefnducky.org"

    def site_url() -> str:
        return site_base() + ENDPOINT_PATH

    def install_id() -> str:
        """A random id for this install only: not the account, email or PC."""
        doc = api.data.get("install") or {}
        if not re.fullmatch(r"[0-9a-f]{32}", str(doc.get("id") or "")):
            doc = {"name": "Ducky Auto install", "id": uuid.uuid4().hex}
            api.data.put("install", doc)
        return doc["id"]

    def custom_rules() -> bool:
        saved = api.data.get("rules")
        return bool(saved) and merged_rules(saved) != merged_rules(None)

    def sharing_on() -> bool:
        return settings().get("share_analytics") is True

    def share_step(row: dict) -> None:
        try:
            if not sharing_on():
                return
            ev = event_for(row, version=VERSION, install_id=install_id(), custom_rules=custom_rules())
        except Exception:
            return  # sharing never breaks a chat
        if ev is None:
            return
        with share_lock:
            q = share["queue"]
            q.append(ev)
            del q[:-_SHARE_QUEUE_MAX]
            share["first_wait"] = share["first_wait"] or time.time()
            due = len(q) >= _SHARE_EVERY or time.time() - share["first_wait"] >= _SHARE_MAX_WAIT_S
            if not due or share["busy"]:
                return
            share["busy"] = True
        threading.Thread(target=flush_share, daemon=True, name="ducky-auto-share").start()

    def flush_share() -> None:
        try:
            while True:
                with share_lock:
                    batch = share["queue"][:MAX_BATCH]
                if not batch or not sharing_on():  # turned off: what waits is never sent
                    with share_lock:
                        if not sharing_on():
                            share["queue"].clear()
                    return
                try:
                    # Collect endpoints want Origin = the site (like the app's own version check).
                    api.http_json("POST", site_url(), json_body={"events": batch}, timeout=20,
                                  headers={"Origin": site_base(), "User-Agent": f"UEFN-Ducky-Auto/{VERSION}"})
                except Exception as exc:
                    with share_lock:
                        share["last_error"] = str(exc)[:120]
                    return
                with share_lock:
                    del share["queue"][:len(batch)]
                    share["sent"] += len(batch)
                    share["last_sent"] = time.time()
                    share["last_error"] = ""
                    share["first_wait"] = time.time() if share["queue"] else 0.0
        finally:
            with share_lock:
                share["busy"] = False

    def share_status() -> dict:
        last = log.rows(limit=1)
        sample = last[0] if last else {"task": "coding", "decision": "first", "gateway": "gemini",
                                       "model": "gemini-3.8-flash", "context_tokens": 42000, "ms": 3500,
                                       "usage": {"input_tokens": 52000, "output_tokens": 128}}
        try:
            preview = event_for(sample, version=VERSION, install_id=install_id(), custom_rules=custom_rules())
        except Exception:
            preview = None
        with share_lock:
            return {"ok": True, "enabled": sharing_on(), "sent": share["sent"], "waiting": len(share["queue"]),
                    "last_sent": share["last_sent"], "last_error": share["last_error"], "to": site_url(),
                    "preview": preview}

    # --- Changes: by the person, an agent, setup or the tuner — all logged -------------------
    def log_adjust(by: str, task: str, before: str, after: str, why: str) -> None:
        try:
            api.data.put(f"adjust.{int(time.time() * 1000)}",
                         {"name": f"Ducky Auto change: {task}", "when": time.time(), "by": by, "task": task,
                          "before": before or "Auto", "after": after or "Auto", "why": why})
        except Exception:
            pass

    def adjustments(limit: int = 50) -> list[dict]:
        rows = list(api.data.items("adjust.").values())
        return sorted(rows, key=lambda a: a.get("when", 0), reverse=True)[:limit]

    def efforts() -> dict[str, str]:
        """Thinking effort per task ("" = the chat's own Faster / Smarter setting)."""
        raw = routes_doc().get("effort")
        known = all_tasks(rules())
        return {t: str(v) for t, v in (raw.items() if isinstance(raw, dict) else []) if t in known and v}

    def set_model(task: str = "", model: str = "", by: str = "you", why: str = "", effort: str | None = None) -> dict:
        """model: "gateway:model", or "" for Auto. effort: a thinking effort id ("off", "low", "high"…),
        None = leave it, "" = follow the chat's slider."""
        task = str(task or "").strip().lower()
        known = all_tasks(rules())
        if task not in known:
            return {"ok": False, "error": f"task is one of: {', '.join(known)}."}
        after = ""
        if str(model or "").strip():
            g, m = parse_route(str(model))
            if not g or not m or g == SELF:
                return {"ok": False, "error": "model is gateway:model (e.g. anthropic:claude-sonnet-5-5), or empty for Auto."}
            after = f"{g}:{m}"
        doc = dict(routes_doc())
        before = str(doc.get(task) or "")
        level = efforts()
        old_effort = level.get(task, "")
        new_effort = old_effort if effort is None else re.sub(r"[^a-z0-9_-]", "", str(effort).lower())[:20]
        if before == after and old_effort == new_effort:
            return {"ok": True, "task": task, "model": after or "Auto", "changed": False}
        doc[task] = after
        doc["effort"] = {**level, task: new_effort}
        try:
            api.data.put("routes", doc)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        if before != after:
            log_adjust(by, task, before, after, why)
        if old_effort != new_effort:
            log_adjust(by, f"{task} thinking", old_effort or "chat's", new_effort or "chat's", why)
        g, m = parse_route(after)
        return {"ok": True, "task": task, "model": after or "Auto", "effort": new_effort, "changed": True,
                "warning": pick_problem(g, m) if g else ""}

    def set_gateway(gateway: str = "", by: str = "you") -> dict:
        doc = dict(routes_doc())
        gateway = str(gateway or "").strip().lower()
        if gateway == str(doc.get("gateway") or ""):
            return {"ok": True, "changed": False}
        before, doc["gateway"] = str(doc.get("gateway") or ""), gateway
        api.data.put("routes", doc)
        log_adjust(by, "Auto picks from", before or "any", gateway or "any", "")
        return {"ok": True, "changed": True}

    async def tier_winners(prefer: str = "") -> dict[str, tuple[str, str]]:
        """One model per tier that answered its check, from the gateway with the most tiers working."""
        per_gateway: dict[str, dict[str, tuple[str, str]]] = {}
        gws = await asyncio.to_thread(gateways)
        for g in ([prefer] if prefer in gws else []) + [x for x in gws if x != prefer]:
            found: dict[str, tuple[str, str]] = {}
            ids = await asyncio.to_thread(models_of, g)
            for tier in ("best", "balanced", "fast"):
                for m in [x for x in rank_tier(ids, tier, _PER_GATEWAY) if tier_of(x) == tier]:
                    if (await probe(g, m))[0]:
                        found[tier] = (g, m)
                        break
            per_gateway[g] = found
            if len(found) == 3:
                break
        ranked = sorted(per_gateway.items(), key=lambda kv: (-len(kv[1]), kv[0] != prefer))
        winners: dict[str, tuple[str, str]] = {}
        for _g, found in ranked:  # the fullest gateway first; others fill its gaps
            for tier, pick in found.items():
                winners.setdefault(tier, pick)
        for tier, fallbacks in (("balanced", ("best", "fast")), ("best", ("balanced", "fast")), ("fast", ("balanced", "best"))):
            for f in fallbacks:
                if tier not in winners and f in winners:
                    winners[tier] = winners[f]
        return winners

    def setup(apply: bool = True, keep_my_picks: bool = True, prefer_gateway: str = "", by: str = "setup") -> dict:
        """Check the models and pin one per task: best for planning, fast for quick questions,
        balanced for the rest; tool steps stay on the turn's model. Keeps working picks unless told."""
        winners = run(tier_winners(str(prefer_gateway or "").strip().lower()), {})
        if not isinstance(winners, dict) or not winners:
            return {"ok": False, "error": "No model answered its check. Add an API key under Settings → LLMs first."}
        r, doc = rules(), routes_doc()
        plan, kept = {}, {}
        for task in all_tasks(r):
            tier = r["auto_tier"].get(task, "balanced")
            if tier == "stay":
                continue
            current = str(doc.get(task) or "")
            if keep_my_picks and current and not pick_problem(*parse_route(current)):
                kept[task] = current
                continue
            g, m = winners.get(tier) or winners.get("balanced") or next(iter(winners.values()))
            plan[task] = f"{g}:{m}"
        applied = []
        if apply:
            for task, model in plan.items():
                out = set_model(task, model, by=by, why=f"checked {r['auto_tier'].get(task)} model")
                if out.get("changed"):
                    applied.append(task)
        distinct = {f"{g}:{m}" for g, m in winners.values()}
        note = ("Only one model answered its check, so every task uses it. Add another gateway's key for a "
                "real split.") if len(distinct) == 1 else ""
        return {"ok": True, "tiers": {t: f"{g}:{m}" for t, (g, m) in winners.items()}, "plan": plan,
                "kept_your_picks": kept, "applied": applied, "note": note}

    def tune(apply: bool = False, task: str = "", kind: str = "") -> dict:
        """What the analytics say to change; with apply, change it (every change is logged).
        task / kind: apply only the suggestion that matches (the panel's per-suggestion Apply)."""
        rows = log.rows(limit=500)
        doc = routes_doc()
        picks = {t: str(doc.get(t) or "") for t in all_tasks(rules())}
        found = suggest(rows, picks)
        applied = []
        if apply:
            r = rules()
            for s in [x for x in found if (not task or x["task"] == task) and (not kind or x["kind"] == kind)]:
                if s["action"] == "replace":
                    bad = {s.get("model", ""), picks.get(s["task"], "")}
                    cfg = {**config(), f"route_{s['task']}": ""}
                    cands = [c for c in candidates(s["task"], cfg, r) if f"{c[0]}:{c[1]}" not in bad]

                    async def first_ok(cands=cands):
                        for g, m in cands:
                            if (await probe(g, m))[0]:
                                return g, m
                        return "", ""

                    g, m = run(first_ok(), ("", ""))
                    if g:
                        set_model(s["task"], f"{g}:{m}", by="tune", why=s["why"])
                        applied.append({**s, "now": f"{g}:{m}"})
                elif s["action"] == "pin":
                    out = setup(apply=True, keep_my_picks=True, by="tune")
                    applied.append({**s, "now": out.get("plan")})
        return {"ok": True, "suggestions": found, "applied": applied,
                "note": "" if found else f"Nothing to change from the last {len(rows)} steps."}

    def baseline() -> tuple[str, tuple | None]:
        """The priciest best-tier model you have: what 'without Ducky Auto' is measured against."""
        best: tuple[str, tuple | None] = ("", None)
        for g in gateways():
            m = pick_tier(models_of(g), "best")
            p = prices(g, m) if m else None
            if p and p[0] is not None and p[1] is not None and (best[1] is None or p[0] > best[1][0]):
                best = (f"{g}:{m}", p)
        return best

    def analytics(limit: int = 100, chat: str = "") -> dict:
        rows = log.rows(limit=max(1, min(int(limit or 100), 2000)), chat=str(chat or ""))
        name, base = baseline()
        def prices_of(route: str) -> tuple | None:
            g, _, m = route.partition(":")
            return prices(g, m) if g and m else None

        return {"ok": True, "summary": summary(rows, base, name, prices_of), "steps": list(reversed(rows)),
                "adjustments": adjustments()}

    def analytics_clear() -> dict:
        log.clear()
        return {"ok": True}

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_route(prompt: str = "") -> dict:
        """Which task a prompt is, the rule that matched, and the checked gateway/model Ducky Auto sends it to."""
        return route_for(prompt)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_check_routes() -> dict:
        """Check every Ducky Auto task: send each picked (or Auto) model a tiny prompt and list what answers."""
        return check_routes()

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_get_rules() -> dict:
        """Ducky Auto's rules: task order (first match wins), keywords per task, Auto tier per task,
        the model picked per task ("" = Auto) and the cost numbers."""
        return get_rules()

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_save_rules(rules_patch: dict | None = None, why: str = "") -> dict:
        """Change Ducky Auto's rules. rules_patch may hold order (list of tasks), keywords ({task: [words]};
        "word*" matches any ending), auto_tier ({task: fast|balanced|best|stay}), short_question_chars,
        small_context, steps_ahead. Unsent fields keep their value. why = a short reason; every change
        shows in the person's History and Decision tree as made by an agent."""
        return save_rules(rules_patch, by="agent", why=why)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_add_rule(label: str = "", keywords: list | None = None, why: str = "") -> dict:
        """Add a Ducky Auto rule of the person's own, e.g. label "Sound & music", keywords ["sfx", "music*"].
        It is checked first; give it a model with ducky_auto_set_model(task=<returned task>)."""
        return add_rule(label, keywords, by="agent", why=why)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_delete_rule(task: str = "", why: str = "") -> dict:
        """Delete a rule the person added (its task id starts with my_). Built-in rules can't be deleted."""
        return delete_rule(task, by="agent", why=why)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_reset_rules() -> dict:
        """Put Ducky Auto's rules back to the defaults (models picked per task stay; added rules go)."""
        return reset_rules(by="agent")

    @api.tool(intent=r"\b(ducky[ -]?auto|routing) (analytics|log|stats)\b", listener=False)
    def ducky_auto_analytics(limit: int = 100, chat: str = "") -> dict:
        """Ducky Auto's routing log, newest first: per step the task and the rule that matched, model, models
        that failed their check, switch/keep decision and why, context size, tokens, estimated cost, time
        and errors; plus totals per model. chat = a chat key from a step, to see one chat only."""
        return analytics(limit, chat)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_analytics_clear() -> dict:
        """Delete Ducky Auto's routing log on this PC."""
        return analytics_clear()

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_setup(apply: bool = False, keep_my_picks: bool = True, prefer_gateway: str = "") -> dict:
        """Set Ducky Auto up for the person: check which models answer and pin one per task (best for
        planning, fast for quick questions, balanced for the rest; tool steps stay on the turn's model).
        keep_my_picks keeps models the person already picked that still run. apply=False (default) only shows
        the plan; apply=True only when the person asked for it — never pick models on your own.
        Every change is logged under Analytics → Changes."""
        return setup(apply, keep_my_picks, prefer_gateway, by="agent")

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_set_model(task: str = "", model: str = "", why: str = "", effort: str | None = None) -> dict:
        """Set the model for one Ducky Auto task (planning, coding, modeling, execution, research, writing,
        quick, general, long = chats over the Long chats size). model = "gateway:model" (e.g. anthropic:claude-sonnet-5-5) or "" for Auto.
        effort = thinking effort for that task (off, low, medium, high…; "" = the chat's slider; omit = keep).
        why = a short reason, shown in the change log."""
        return set_model(task, model, by="agent", why=why, effort=effort)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_set_gateway(gateway: str = "") -> dict:
        """The gateway Ducky Auto's Auto picks try first (e.g. anthropic, openai, gemini); "" = any with a key."""
        return set_gateway(gateway, by="agent")

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_tune(apply: bool = False) -> dict:
        """Read Ducky Auto's analytics and say what to change: a model that errors on a task too often,
        a picked model that can't run, steps slowed by models failing their check, slow tasks. apply=True
        makes the changes (each logged with its reason); apply=False only suggests."""
        return tune(apply)

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_share_status() -> dict:
        """Whether anonymous usage sharing is on (the person's toggle in the Ducky Auto panel), how many
        steps were sent, and a preview of exactly what one step sends. Only the person turns it on."""
        return share_status()

    def picker() -> dict:
        """What the panel's model menu lists, like the chat's: signed-in logins with their models, then
        API models of gateways that have a key. Each model carries its Faster / Smarter levels."""
        from backend.agent.model_fetch import get_model_info
        from backend.agent.thinking_effort import ensure_thinking_menu
        from backend.uefn_plugins.plugin_host.gateways import get_llm_provider_registration

        logins = []
        try:
            from backend.agent.coding_agents import detect_all  # cached: no CLI start here

            for a in (detect_all() or {}).get("agents") or []:
                aid = str(a.get("id") or "")
                if aid in ("", "ducky") or not (a.get("enabled") and a.get("available")) or a.get("logged_in") is False:
                    continue
                pid = str(a.get("plugin_id") or "")
                gw = next((g for g in gateways_all() if (get_llm_provider_registration(g) or {}).get("plugin_id") == pid), "")
                logins.append({"id": aid, "label": a.get("label") or agent_label(aid), "gateway": gw,
                               "models": [{"id": m["id"], "name": m.get("name") or m["id"],
                                           "menu": ensure_thinking_menu(m.get("thinking_menu"))}
                                          for m in a.get("models") or [] if isinstance(m, dict) and m.get("id")]})
        except Exception as exc:
            api.log(f"Ducky Auto: logins unreadable: {exc}")
        api_rows = []
        for g in gateways():
            label = str((get_llm_provider_registration(g) or {}).get("label") or g.replace("_", " ").title())
            for mid in models_of(g)[:80]:
                info = get_model_info(g, mid)
                api_rows.append({"gateway": g, "label": label, "id": mid, "name": getattr(info, "display_name", None) or mid,
                                 "menu": ensure_thinking_menu(getattr(info, "thinking_menu", None))})
        return {"ok": True, "logins": logins, "api": api_rows}

    def gateways_all() -> list[str]:
        try:
            from backend.agent.providers import gateway_providers

            return [g for g in gateway_providers() if g != SELF]
        except Exception:
            return []

    @api.tool(intent=r"\bducky[ -]?auto\b", listener=False)
    def ducky_auto_models() -> dict:
        """Every model Ducky Auto can be given for a task, as the chat's picker lists them: signed-in logins
        (Claude Code, Codex…) with their models, then API models. Pick one with ducky_auto_set_model
        (login models as agent:model, e.g. claude_code:claude-opus-5-5)."""
        return picker()

    @api.register_pipeline_node("ducky-auto.route")
    def node_route(ctx: dict) -> dict:
        return route_for(str((ctx.get("inputs") or {}).get("prompt") or ""))

    # Settings → LLMs → Ducky Auto: the page ui/settings.js draws in the provider's ducky:llm-slot.
    # Each name has its ducky_auto_<name> tool for agents.
    api.register_panel_rpc("get_rules", lambda: get_rules())
    api.register_panel_rpc("save_rules", lambda rules_patch=None: save_rules(rules_patch, by="you"))
    api.register_panel_rpc("add_rule", lambda label="", keywords=None: add_rule(label, keywords, by="you"))
    api.register_panel_rpc("delete_rule", lambda task="": delete_rule(task, by="you"))
    api.register_panel_rpc("reset_rules", lambda: reset_rules(by="you"))
    api.register_panel_rpc("route", lambda prompt="": route_for(prompt))
    api.register_panel_rpc("check_routes", lambda: check_routes())
    api.register_panel_rpc("analytics", lambda limit=200, chat="": analytics(limit, chat))
    api.register_panel_rpc("analytics_clear", lambda: analytics_clear())
    api.register_panel_rpc("share_status", lambda: share_status())
    api.register_panel_rpc("set_model", lambda task="", model="", effort=None: set_model(task, model, by="you", effort=effort))
    api.register_panel_rpc("set_gateway", lambda gateway="": set_gateway(gateway, by="you"))
    api.register_panel_rpc("setup", lambda: setup(True, True, "", by="you"))
    api.register_panel_rpc("tune", lambda apply=False, task="", kind="": tune(bool(apply), str(task or ""), str(kind or "")))
    api.log("Ducky Auto gateway registered")
