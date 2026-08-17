"""USR_025 - USR_032 : user detail General tab.
USR_075 - USR_076 : edit persistence.  USR_081 - USR_082 : auth-token security. (added)"""
from __future__ import annotations

import re

import pytest

from pages.user_detail_page import DETAIL_FIELDS

SCENARIO = "User Detail - General Tab"
EDIT_SCENARIO = "User Detail - Edit Persistence"
TOKEN_SCENARIO = "User Detail - Auth Token Security"


@pytest.fixture
def detail(users, user_detail, seeded_user):
    """A disposable user's detail page, opened."""
    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    if not users.open_user(seeded_user):
        user_detail.open_uid(seeded_user)
    return user_detail


@pytest.mark.tc(id="USR_025", scenario=SCENARIO, sentiment="Positive", priority="Critical",
                title="Verify user detail page opens with General tab",
                expected="Detail page shows General tab with user name and avatar in header")
def test_usr_025_detail_opens(detail, seeded_user):
    assert seeded_user in detail.page.url or seeded_user in detail.main_text(), (
        f"Detail page does not appear to be for {seeded_user}. URL: {detail.page.url}"
    )

    tabs = detail.tabs()
    assert any(re.search("general", t, re.I) for t in tabs), (
        f"No General tab on the user detail page. Tabs: {tabs}"
    )
    active = detail.active_tab()
    assert active and re.search("general", active, re.I), (
        f"General is not the default tab (active: {active!r})"
    )


@pytest.mark.tc(id="USR_026", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify back arrow navigates to users list",
                expected="Navigates back to the users list")
def test_usr_026_back_arrow(detail):
    assert detail.go_back(), "No back control found on the user detail page"
    assert re.search(r"/users/?$", detail.page.url), (
        f"Back did not return to the users list. Landed on: {detail.page.url}"
    )


@pytest.mark.tc(id="USR_027", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Details card shows all user info",
                expected="Name, UID, Role ID, Tags, Avatar, Link, Metadata, Created")
def test_usr_027_details_card(detail):
    present = detail.detail_labels_present()
    missing = [f for f in DETAIL_FIELDS if f not in present]
    assert not missing, (
        f"Details card is missing field label(s): {missing}. Present: {present}"
    )


@pytest.mark.tc(id="USR_028", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Edit button on Details card",
                expected="Allows editing name, role, tags, avatar, link, metadata")
def test_usr_028_edit_button(detail):
    assert detail.edit_button() is not None, "No Edit button on the Details card"
    assert detail.click_edit(), "Edit button could not be clicked"

    editable = detail.page.locator("input:visible, textarea:visible")
    assert editable.count() >= 2, (
        f"Clicking Edit exposed only {editable.count()} editable field(s)"
    )


@pytest.mark.tc(id="USR_029", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Auth Tokens section displayed",
                expected="Auth Tokens section with table and '+ Create Auth Token' button")
def test_usr_029_auth_tokens_section(detail):
    assert detail.auth_tokens_visible(), "No 'Auth Tokens' section on the General tab"
    assert detail.create_token_button() is not None, (
        "'+ Create Auth Token' button not found in the Auth Tokens section"
    )


@pytest.mark.tc(id="USR_030", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Create Auth Token button",
                expected="New auth token generated and shown in the tokens table")
def test_usr_030_create_token(detail):
    before = detail.token_row_count()
    assert detail.create_token(), "'+ Create Auth Token' button not found"

    after = detail.token_row_count()
    assert after > before, (
        f"Token count did not increase after clicking Create ({before} -> {after})"
    )


