"""CHF_024 - CHF_026 : Smart Chat Features are gated behind AI Settings.

VERIFIED live on 2 Sep 2026: on an app with no AI Settings configured,
attempting to enable any Smart Chat Feature does not toggle it. Instead a
blocking modal reads "AI Feature Requires AI Settings to Be Enabled" and
offers a "Configure AI Settings" button. The switch never leaves Off. These
three therefore get gate-behavior cases here instead of the enable/disable
round trip in test_extensions_toggle.py, which they cannot complete on this
app.
"""
from __future__ import annotations

import pytest

SCENARIO = "Chat & Messaging - Features - Smart Chat Features AI Gate"

SMART_CHAT_FEATURES = [
    "Conversation Starter",
    "Smart Replies",
    "Conversation Summary",
]


def _params():
    for i, name in enumerate(SMART_CHAT_FEATURES, start=24):
        marker = pytest.mark.tc(
            id=f"CHF_{i:03d}",
            scenario=SCENARIO,
            sentiment="Negative",
            priority="Medium",
            title=f"Verify {name} cannot be enabled without AI Settings configured",
            expected=(
                "Clicking the switch does not enable it; a modal explains AI Settings "
                "must be configured first, and the switch remains Off after the modal "
                "is dismissed"
            ),
        )
        yield pytest.param(name, id=name.replace(" ", "_"), marks=marker)


@pytest.mark.parametrize("name", list(_params()))
def test_smart_chat_feature_requires_ai_settings(chat_features, name):
    assert chat_features.exists(name), f"{name} not found on the Features page"
    assert not chat_features.is_enabled(name), (
        f"{name} is already enabled — this app must have AI Settings configured; "
        "this case only applies while it does not"
    )

    chat_features.toggle(name)

    assert chat_features.modal_visible(), (
        f"Enabling {name} without AI Settings configured showed no gating modal "
        "and no toast — the switch may have silently failed instead of explaining why"
    )
    modal_text = chat_features.modal_text()
    assert "AI Settings" in modal_text, (
        f"Gating modal for {name} does not mention AI Settings. Saw: {modal_text!r}"
    )
    chat_features.close_modal()

    assert not chat_features.is_enabled(name), (
        f"{name} switch shows enabled after the AI Settings gate was dismissed"
    )
