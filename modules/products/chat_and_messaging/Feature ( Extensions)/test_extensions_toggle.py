"""CHF_003 - CHF_026 : enable/disable round-trip for every Features extension.

Each case flips one extension to the opposite of whatever state it started in,
confirms the switch and the confirmation toast agree, then flips it back — so
every extension is exercised in both directions without permanently changing
the app's configuration. `restore_extension_state` (module conftest) is a
second, independent safety net in case a mid-test assertion fails before the
second toggle runs.

Extension names/categories are VERIFIED against the live DOM on 2 Sep 2026 —
see the Features page inventory. Casing is copied exactly as rendered, since
the switch's aria-label must match the display name byte-for-byte.
"""
from __future__ import annotations

import pytest

SCENARIO = "Chat & Messaging - Features - Extension Toggle"

# (display name, category) — display name doubles as the aria-label key.
EXTENSIONS = [
    ("Bitly", "User Experience"),
    ("Link Preview", "User Experience"),
    ("Message shortcuts", "User Experience"),
    ("Pin Message", "User Experience"),
    ("Rich Media Preview", "User Experience"),
    ("Save Message", "User Experience"),
    ("Thumbnail Generation", "User Experience"),
    ("TinyURL", "User Experience"),
    ("Voice Transcription", "User Experience"),
    ("Giphy", "User Engagement"),
    ("Message Translation", "User Engagement"),
    ("Polls", "User Engagement"),
    ("Reminders", "User Engagement"),
    ("Stickers", "User Engagement"),
    ("Stipop", "User Engagement"),
    ("Tenor", "User Engagement"),
    ("Collaborative document", "Collaboration"),
    ("Collaborative whiteboard", "Collaboration"),
    ("Disappearing messages", "Security"),
    ("Chatwoot", "Customer Support"),
    ("Intercom", "Customer Support"),
    # Smart Chat Features (Conversation Starter, Smart Replies, Conversation
    # Summary) are deliberately excluded here: VERIFIED live that enabling any
    # of them opens a blocking "AI Feature Requires AI Settings to Be Enabled"
    # modal instead of toggling, on an app with no AI Settings configured. They
    # cannot complete this round trip and get their own gate-behavior cases in
    # test_smart_chat_features_gate.py instead.
]


def _params():
    for i, (name, category) in enumerate(EXTENSIONS, start=3):
        marker = pytest.mark.tc(
            id=f"CHF_{i:03d}",
            scenario=SCENARIO,
            sentiment="Positive",
            priority="High",
            title=f"Verify enabling and disabling {name} ({category})",
            expected=(
                f"{name} toggles to the opposite state with a matching confirmation "
                f"toast, then toggles back to its original state"
            ),
        )
        yield pytest.param(name, category, id=name.replace(" ", "_"), marks=marker)


@pytest.mark.parametrize("name,category", list(_params()))
def test_extension_toggle_roundtrip(chat_features, restore_extension_state, name, category):
    assert chat_features.exists(name), f"{name} ({category}) not found on the Features page"
    restore_extension_state(name)

    started_enabled = chat_features.is_enabled(name)
    target = not started_enabled

    # --- toggle away from the starting state ---
    chat_features.toggle(name)
    chat_features.wait_for_state(name, target)
    assert chat_features.is_enabled(name) is target, (
        f"{name} switch did not reach {'On' if target else 'Off'} after toggling"
    )

    toast = chat_features.toast_text()
    verb = "enabled" if target else "disabled"
    assert toast and name in toast and verb in toast.lower(), (
        f"No confirmation toast naming {name} and '{verb}' after toggling. Saw: {toast!r}"
    )

    # --- toggle back to the starting state ---
    chat_features.toggle(name)
    chat_features.wait_for_state(name, started_enabled)
    assert chat_features.is_enabled(name) is started_enabled, (
        f"{name} did not return to its original state after the second toggle"
    )
