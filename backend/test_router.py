"""Run: py -3 -I backend/test_router.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from router import (  # noqa: E402
    DEFAULT_RULES, classify, explain_task, merged_rules, parse_route, pick_tier, rank_tier, tier_count, tier_of,
    cache_rules, fits_window, similar_task, worth_switching,
)

OPUS = (5.0, 25.0, 0.5)
HAIKU = (1.0, 5.0, 0.1)


def test_classify() -> None:
    assert classify("fix the Verse compile errors in shop.verse") == "coding"
    assert classify("model a low poly car in Blender") == "modeling"
    assert classify("plan the quest system for my island") == "planning"
    assert classify("research the best lighting setups") == "research"
    assert classify("write a short lore blurb") == "writing"
    assert classify("what time is it?") == "quick"
    assert classify("hey") == "quick"
    assert classify("make the cinema bigger and add more seats everywhere") == "general"
    assert classify("anything", "tool") == "execution"
    assert explain_task("we are planning a raid") == ("planning", 'matched "plan*"')  # stem
    assert classify("they explained it") == "general"  # "plan*" needs a word start


def test_person_rules() -> None:
    # Moving Coding above Modeling changes who wins "fix the texture compile errors".
    text = "fix the texture compile errors"
    assert classify(text, rules=merged_rules(None)) == "modeling"
    mine = merged_rules({"order": ["coding", "modeling"], "keywords": {"writing": ["haiku", "pitch deck"]}})
    assert mine["order"][:2] == ["coding", "modeling"] and len(mine["order"]) == len(DEFAULT_RULES["order"])
    assert classify(text, rules=mine) == "coding"
    assert explain_task("make a pitch deck", rules=mine) == ("writing", 'matched "pitch deck"')
    # Bad values fall back to the defaults.
    junk = merged_rules({"order": ["nope"], "auto_tier": {"coding": "huge"}, "steps_ahead": "x"})
    assert junk["auto_tier"]["coding"] == "balanced" and junk["steps_ahead"] == 3


def test_tiers() -> None:
    ids = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-4-1", "text-embedding-3"]
    assert tier_of("gpt-5-mini") == "fast" and tier_of("gemini-3-pro") == "best"
    assert pick_tier(ids, "fast") == "claude-haiku-5-5"
    assert pick_tier(ids, "balanced") == "claude-sonnet-5-5"
    assert pick_tier(ids, "best") == "claude-opus-5-5"
    assert rank_tier(ids, "best")[:2] == ["claude-opus-5-5", "claude-opus-4-1"]
    assert pick_tier(["claude-opus-5-5"], "fast") == "claude-opus-5-5"
    many = ["m-1", "m-2", "m-3", "m-4", "x-pro-2", "x-flash-3"]
    assert rank_tier(many, "balanced", 3) == ["m-4", "m-3", "m-2", "x-pro-2", "x-flash-3"]
    assert pick_tier([], "best") == ""
    assert pick_tier(["auto", "claude-opus-5"], "balanced") == "claude-opus-5"
    assert tier_count(ids) == 3 and tier_count(["auto", "claude-opus-5"]) == 1


def test_switch_costs() -> None:
    assert worth_switching(5_000, OPUS, HAIKU)
    assert not worth_switching(400_000, OPUS, HAIKU, steps=1, out_tokens=100)
    assert not worth_switching(50_000, HAIKU, OPUS)
    assert worth_switching(400_000, HAIKU, OPUS, upgrade=True)
    assert worth_switching(400_000, None, HAIKU)
    assert worth_switching(2_000, (None, None, None), HAIKU)
    assert not worth_switching(50_000, (None, None, None), HAIKU)
    assert worth_switching(50_000, (None, None, None), HAIKU, small_context=100_000)


def test_cache_aware_switching() -> None:
    assert cache_rules("anthropic")["write"] == 1.25 and cache_rules("openai")["ttl_s"] == 1800
    assert cache_rules("somebody") == {"write": 1.0, "ttl_s": 300, "min_prefix": 1024}
    assert cache_rules("anthropic", 3.0, 6.0)["write"] == 2.0  # the model's own write price wins
    # 200k chat, Opus → Haiku for 1 step: a warm Opus cache makes staying cheaper...
    assert not worth_switching(200_000, OPUS, HAIKU, steps=1, out_tokens=100)
    # ...but after the cache expired (chat idle), staying re-reads it all on Opus: switch.
    assert worth_switching(200_000, OPUS, HAIKU, steps=1, out_tokens=100, stay_warm=0.0, stay_write=1.25)
    # Going back to a model whose cache is still warm costs almost nothing.
    assert worth_switching(200_000, OPUS, HAIKU, steps=1, out_tokens=100, new_warm=1.0)
    # No write fee (OpenAI-style) tips a borderline switch: 5 steps at 60k, 90 % cache hits, 2x price gap.
    cheap, dear = (1.0, 4.0, 0.1), (2.0, 8.0, 0.2)
    assert not worth_switching(60_000, dear, cheap, steps=5, new_write=1.25, hit=0.9)
    assert worth_switching(60_000, dear, cheap, steps=5, new_write=1.0, hit=0.9)
    # No prices: a cold cache allows the switch whatever the size.
    assert worth_switching(500_000, (None, None, None), HAIKU, stay_warm=0.0)


def test_long_chats_and_windows() -> None:
    r = merged_rules(None)
    assert explain_task("fix the verse bug", "user", r, context_tokens=140_000) == (
        "long", "the chat is 140k tokens (over 100k)")
    assert explain_task("fix the verse bug", "user", r, context_tokens=20_000)[0] == "coding"
    assert explain_task("go on", "tool", r, context_tokens=500_000)[0] == "execution"  # tool steps stay
    assert explain_task("fix it", "user", merged_rules({"long_context": 0}), context_tokens=900_000)[0] != "long"
    assert not fits_window(130_000, 128_000) and fits_window(100_000, 128_000) and fits_window(10**6, None)
    # Long chats is a real task: a model can be picked for it and its Auto tier sticks.
    from router import all_tasks
    assert "long" in all_tasks(r)
    assert merged_rules({"auto_tier": {"long": "best"}})["auto_tier"]["long"] == "best"


def test_examples() -> None:
    r = merged_rules(None)
    task, why = explain_task("the door doesn't open when I step on the plate", "user", r)
    assert task == "coding" and why.startswith('like "make the door open'), why
    assert explain_task("cool thanks!", "user", r)[0] == "quick"
    assert explain_task("make the cinema bigger and add more seats everywhere", "user", r)[0] == "general"
    mine = merged_rules({"custom": {"my_sound": {"label": "Sound"}}, "order": ["my_sound"],
                         "examples": {"my_sound": ["the explosion is too quiet"], "coding": []}})
    assert similar_task("explosions are too quiet", mine)[0] == "my_sound"
    assert mine["examples"]["coding"] == []  # the person can clear a rule's examples
    assert merged_rules({"match_confidence": 99})["match_confidence"] == 99


def test_parse_route() -> None:
    assert parse_route("anthropic:claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert parse_route("ollama:llama3:8b") == ("ollama", "llama3:8b")
    assert parse_route("") == ("", "")
    assert parse_route("tier:fast") == ("", "") and parse_route("same") == ("", "")


def test_custom_rules() -> None:
    from router import all_tasks, custom_id

    assert custom_id("Sound & music!") == "my_sound_music" and custom_id("??") == ""
    r = merged_rules({"custom": {"my_sound": {"label": "Sound"}, "evil": {"label": "x"}, "my_blank": {"label": ""}},
                      "keywords": {"my_sound": ["sfx", "music*"]}, "order": ["my_sound", "coding"]})
    assert list(r["custom"]) == ["my_sound"]  # bad id and empty name dropped
    assert r["order"][:2] == ["my_sound", "coding"] and "my_sound" in all_tasks(r)
    assert explain_task("add music to the lobby", "user", r) == ("my_sound", 'matched "music*"')
    assert r["auto_tier"]["my_sound"] == "balanced"
    gone = merged_rules({"keywords": {"my_sound": ["sfx"]}, "order": ["my_sound"]})  # rule deleted
    assert "my_sound" not in gone["order"] and "my_sound" not in gone["keywords"]


def test_a_keyless_pick_only_runs_on_a_login_that_has_the_model() -> None:
    from router import login_offering

    google = [("gemini_cli", ["auto", "pro", "flash"]),
              ("antigravity", ["auto", "gemini-3.8-flash-low", "gemini-4-neon-low"])]
    assert login_offering(google, "gemini-4-neon-low") == "antigravity"
    assert login_offering(google, "flash") == "gemini_cli"
    assert login_offering(google, "gemini-3.8-flash") == ""  # neither knows it: the API key's job
    assert login_offering(google, "") == "gemini_cli"  # no model asked: any signed-in login
    assert login_offering([], "pro") == ""


if __name__ == "__main__":
    test_a_keyless_pick_only_runs_on_a_login_that_has_the_model()
    test_custom_rules()
    test_classify()
    test_person_rules()
    test_tiers()
    test_switch_costs()
    test_cache_aware_switching()
    test_long_chats_and_windows()
    test_examples()
    test_parse_route()
    print("router ok")
