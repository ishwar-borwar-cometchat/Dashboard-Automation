"""OV_001 - OV_005 : Overview page load and dashboard header."""
from __future__ import annotations

import re

import pytest

from modules.general.overview.overview_page import HEADER_BUTTONS

SCENARIO = "Overview - Page Load"


@pytest.mark.tc(
    id="OV_001",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Critical",
    title="Verify Overview page loads successfully",
    expected="All sections visible: Get Started, Usage, Operational Data, Charts, Credentials, Quick Links",
)
def test_ov_001_overview_page_loads(raw_overview):
    ov = raw_overview.open()

    assert "/overview" in ov.page.url, f"Not on Overview URL: {ov.page.url}"

    body = ov.main_text()
    required_sections = {
        "Get Started / Integrate": r"Get Started",
        "Usage": r"Usage",
        "Operational Data": r"Operational Data",
        "Charts": r"Peak concurrent connections",
        "Credentials": r"Credentials",
        "Quick Links": r"Quick Links",
    }
    missing = [
        label for label, pattern in required_sections.items()
        if not re.search(pattern, body, re.I)
    ]
    assert not missing, f"Missing Overview sections: {missing}"


@pytest.mark.tc(
    id="OV_002",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Dashboard header buttons visible",
    expected="Get Help, App Credentials, Documentation buttons visible",
)
def test_ov_002_header_buttons_visible(overview):
    missing = [name for name in HEADER_BUTTONS if overview.header_button(name) is None]
    assert not missing, f"Header buttons not visible: {missing}"


@pytest.mark.tc(
    id="OV_003",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify Get Help button opens support",
    expected="Should open support/help page or modal",
)
def test_ov_003_get_help_opens_support(overview):
    btn = overview.header_button("Get Help")
    assert btn is not None, "'Get Help' button not found"

    before_url = overview.page.url
    popup_url = overview.new_tab_url_after(lambda: btn.click())

    if popup_url:
        assert re.search(r"help|support|docs|cometchat", popup_url, re.I), (
            f"Get Help opened an unexpected URL: {popup_url}"
        )
        return

    overview.page.wait_for_timeout(2_000)
    modal = overview.page.locator("[role='dialog'], [class*='modal' i], [class*='drawer' i]")
    navigated = overview.page.url != before_url
    modal_open = modal.count() > 0 and modal.first.is_visible()
    assert navigated or modal_open, (
        "Clicking 'Get Help' neither navigated, opened a new tab, nor opened a modal"
    )


@pytest.mark.tc(
    id="OV_004",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify App Credentials button works",
    expected="Navigates to or shows app credentials section",
)
def test_ov_004_app_credentials_button(overview):
    btn = overview.header_button("App Credentials")
    assert btn is not None, "'App Credentials' button not found"

    before_url = overview.page.url
    btn.click()
    overview.page.wait_for_timeout(2_500)

    navigated = overview.page.url != before_url
    modal = overview.page.locator("[role='dialog'], [class*='modal' i], [class*='drawer' i]")
    modal_open = modal.count() > 0 and modal.first.is_visible()
    shows_credentials = bool(
        re.search(r"App ID|Auth Key|API Key", overview.page.locator("body").inner_text(), re.I)
    )

    assert navigated or modal_open or shows_credentials, (
        "'App Credentials' click produced no credentials view"
    )


@pytest.mark.tc(
    id="OV_005",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify Documentation button opens docs",
    expected="Opens CometChat documentation in a new tab",
)
def test_ov_005_documentation_button(overview):
    btn = overview.header_button("Documentation")
    assert btn is not None, "'Documentation' button not found"

    href = None
    try:
        href = btn.locator("xpath=ancestor-or-self::a[1]").get_attribute("href", timeout=3_000)
    except Exception:
        pass

    if href:
        assert re.search(r"documentation|docs", href, re.I), f"Unexpected docs href: {href}"
        return

    popup_url = overview.new_tab_url_after(lambda: btn.click())
    assert popup_url is not None, "Documentation did not open a new tab"
    assert re.search(r"documentation|docs", popup_url, re.I), (
        f"Documentation opened unexpected URL: {popup_url}"
    )
