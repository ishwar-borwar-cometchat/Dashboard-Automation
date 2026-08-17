"""USR_046 - USR_051 : Add User validation.  USR_071 - USR_074 : extended (added)."""
from __future__ import annotations

import re

import pytest

from core.testdata import make_uid

SCENARIO = "Add User - Validation"
EXT_SCENARIO = "Add User - Validation (extended)"


@pytest.fixture
def modal(users):
    assert users.open_add_user(), "Clicking '+ Add User' did not open a modal"
    yield users
    try:
        if users.modal_open():
            users.close_modal_x()
        if users.modal_open():
            users.page.keyboard.press("Escape")
    except Exception:
        pass


def _assert_rejected(users, what: str):
    """Save must not succeed: either an error shows, or the modal stays open."""
    errors = users.form_errors()
    still_open = users.modal_open()
    assert errors or still_open, (
        f"{what} was accepted — modal closed with no validation error shown"
    )
    return errors


@pytest.mark.tc(id="USR_046", scenario=SCENARIO, sentiment="Negative", priority="High",
                title="Verify creating user without Name fails",
                expected="Validation error requiring Name")
def test_usr_046_missing_name(modal):
    modal.fill_user_form(uid=make_uid("noname"))
    modal.save_modal()
    _assert_rejected(modal, "A user with no Name")


@pytest.mark.tc(id="USR_047", scenario=SCENARIO, sentiment="Negative", priority="High",
                title="Verify creating user without UID fails",
                expected="Validation error requiring UID")
def test_usr_047_missing_uid(modal):
    modal.fill_user_form(name="E2E No UID")
    modal.save_modal()
    _assert_rejected(modal, "A user with no UID")


@pytest.mark.tc(id="USR_048", scenario=SCENARIO, sentiment="Negative", priority="Critical",
                title="Verify duplicate UID rejected",
                expected="Error indicating the UID already exists")
def test_usr_048_duplicate_uid(users, seeded_user):
    assert users.open_add_user(), "Add User modal did not open"
    try:
        users.fill_user_form(name="E2E Duplicate UID", uid=seeded_user)
        users.save_modal()

        errors = _assert_rejected(users, f"A second user with the existing UID {seeded_user}")
        if errors:
            assert re.search(r"exist|duplicate|taken|already", " ".join(errors), re.I), (
                f"Duplicate UID was rejected, but the message does not explain why: {errors}"
            )
    finally:
        if users.modal_open():
            users.close_modal_x()


@pytest.mark.tc(id="USR_049", scenario=SCENARIO, sentiment="Negative", priority="High",
                title="Verify invalid Metadata JSON rejected",
                expected="Validation error for invalid JSON format")
def test_usr_049_invalid_metadata(modal):
    modal.fill_user_form(name="E2E Bad JSON", uid=make_uid("badjson"), metadata="not json {{{")
    modal.save_modal()
    _assert_rejected(modal, "Metadata that is not valid JSON")


@pytest.mark.tc(id="USR_050", scenario=SCENARIO, sentiment="Negative", priority="High / Critical",
                title="Verify XSS in Name field",
                expected="Script does not execute, treated as plain text")
def test_usr_050_xss_in_name(users):
    payload = "<script>window.__xss_fired=true</script>"
    uid = make_uid("xss")

    dialogs = []
    users.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))

    assert users.open_add_user(), "Add User modal did not open"
    users.fill_user_form(name=payload, uid=uid)
    users.save_modal()

    fired = users.page.evaluate("() => !!window.__xss_fired")
    assert not fired, "SECURITY: script payload in the Name field executed"
    assert not dialogs, f"SECURITY: injected script opened a dialog: {dialogs}"

    if users.modal_open():
        users.close_modal_x()
        return  # rejected outright is also acceptable

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    row = users.row_for_uid(uid)
    if row is None:
        return

    assert not users.page.evaluate("() => !!window.__xss_fired"), (
        "SECURITY: stored payload executed when the user list rendered"
    )
    injected = users.page.locator("main script")
    assert injected.count() == 0, (
        "SECURITY: the Name value was rendered as a live <script> element, not escaped text"
    )
    # Clean up — this user is not created via user_factory.
    idx = users._row_index_for(uid)
    if idx >= 0:
        control = users.row_action(idx, 2)
        if control is not None:
            control.click()
            users.page.wait_for_timeout(800)
            users.accept_confirm()


