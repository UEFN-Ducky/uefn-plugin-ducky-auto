"""Pure routing rules: task type, price tier, and whether a model switch pays for itself.

Rules are data the person edits in Settings → LLMs → Ducky Auto (order, keywords, Auto tier).
No host imports, so test_router.py runs with plain Python.
"""

from __future__ import annotations

import re

TASKS = ("planning", "coding", "modeling", "execution", "research", "writing", "quick", "long", "general")
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
                  "writing": "balanced", "quick": "fast", "general": "balanced", "execution": "stay",
                  "long": "balanced"},
    # When no keyword matches, the closest example message picks the rule (word overlap, no model).
    "examples": {
        "modeling": ["make a low poly rock", "the car looks too shiny", "add a tree with leaves",
                     "smooth the edges on the sword", "the character looks stretched"],
        "coding": ["make the door open when a player steps on the plate", "why does it crash when the round starts",
                   "the build fails with a weird message", "give players points when they eliminate someone",
                   "the timer never stops"],
        "planning": ["what steps do i need to build a tycoon", "help me figure out the game loop",
                     "how do i structure the rounds and scoring", "what should i build first"],
        "research": ["what is the best way to do a day night cycle", "is there a device that tracks score",
                     "what do other creators use for leaderboards", "which one is faster"],
        "writing": ["give the shopkeeper some lines", "name ideas for my island", "make the intro text sound exciting",
                    "write the quest text"],
        "quick": ["ok", "yes", "cool thanks", "got it", "nice"],
    },
    "match_confidence": 35,      # % word overlap an example needs to pick its rule
    "short_question_chars": 90,  # a question shorter than this is Quick
    "small_context": 8000,       # without prices, only switch while the chat is under this many tokens
    "steps_ahead": 3,            # steps a switch is expected to pay back over
    "long_context": 100_000,     # a chat over this many tokens goes to the Long chats rule (0 = off)
    "learn": True,               # Auto prefers models that answered well for this rule before
}

# How each provider bills its prompt cache: write = price of filling it (x input), ttl_s = how long
# it stays warm without use, min_prefix = shortest prompt it caches. From each vendor's pricing page:
# Anthropic 1.25x write and 5 min; OpenAI 30 min, no write fee; Gemini implicit cache from 4k tokens.
CACHE_RULES = {
    "anthropic": {"write": 1.25, "ttl_s": 300, "min_prefix": 1024},
    "openai": {"write": 1.0, "ttl_s": 1800, "min_prefix": 1024},
    "gemini": {"write": 1.0, "ttl_s": 300, "min_prefix": 4096},
    "deepseek": {"write": 1.0, "ttl_s": 3600, "min_prefix": 64},
    "kimi": {"write": 1.0, "ttl_s": 300, "min_prefix": 1024},
}
_CACHE_DEFAULT = {"write": 1.0, "ttl_s": 300, "min_prefix": 1024}


def cache_rules(gateway: str, price_in: float | None = None, price_write: float | None = None) -> dict:
    """The gateway's cache billing; a model's own cache-write price wins when the gateway lists it."""
    out = dict(CACHE_RULES.get((gateway or "").lower(), _CACHE_DEFAULT))
    if price_write and price_in:
        out["write"] = round(price_write / price_in, 3)
    return out


def fits_window(context_tokens: int, limit: int | None) -> bool:
    """Room for the chat plus an answer (15 %); unknown windows always fit."""
    return not limit or limit >= context_tokens * 1.15

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

    examples = {**DEFAULT_RULES["examples"], **{c: [] for c in custom}}
    for task, lines in (s.get("examples") or {}).items():
        if task in ruled and isinstance(lines, list):
            examples[task] = [str(x).strip()[:200] for x in lines if str(x).strip()][:30]

    return {"order": order, "keywords": keywords, "examples": examples, "auto_tier": tiers, "custom": custom,
            "short_question_chars": num("short_question_chars", 0, 1000),
            "small_context": num("small_context", 0, 2_000_000), "steps_ahead": num("steps_ahead", 1, 50),
            "long_context": num("long_context", 0, 10_000_000), "match_confidence": num("match_confidence", 1, 100),
            "learn": bool(s.get("learn", DEFAULT_RULES["learn"]))}


