"""OV_035 - OV_044 : Quick Links panel.

Quick Links are div[role=button] elements whose handlers call window.open() —
they are NOT anchors, so there is no href to read. Each test clicks the link with
window.open intercepted, then asserts on the captured destination. Nothing
actually navigates, so the suite stays on the Overview page throughout.
"""
from __future__ import annotations

import re

import pytest

SCENARIO = "Overview - Quick Links"

EXPECTED_TARGET = {
    "Create Support Ticket": r"help\.cometchat\.com/hc/.*requests/new",
    "Developer Docs": r"cometchat\.com/docs",
    "API Docs": r"api-explorer\.cometchat\.com",
    "Sample Apps": r"github\.com/cometchat",
    "Help Center": r"help\.cometchat\.com",
    "Community": r"community\.cometchat\.com",
    "Product Updates": r"updates\.cometchat\.com",
    "Product Feedback": r"feedback\.cometchat\.com",
    "Status Page": r"status\.cometchat\.com",
}


def _check(overview, name: str) -> None:
    result = overview.click_quick_link(name)
    assert result.get("found"), f"Quick link '{name}' not found"

    opened = result.get("opened") or []
    assert opened, (
        f"'{name}' opened nothing — no window.open call, no navigation "
        f"(modals seen: {result.get('modals')})"
    )
    assert re.search(EXPECTED_TARGET[name], opened[0], re.I), (
        f"'{name}' opened an unexpected URL: {opened[0]}"
    )


@pytest.mark.tc(id="OV_035", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Create Support Ticket link",
                expected="Opens support ticket creation page/form")
def test_ov_035_create_support_ticket(overview):
    _check(overview, "Create Support Ticket")


@pytest.mark.tc(id="OV_036", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Developer Docs link", expected="Opens developer documentation")
def test_ov_036_developer_docs(overview):
    _check(overview, "Developer Docs")


@pytest.mark.tc(id="OV_037", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify API Docs link", expected="Opens API reference documentation")
def test_ov_037_api_docs(overview):
    _check(overview, "API Docs")


@pytest.mark.tc(id="OV_038", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Sample Apps link", expected="Opens GitHub sample apps page")
def test_ov_038_sample_apps(overview):
    _check(overview, "Sample Apps")


@pytest.mark.tc(id="OV_039", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Help Center link", expected="Opens CometChat Help Center")
def test_ov_039_help_center(overview):
    _check(overview, "Help Center")


@pytest.mark.tc(id="OV_040", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Slack Support link",
                expected="Opens Slack channel invite or join link")
def test_ov_040_slack_support(overview):
    """Slack Support is the one link that opens an in-app modal, not a URL."""
    result = overview.click_quick_link("Slack Support")
    assert result.get("found"), "Quick link 'Slack Support' not found"

    opened = result.get("opened") or []
    modals = result.get("modals") or []

    try:
        if opened:
            assert re.search(r"slack", opened[0], re.I), (
                f"Slack Support opened an unexpected URL: {opened[0]}"
            )
            return
        assert modals, "Slack Support neither opened a URL nor showed a modal"
        assert any(re.search(r"slack", m, re.I) for m in modals), (
            f"Slack Support opened a modal that is not Slack-related: {modals}"
        )
    finally:
        # Never submit the request form; just dismiss it.
        overview.close_any_modal()


@pytest.mark.tc(id="OV_041", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Community link", expected="Opens CometChat community page")
def test_ov_041_community(overview):
    _check(overview, "Community")


@pytest.mark.tc(id="OV_042", scenario=SCENARIO, sentiment="Positive", priority="Low",
                title="Verify Product Updates link", expected="Opens product updates page")
def test_ov_042_product_updates(overview):
    _check(overview, "Product Updates")


@pytest.mark.tc(id="OV_043", scenario=SCENARIO, sentiment="Positive", priority="Low",
                title="Verify Product Feedback link",
                expected="Opens feedback portal (feedback.cometchat.com)")
def test_ov_043_product_feedback(overview):
    _check(overview, "Product Feedback")


@pytest.mark.tc(id="OV_044", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Status Page link",
                expected="Opens system status page (status.cometchat.com)")
def test_ov_044_status_page(overview):
    _check(overview, "Status Page")