@pytest.mark.tc(id="USR_051", scenario=SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify very long UID (500+ chars)",
                expected="Should reject or truncate, not crash")
def test_usr_051_long_uid(modal):
    long_uid = "e2e_" + ("x" * 520)
    modal.fill_user_form(name="E2E Long UID", uid=long_uid)
    modal.save_modal()

    assert not modal.visible_error_banners() or modal.modal_open(), (
        "A 500+ character UID produced an unhandled error state"
    )
    assert modal.page.locator("body").count(), "Page crashed on a 500+ character UID"


# ---------------------------------------------------------------------------
# Added during review
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_071", scenario=EXT_SCENARIO, sentiment="Negative", priority="Medium / High",
                title="Verify UID containing spaces or special characters",
                expected="Reject with a clear message, or normalise — never silently create")
def test_usr_071_uid_special_chars(users):
    raw_uid = "e2e uid@!#$%"
    assert users.open_add_user(), "Add User modal did not open"
    users.fill_user_form(name="E2E Special UID", uid=raw_uid)
    users.save_modal()

    if users.modal_open():
        users.close_modal_x()
        return  # rejected — acceptable

    users.open()
    if users.search_box() is not None:
        users.search("e2e")
    text = users.main_text()
    assert raw_uid not in text, (
        f"A UID containing spaces and special characters ({raw_uid!r}) was created verbatim "
        "with no validation or normalisation"
    )


@pytest.mark.tc(id="USR_072", scenario=EXT_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify unicode and emoji display names render correctly",
                expected="Name stored and rendered intact — no mojibake or dropped characters")
def test_usr_072_unicode_name(users, user_factory):
    name = "Ananya 日本語 😀"
    uid = user_factory(name=name)

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    row = users.row_for_uid(uid)
    assert row is not None, f"User with a unicode name was not created ({uid})"

    rendered = users.row_cells(users._row_index_for(uid))[0]
    assert "日本語" in rendered, f"Japanese characters lost or mangled: {rendered!r}"
    assert "😀" in rendered, f"Emoji lost or mangled: {rendered!r}"
    assert "?" not in rendered and "�" not in rendered, (
        f"Name shows replacement characters (mojibake): {rendered!r}"
    )


@pytest.mark.tc(id="USR_073", scenario=EXT_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify leading/trailing whitespace in Name and UID",
                expected="Values trimmed before saving, or rejected")
def test_usr_073_whitespace_trimmed(users):
    base = make_uid("trim")
    assert users.open_add_user(), "Add User modal did not open"
    users.fill_user_form(name="  E2E Trim  ", uid=f"  {base}  ")
    users.save_modal()

    if users.modal_open():
        users.close_modal_x()
        return  # rejected — acceptable

    users.open()
    if users.search_box() is not None:
        users.search(base)
    row = users.row_for_uid(base)
    assert row is not None, "User was created but cannot be found by its trimmed UID"

    cells = users.row_cells(users._row_index_for(base))
    uid_cell = next((c for c in cells if base in c), "")
    assert uid_cell.strip() == uid_cell.strip().strip(), "UID retained surrounding whitespace"
    assert not uid_cell.startswith(" ") and not uid_cell.endswith(" "), (
        f"UID was stored with surrounding whitespace: {uid_cell!r}"
    )

    idx = users._row_index_for(base)
    control = users.row_action(idx, 2)
    if control is not None:
        control.click()
        users.page.wait_for_timeout(800)
        users.accept_confirm()


@pytest.mark.tc(id="USR_074", scenario=EXT_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify Avatar and Link reject non-URL input",
                expected="Validation error for malformed URL")
def test_usr_074_invalid_url(modal):
    modal.fill_user_form(
        name="E2E Bad URL", uid=make_uid("badurl"), avatar="not-a-url", link="also not a url"
    )
    modal.save_modal()
    _assert_rejected(modal, "A malformed Avatar/Link URL")