def _keyword_rx(word: str) -> re.Pattern[str]:
    stem = word.endswith("*")
    body = re.escape(word.rstrip("*")).replace(r"\ ", r"\s+")
    lead = r"\b" if re.match(r"\w", word) else ""
    return re.compile(lead + body + (r"\w*" if stem else (r"\b" if re.search(r"\w$", word) else "")), re.I)


_STOP = frozenset("a an the and or but to of in on at for with my me i it is are be do does did this that "
                  "these those you your we our can could would should will just so some any please "
                  "what how why which when where who there here make get want need".split())


def _stems(text: str) -> set[str]:
    """Words without their ending (steps → step, crashed → crash), common words dropped."""
    out = set()
    for w in re.findall(r"[a-z0-9@]+", (text or "").lower()):
        if w in _STOP:
            continue
        for end in ("ing", "ed", "es", "s", "ly"):
            if len(w) > len(end) + 2 and w.endswith(end):
                w = w[: -len(end)]
                break
        out.add(w)
    return out


def similar_task(text: str, rules: dict) -> tuple[str, float, str]:
    """(task, score 0..1, example) of the example message closest to ``text``; ("", 0, "") when none."""
    words = _stems(text)
    best = ("", 0.0, "")
    if not words:
        return best
    for task in rules["order"]:
        for ex in (rules.get("examples") or {}).get(task) or []:
            other = _stems(ex)
            if other:
                score = len(words & other) / (len(words) * len(other)) ** 0.5
                if score > best[1]:
                    best = (task, score, ex)
    return best


def explain_task(text: str, last_role: str = "user", rules: dict | None = None,
                 context_tokens: int = 0) -> tuple[str, str]:
    """(task, why). A step right after a tool result is execution; a chat over Long chats' size is long;
    then keywords top to bottom; then the closest example message; then a short question is quick."""
    r = rules or DEFAULT_RULES
    if (last_role or "").lower() == "tool":
        return "execution", "a step right after a tool returned"
    limit = r.get("long_context") or 0
    if limit and context_tokens > limit:
        return "long", f"the chat is {context_tokens // 1000}k tokens (over {limit // 1000}k)"
    t = (text or "").strip()
    for task in r["order"]:
        for word in r["keywords"].get(task) or []:
            if _keyword_rx(word).search(t):
                return task, f'matched "{word}"'
    task, score, ex = similar_task(t, r)
    if task and score * 100 >= r.get("match_confidence", DEFAULT_RULES["match_confidence"]):
        return task, f'like "{ex}" ({round(score * 100)}%)'
    if t.endswith("?") and len(t) < r["short_question_chars"]:
        return "quick", f"a question under {r['short_question_chars']} characters"
    return "general", "no keyword or example matched"


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
    stay_warm: float = 1.0,
    new_warm: float = 0.0,
    stay_write: float = 1.0,
    new_write: float = 1.25,
    hit: float = 1.0,
) -> bool:
    """Is moving the chat to another model cheaper than staying, counting the re-read?

    ``current`` / ``new``: (price_in, price_out, price_cached_in) per 1M tokens, None unknown.
    ``stay_warm`` / ``new_warm``: share of the chat each model would read from its cache on the next
    step (0 once its cache expired, e.g. the chat sat idle). The rest is read at the input price times
    that gateway's cache-write price (``stay_write`` / ``new_write``). Later steps read ``hit`` of the
    chat from cache (the model's measured share). An upgrade (stronger tier) always switches.
    """
    if upgrade or current is None:
        return True
    if new is None or None in current[:2] or None in new[:2]:
        return context_tokens < small_context or stay_warm == 0
    a_in, a_out, a_cached = current
    b_in, b_out, b_cached = new
    a_cached = a_in * 0.1 if a_cached is None else a_cached
    b_cached = b_in * 0.1 if b_cached is None else b_cached

    def run(p_in: float, p_cached: float, p_out: float, warm: float, write: float) -> float:
        first = context_tokens * (warm * p_cached + (1 - warm) * p_in * write)
        later = (steps - 1) * context_tokens * (hit * p_cached + (1 - hit) * p_in)
        return first + later + steps * out_tokens * p_out

    return run(b_in, b_cached, b_out, new_warm, new_write) < run(a_in, a_cached, a_out, stay_warm, stay_write)


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
