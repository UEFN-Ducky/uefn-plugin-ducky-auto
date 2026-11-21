"""Pure routing rules: task type, price tier, and whether a model switch pays for itself.

Rules are data the person edits in Settings → LLMs → Ducky Auto (order, keywords, Auto tier).
No host imports, so test_router.py runs with plain Python.
"""

from __future__ import annotations

import re

TASKS = ("planning", "coding", "modeling", "execution", "research", "writing", "quick", "general")
KEYWORD_TASKS = ("modeling", "coding", "planning", "research", "writing", "quick")  # default order
TIER_RANK = {"fast": 0, "balanced": 1, "best": 2}

DEFAULT_RULES: dict = {
    # First match wins, top to bottom. "word*" matches any ending (plan* = plan, planning, planned).
    "order": list(KEYWORD_TASKS),
    "keywords": {
        "modeling": ["blender", "mesh", "meshes", "modeling", "3d", "sculpt*", "retopo*", "uv", "uvs", "rig",
                     "rigging", "fbx", "texture*", "material*", "shader*", "lod", "prop", "vfx", "niagara",
                     "level design", "layout"],
        "coding": ["verse", "code", "coding", "function", "class", "bug", "error", "errors", "compile*", "script*",
                   "python", "typescript", "javascript", "refactor*", "debug*", "stack trace", "exception", "api",
                   "device wiring", "@editable"],
        "planning": ["plan*", "design*", "architect*", "roadmap", "strategy", "break it down", "break down", "spec",
                     "outline", "how should i", "how should we", "approach"],
        "research": ["research", "look up", "lookup", "search", "compare", "comparison", "find out", "docs",
                     "documentation", "which is better", "sources"],
        "writing": ["write", "rewrite", "story", "dialogue", "lore", "description", "copywriting", "blurb",
                    "translate*", "poem", "email", "summar*"],
        "quick": ["hi", "hey", "hello", "thanks", "thank you"],
    },
    # Auto's price tier per task. Execution "stay" = keep the turn's model (its cache stays warm).
    "auto_tier": {"planning": "best", "coding": "balanced", "modeling": "balanced", "research": "balanced",
                  "writing": "balanced", "quick": "fast", "general": "balanced", "execution": "stay"},
    "short_question_chars": 90,  # a question shorter than this is Quick
    "small_context": 8000,       # without prices, only switch while the chat is under this many tokens
    "steps_ahead": 3,            # steps a switch is expected to pay back over
}

FAST = re.compile(r"\b(haiku|mini|nano|flash|lite|small|instant|tiny|[1-9]b)\b", re.I)  # \b: "gemini" isn't "mini"
BEST = re.compile(r"\b(opus|ultra|pro|large|max|fable)\b", re.I)
# Models a chat can't run (speech, pictures, embeddings…) and other routers.
_NOT_CHAT = re.compile(
    r"embed|tts|whisper|dall-?e|image|audio|realtime|moderation|transcri|search-preview|^(auto|default)$", re.I
)
SMALL_CONTEXT = DEFAULT_RULES["small_context"]


CUSTOM_ID = re.compile(r"^my_[a-z0-9_]{1,40}$")  # rules the person adds: "my_" + a slug of its name
MAX_CUSTOM = 30


def custom_id(label: str) -> str:
    """'Sound & music' → 'my_sound_music'."""
    slug = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")[:40]
    return f"my_{slug}" if slug else ""


def all_tasks(rules: dict) -> tuple[str, ...]:
    """The built-in tasks plus the rules the person added."""
    return TASKS + tuple(rules.get("custom") or {})


def merged_rules(saved: dict | None) -> dict:
    """The person's rules over the defaults; unknown tasks and bad values are dropped."""
    s = saved if isinstance(saved, dict) else {}
    custom: dict[str, dict] = {}
    for cid, info in list((s.get("custom") or {}).items())[:MAX_CUSTOM]:
        label = str((info or {}).get("label") or "").strip()[:60] if isinstance(info, dict) else ""
        if CUSTOM_ID.match(str(cid)) and label:
            custom[cid] = {"label": label, "hint": str(info.get("hint") or "").strip()[:120]}
    ruled = KEYWORD_TASKS + tuple(custom)
    order = [t for t in s.get("order") or [] if t in ruled]
    order += [t for t in ruled if t not in order]
    keywords = {**DEFAULT_RULES["keywords"], **{c: [] for c in custom}}
    for task, words in (s.get("keywords") or {}).items():
        if task in ruled and isinstance(words, list):
            keywords[task] = [str(w).strip().lower() for w in words if str(w).strip()][:200]
    tiers = {**DEFAULT_RULES["auto_tier"], **{c: "balanced" for c in custom}}
    for task, tier in (s.get("auto_tier") or {}).items():
        if (task in TASKS or task in custom) and tier in ("fast", "balanced", "best", "stay"):
            tiers[task] = tier

    def num(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(s.get(key, DEFAULT_RULES[key]))))
        except (TypeError, ValueError):
            return DEFAULT_RULES[key]

    return {"order": order, "keywords": keywords, "auto_tier": tiers, "custom": custom,
            "short_question_chars": num("short_question_chars", 0, 1000),
            "small_context": num("small_context", 0, 2_000_000), "steps_ahead": num("steps_ahead", 1, 50)}


