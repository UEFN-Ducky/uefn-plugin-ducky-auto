"""Run: py -3 -I backend/test_router.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from router import (  # noqa: E402
    DEFAULT_RULES, classify, explain_task, merged_rules, parse_route, pick_tier, rank_tier, tier_count, tier_of,
    worth_switching,
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


if __name__ == "__main__":
    test_custom_rules()
    test_classify()
    test_person_rules()
    test_tiers()
    test_switch_costs()
    test_parse_route()
    print("router ok")
