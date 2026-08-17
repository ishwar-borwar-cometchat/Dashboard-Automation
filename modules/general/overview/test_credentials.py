"""OV_011 - OV_017 : Credentials panel.  OV_051 - OV_052 : credentials security."""
from __future__ import annotations

import re

import pytest

from modules.general.overview.overview_page import VALID_REGIONS, OverviewPage

SCENARIO = "Overview - Credentials Panel"
SECURITY_SCENARIO = "Overview - Credentials Security"


@pytest.mark.tc(id="OV_011", scenario=SCENARIO, sentiment="Positive", priority="Critical",
                title="Verify App ID is displayed", expected="App ID shown in Credentials panel")
def test_ov_011_app_id_displayed(overview, app_config):
    value = overview.app_id_value()
    assert value, "App ID not rendered in the Credentials panel"
    assert re.fullmatch(r"[A-Za-z0-9]{8,}", value), f"App ID looks malformed: {value!r}"
    assert value == app_config["app_id"], (
        f"App ID mismatch — page shows {value!r}, expected {app_config['app_id']!r}"
    )


@pytest.mark.tc(id="OV_012", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Region is displayed", expected="Region shows US / EU / IN / LONDON")
def test_ov_012_region_displayed(overview):
    value = overview.region_value()
    assert value, "Region not rendered"
    assert value.upper() in VALID_REGIONS, f"Unexpected region: {value!r}"


@pytest.mark.tc(id="OV_013", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Auth Key is displayed (masked)",
                expected="Auth Key masked with asterisks")
def test_ov_013_auth_key_masked(overview):
    shown = overview.auth_key_visible()
    assert shown, "Auth Key row not rendered"
    assert OverviewPage.is_masked(shown), (
        f"Auth Key is not masked — visible node contains alphanumerics ({len(shown)} chars)"
    )


@pytest.mark.tc(id="OV_014", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Auth Key show/hide toggle",
                expected="Auth Key toggles between visible and masked")
def test_ov_014_auth_key_toggle(overview):
    toggle = overview.auth_key_toggle()
    assert toggle is not None, "No reveal (eye) control found on the Auth Key row"

    masked = overview.auth_key_visible()
    assert OverviewPage.is_masked(masked), "Auth Key was not masked to begin with"

    toggle.click()
    overview.page.wait_for_timeout(800)
    revealed = overview.auth_key_visible()
    assert not OverviewPage.is_masked(revealed), "Auth Key did not reveal after clicking the toggle"
    assert re.fullmatch(r"[A-Za-z0-9]{16,}", revealed or ""), (
        "Revealed value does not look like an Auth Key"
    )

    toggle.click()
    overview.page.wait_for_timeout(800)
    assert OverviewPage.is_masked(overview.auth_key_visible()), (
        "Auth Key did not return to its masked state"
    )


@pytest.mark.tc(id="OV_015", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Copy App ID button", expected="App ID copied to clipboard")
def test_ov_015_copy_app_id(overview, app_config):
    overview.reset_capture()
    btn = overview.app_id_copy()
    assert btn is not None, "No copy control on the App ID row"

    btn.click()
    overview.page.wait_for_timeout(800)

    clips = overview.captured_clips()
    assert clips, "Clicking copy on App ID wrote nothing to the clipboard"
    assert clips[-1].strip() == app_config["app_id"], (
        f"Clipboard received {clips[-1]!r}, expected the App ID"
    )


@pytest.mark.tc(id="OV_016", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Copy Auth Key button", expected="Auth Key copied to clipboard")
def test_ov_016_copy_auth_key(overview):
    overview.reset_capture()
    btn = overview.auth_key_copy()
    assert btn is not None, "No copy control on the Auth Key row"

    btn.click()
    overview.page.wait_for_timeout(800)

    clips = overview.captured_clips()
    assert clips, "Clicking copy on Auth Key wrote nothing to the clipboard"
    copied = clips[-1].strip()
    assert not OverviewPage.is_masked(copied), "Clipboard received the masked value, not the key"
    assert re.fullmatch(r"[A-Za-z0-9]{16,}", copied), (
        f"Clipboard value is not key-shaped ({len(copied)} chars)"
    )


@pytest.mark.tc(id="OV_017", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify View All credentials link",
                expected="Navigates to full credentials page")
def test_ov_017_view_all_link(overview):
    link = overview.view_all_link()
    assert link is not None, "'View All' link not found"

    before = overview.page.url
    link.click()
    overview.page.wait_for_timeout(2_500)

    assert overview.page.url != before, "'View All' did not navigate"
    assert re.search(r"credential", overview.page.url, re.I), (
        f"'View All' went somewhere unexpected: {overview.page.url}"
    )


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="OV_051", scenario=SECURITY_SCENARIO, sentiment="Negative", priority="Critical",
                title="Verify Auth Key masked by default",
                expected="Auth Key masked on load, not plain text")
def test_ov_051_auth_key_masked_by_default(raw_overview):
    ov = raw_overview.open()
    shown = ov.auth_key_visible()
    assert shown, "Auth Key row not rendered"
    assert OverviewPage.is_masked(shown), f"Auth Key exposed in plain text on load ({len(shown)} chars)"


@pytest.mark.tc(id="OV_052", scenario=SECURITY_SCENARIO, sentiment="Negative",
                priority="High / Critical",
                title="Verify credentials not exposed in page source",
                expected="Auth Key not present in plain text in the DOM before revealing")
def test_ov_052_auth_key_not_in_page_source(raw_overview):
    """KNOWN DEFECT as of 2026-08-17.

    The Auth Key row renders the mask in .style_credentialItemLeft and the REAL key
    in a display:none .style_credentialItemRight sibling, so the plaintext key is in
    the DOM at all times. This test is expected to fail until that is fixed.
    """
    ov = raw_overview.open()

    visible = ov.auth_key_visible()
    assert OverviewPage.is_masked(visible), "Precondition failed: Auth Key not masked on load"

    hidden = ov.auth_key_hidden_plaintext()
    assert not (hidden and re.search(r"[A-Za-z0-9]{16,}", hidden)), (
        "SECURITY: the real Auth Key is rendered into a hidden sibling node while the "
        "field displays as masked — it is readable from the DOM without revealing it."
    )

    card_html = ov.credentials_card_html()
    runs = [r for r in re.findall(r"[A-Za-z0-9]{25,}", card_html)]
    assert not runs, (
        f"SECURITY: credentials card markup contains {len(runs)} key-length alphanumeric "
        f"run(s) (lengths {[len(r) for r in runs]}) while the Auth Key is masked."
    )