def _keyword_rx(word: str) -> re.Pattern[str]:
    stem = word.endswith("*")
    body = re.escape(word.rstrip("*")).replace(r"\ ", r"\s+")
    lead = r"\b" if re.match(r"\w", word) else ""
    return re.compile(lead + body + (r"\w*" if stem else (r"\b" if re.search(r"\w$", word) else "")), re.I)


def explain_task(text: str, last_role: str = "user", rules: dict | None = None) -> tuple[str, str]:
    """(task, why). A step right after a tool result is execution."""
    r = rules or DEFAULT_RULES
    if (last_role or "").lower() == "tool":
        return "execution", "a step right after a tool returned"
    t = (text or "").strip()
    for task in r["order"]:
        for word in r["keywords"].get(task) or []:
            if _keyword_rx(word).search(t):
                return task, f'matched "{word}"'
    if t.endswith("?") and len(t) < r["short_question_chars"]:
        return "quick", f"a question under {r['short_question_chars']} characters"
    return "general", "no keyword matched"


def classify(text: str, last_role: str = "user", rules: dict | None = None) -> str:
    return explain_task(text, last_role, rules)[0]


def tier_of(model_id: str) -> str:
    if FAST.search(model_id or ""):
        return "fast"
    if BEST.search(model_id or ""):
        return "best"
    return "balanced"


def _newest_first(model_id: str) -> tuple:
    return tuple(-int(n) for n in re.findall(r"\d+", model_id or ""))


def rank_tier(model_ids: list[str], tier: str, per_tier: int = 0) -> list[str]:
    """Chat models of ``tier`` newest first, then the next tier up, then down.
    ``per_tier``: at most this many from each tier (0 = all), so a tier full of
    models that fail their check can't hide the next tier."""
    usable = [m for m in model_ids if m and not _NOT_CHAT.search(m)]
    order = {"fast": ("fast", "balanced", "best"), "balanced": ("balanced", "best", "fast"),
             "best": ("best", "balanced", "fast")}.get(tier, ("balanced", "best", "fast"))
    out: list[str] = []
    for want in order:
        hits = sorted((m for m in usable if tier_of(m) == want), key=_newest_first)
        out += hits[:per_tier] if per_tier else hits
    return out


def pick_tier(model_ids: list[str], tier: str) -> str:
    ranked = rank_tier(model_ids, tier)
    return ranked[0] if ranked else ""


def tier_count(model_ids: list[str]) -> int:
    """How many of fast/balanced/best a gateway offers (Auto prefers the full set)."""
    return len({tier_of(m) for m in model_ids if m and not _NOT_CHAT.search(m)})


def worth_switching(
    context_tokens: int,
    current: tuple | None,
    new: tuple | None,
    *,
    upgrade: bool = False,
    steps: int = 3,
    out_tokens: int = 800,
    small_context: int = SMALL_CONTEXT,
) -> bool:
    """Is moving the chat to another model cheaper than staying, counting the re-read?

    ``current`` / ``new``: (price_in, price_out, price_cached_in) per 1M tokens, None unknown.
    The new model reads the whole chat once uncached (+25 % cache write), then cached; the current
    model reads it cached every step. An upgrade (stronger tier) always switches: quality first.
    """
    if upgrade or current is None:
        return True
    if new is None or None in current[:2] or None in new[:2]:
        return context_tokens < small_context
    a_in, a_out, a_cached = current
    b_in, b_out, b_cached = new
    a_cached = a_in * 0.1 if a_cached is None else a_cached
    b_cached = b_in * 0.1 if b_cached is None else b_cached
    stay = steps * (context_tokens * a_cached + out_tokens * a_out)
    switch = context_tokens * b_in * 1.25 + (steps - 1) * context_tokens * b_cached + steps * out_tokens * b_out
    return switch < stay


def parse_route(value: str) -> tuple[str, str]:
    """'anthropic:claude-x' → ('anthropic', 'claude-x'); '' → ('', '') = Auto."""
    v = (value or "").strip()
    if not v or ":" not in v:
        return "", ""
    gateway, _, model = v.partition(":")  # ollama ids keep their own colon (llama3:8b)
    gateway = gateway.strip().lower().replace("-", "_")
    if gateway == "tier":  # a 1.0 dropdown value: Auto now
        return "", ""
    return gateway, model.strip()
