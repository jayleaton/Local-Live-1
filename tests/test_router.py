from __future__ import annotations

import re

from jarvis.router.router import FastPathRule, Router, build_default_fast_paths


def _router(rules):
    return Router(fast_path_rules=rules)


def test_fast_path_matches_and_builds_call():
    rules = [FastPathRule(tool_name="demo.now", patterns=[re.compile(r"what time")])]
    plan = _router(rules).plan_fast_path("What time is it?", {"demo.now"})
    assert plan is not None and plan.kind == "tool"
    assert plan.tool_calls[0].name == "demo.now"


def test_fast_path_skips_when_tool_missing():
    rules = [FastPathRule(tool_name="demo.now", patterns=[re.compile(r"what time")])]
    assert _router(rules).plan_fast_path("what time", {"other.tool"}) is None


def test_build_default_fast_paths_detects_time_tool():
    rules = build_default_fast_paths({"demo.now"})
    plan = _router(rules).plan_fast_path("what is the time", {"demo.now"})
    assert plan is not None and plan.tool_calls[0].name == "demo.now"