@pytest.mark.tc(id="USR_031", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify copy auth token", expected="Token string copied to clipboard")
def test_usr_031_copy_token(detail):
    if detail.token_row_count() == 0:
        assert detail.create_token(), "Could not create a token to copy"

    detail.page.evaluate(
        """() => {
             window.__clip = [];
             if (navigator.clipboard) {
               navigator.clipboard.writeText = v => {
                 window.__clip.push(String(v));
                 return Promise.resolve();
               };
             }
           }"""
    )

    assert detail.copy_token(0), "No copy control found on the token row"

    clips = detail.page.evaluate("() => window.__clip || []")
    assert clips, "Clicking copy wrote nothing to the clipboard"
    assert re.fullmatch(r"[A-Za-z0-9._\-]{16,}", clips[-1].strip()), (
        f"Clipboard value does not look like an auth token ({len(clips[-1])} chars)"
    )


@pytest.mark.tc(id="USR_032", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify delete auth token", expected="Token removed from the list")
def test_usr_032_delete_token(detail):
    if detail.token_row_count() == 0:
        assert detail.create_token(), "Could not create a token to delete"

    before = detail.token_row_count()
    assert detail.delete_token(0), "No delete control found on the token row"

    confirm = detail.page.locator(".ant-popconfirm, .ant-modal, [role=dialog]")
    if confirm.count() and confirm.first.is_visible():
        btn = confirm.first.get_by_role("button", name=re.compile(r"ok|yes|confirm|delete", re.I))
        (btn.first if btn.count() else confirm.first.locator("button").last).click()
        detail.page.wait_for_timeout(2_000)

    assert detail.token_row_count() < before, (
        f"Token count did not decrease after delete ({before} -> {detail.token_row_count()})"
    )


# ---------------------------------------------------------------------------
# Added during review — edit persistence
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_075", scenario=EDIT_SCENARIO, sentiment="Positive",
                priority="High / Critical",
                title="Verify edited details persist after save and reload",
                expected="Edited values still shown after reload")
def test_usr_075_edit_persists(detail):
    assert detail.click_edit(), "Could not enter edit mode"

    new_name = "E2E Edited Name"
    name_input = detail.page.locator("input:visible").first
    name_input.fill(new_name)

    save = detail.page.get_by_role("button", name=re.compile(r"save|update|confirm", re.I))
    assert save.count(), "No Save control in edit mode"
    save.first.click()
    detail.page.wait_for_timeout(2_500)

    detail.page.reload(wait_until="domcontentloaded")
    detail.page.wait_for_timeout(3_000)

    assert new_name in detail.main_text(), (
        f"Edited name {new_name!r} did not survive a reload — the change was not persisted"
    )


@pytest.mark.tc(id="USR_076", scenario=EDIT_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify cancelling an edit discards changes",
                expected="Original values retained, changes discarded")
def test_usr_076_edit_cancel(detail):
    original = detail.main_text()
    assert detail.click_edit(), "Could not enter edit mode"

    detail.page.locator("input:visible").first.fill("E2E Discarded Name")

    cancel = detail.page.get_by_role("button", name=re.compile(r"cancel", re.I))
    if not cancel.count():
        pytest.skip("Edit mode exposes no Cancel control")
    cancel.first.click()
    detail.page.wait_for_timeout(2_000)

    assert "E2E Discarded Name" not in detail.main_text(), (
        "Cancelling the edit still applied the changed name"
    )


# ---------------------------------------------------------------------------
# Added during review — auth token security (mirrors the OV_052 defect)
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_081", scenario=TOKEN_SCENARIO, sentiment="Negative",
                priority="High / Critical",
                title="Verify auth token is not exposed in the DOM while masked",
                expected="Token absent from DOM/page source while displayed masked")
def test_usr_081_token_not_in_dom(detail):
    if detail.token_row_count() == 0:
        assert detail.create_token(), "Could not create a token to inspect"

    if not detail.token_is_masked(0):
        pytest.skip(
            "Tokens are displayed in full by default on this page, so there is no masked "
            "state to defeat — see USR_082, which covers whether masking exists at all"
        )

    hidden = detail.token_hidden_nodes()
    assert hidden == 0, (
        f"SECURITY: {hidden} hidden node(s) in the Auth Tokens section contain token-shaped "
        "text while the token displays as masked. This is the same defect found on the "
        "Overview module (OV_052), where the Auth Key sat in a display:none div."
    )

    runs = detail.token_plaintext_in_dom()
    assert not runs, (
        f"SECURITY: the Auth Tokens markup contains {len(runs)} token-length alphanumeric "
        f"run(s) (lengths {runs}) while the token is masked — readable without revealing it."
    )


@pytest.mark.tc(id="USR_082", scenario=TOKEN_SCENARIO, sentiment="Negative", priority="High",
                title="Verify auth token is masked by default in the tokens table",
                expected="Token masked or truncated by default, with an explicit reveal control")
def test_usr_082_token_masked_by_default(detail):
    if detail.token_row_count() == 0:
        assert detail.create_token(), "Could not create a token to inspect"

    assert detail.token_is_masked(0), (
        "Auth token is rendered in full in the tokens table with no masking or truncation — "
        "anyone glancing at the screen or a screenshare can read a live credential"
    )
