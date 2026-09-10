"""CHF_002 : Core features are always-on and cannot be toggled."""
from __future__ import annotations

import pytest

SCENARIO = "Chat & Messaging - Features - Core Features"

CORE_FEATURES = [
    "Instant Messaging",
    "Media Sharing",
    "Read Receipts",
    "Mark as Unread",
    "Typing Indicators",
    "User Presence",
    "Reactions",
    "Mentions",
    "Threaded Conversations",
    "Quoted replies",
    "Group Chats",
    "Report Message",
]

# VERIFIED against the live DOM on 2 Sep 2026: unlike the 12 features above,
# this one's switch carries no `disabled` attribute — it is grouped under CORE
# but is actually clickable. Tracked as its own case rather than folded into
# the "always locked" assertion below. Not included in the extension toggle
# suite: it isn't an extension, and flipping "off" a feature described as core
# search behaviour is out of scope for this suite to do live.
CORE_BUT_TOGGLEABLE = "Conversation and Advanced Search"


@pytest.mark.tc(
    id="CHF_002",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify every CORE feature is enabled and its switch is locked",
    expected="All 12 core features show an on switch that is disabled (not clickable)",
)
def test_chf_002_core_features_locked_on(chat_features):
    missing = [name for name in CORE_FEATURES if not chat_features.exists(name)]
    assert not missing, f"Core features not found on the page: {missing}"

    not_on = [name for name in CORE_FEATURES if not chat_features.is_enabled(name)]
    assert not not_on, f"Core features rendered as off: {not_on}"

    not_locked = [name for name in CORE_FEATURES if not chat_features.is_locked(name)]
    assert not not_locked, f"Core features have a clickable (non-disabled) switch: {not_locked}"


@pytest.mark.tc(
    id="CHF_027",
    scenario=SCENARIO,
    sentiment="Negative",
    priority="Medium",
    title="Verify 'Conversation and Advanced Search' is inconsistently interactive for a CORE feature",
    expected=(
        "Flagged as a UI inconsistency: every other CORE feature renders a disabled "
        "(locked) switch, but this one is a live, clickable toggle despite being "
        "grouped under CORE alongside features that cannot be turned off"
    ),
)
def test_chf_027_advanced_search_switch_is_not_locked(chat_features):
    assert chat_features.exists(CORE_BUT_TOGGLEABLE), f"{CORE_BUT_TOGGLEABLE} not found on the page"
    assert chat_features.is_enabled(CORE_BUT_TOGGLEABLE), f"{CORE_BUT_TOGGLEABLE} is rendered off"
    assert not chat_features.is_locked(CORE_BUT_TOGGLEABLE), (
        f"{CORE_BUT_TOGGLEABLE}'s switch is now disabled/locked like the other CORE features — "
        "this test documented an inconsistency that may have been fixed; if so, move it back "
        "into CORE_FEATURES in this file"
    )
