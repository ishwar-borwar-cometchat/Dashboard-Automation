"""OV_006 - OV_010 : Get Started / Integrate product cards."""
from __future__ import annotations

import re

import pytest

from pages.overview_page import PRODUCT_CARDS

SCENARIO = "Overview - Get Started / Integrate"


def _assert_card(overview, title: str) -> None:
    description = PRODUCT_CARDS[title]

    card = overview.product_card(title)
    assert card is not None, f"Product card '{title}' not found ([class*=navigationCardLink])"

    text = overview.product_card_text(title)
    assert title in text, f"Card title '{title}' missing from card text: {text!r}"
    assert re.search(re.escape(description), text, re.I), (
        f"Card description '{description}' missing from '{title}' card. Got: {text!r}"
    )
    # Icons are drawn with CSS mask-image on this dashboard, not <svg>/<img>.
    assert overview.product_card_has_icon(title), f"No icon rendered on the '{title}' card"
    assert card.get_attribute("role") == "button", (
        f"'{title}' card is not exposed as role=button"
    )


@pytest.mark.tc(id="OV_006", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Chat & Messaging card displayed",
                expected="Icon, title and description 'Real-time user to user & group chats'")
def test_ov_006_chat_messaging_card(overview):
    _assert_card(overview, "Chat & Messaging")


@pytest.mark.tc(id="OV_007", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Voice & Video Calling card displayed",
                expected="Icon, title and description 'In-app calling & conferencing'")
def test_ov_007_voice_video_card(overview):
    _assert_card(overview, "Voice & Video Calling")


@pytest.mark.tc(id="OV_008", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify AI Agents card displayed",
                expected="Icon, title and description 'Full stack AI Agents for your app'")
def test_ov_008_ai_agents_card(overview):
    _assert_card(overview, "AI Agents")


@pytest.mark.tc(id="OV_009", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify BYO Agents card displayed",
                expected="Icon, title and description 'Integrate an existing AI agent'")
def test_ov_009_byo_agents_card(overview):
    _assert_card(overview, "BYO Agents")


@pytest.mark.tc(id="OV_010", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify clicking product card navigates to that section",
                expected="Navigates to Chat & Messaging section/integration guide")
def test_ov_010_card_click_navigates(overview):
    card = overview.product_card("Chat & Messaging")
    assert card is not None, "Chat & Messaging card not found"

    before = overview.page.url
    card.click()
    overview.page.wait_for_timeout(2_500)
    after = overview.page.url

    assert after != before, "Clicking the Chat & Messaging card did not navigate"
    assert re.search(r"messaging|chat|get-?started", after, re.I), (
        f"Card navigated somewhere unexpected: {after}"
    )
