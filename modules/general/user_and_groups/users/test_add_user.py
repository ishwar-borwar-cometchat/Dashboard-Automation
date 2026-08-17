"""USR_013 - USR_024 : Add User modal.  USR_069 - USR_070 : persistence (added)."""
from __future__ import annotations

import re

import pytest

from core.testdata import make_uid
from modules.general.user_and_groups.users.users_page import ADD_USER_FIELDS

SCENARIO = "Add User - Modal"
PERSIST_SCENARIO = "Add User - Persistence"


@pytest.fixture
def modal(users):
    """Open the Add User modal, and always close it afterwards."""
    assert users.open_add_user(), "Clicking '+ Add User' did not open a modal"
    yield users
    try:
        users.close_modal_x()
        if users.modal_open():
            users.cancel_modal()
        if users.modal_open():
            users.page.keyboard.press("Escape")
    except Exception:
        pass


@pytest.mark.tc(id="USR_013", scenario=SCENARIO, sentiment="Positive", priority="Critical",
                title="Verify Add New User modal opens",
                expected="Modal opens titled 'Add New User' with form fields")
def test_usr_013_modal_opens(modal):
    assert modal.modal_open(), "Add User modal is not visible"
    title = modal.modal_title()
    assert re.search(r"add .*user", title, re.I), (
        f"Modal title is {title!r}, expected something like 'Add New User'"
    )
    assert modal.modal().locator("input, textarea").count() >= 2, (
        "Modal opened but contains fewer than 2 form fields"
    )


def _assert_field(modal, key: str, label: str):
    field = modal.modal_field(key)
    assert field is not None, (
        f"{label} field not found. Expected placeholder {ADD_USER_FIELDS[key]!r}. "
        f"Placeholders present: {modal.modal_placeholders()}"
    )
    assert field.is_visible(), f"{label} field is present but not visible"


@pytest.mark.tc(id="USR_014", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Name field present and required",
                expected="Name input with placeholder 'Enter user name'")
def test_usr_014_name_field(modal):
    _assert_field(modal, "name", "Name")


@pytest.mark.tc(id="USR_015", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify UID field present", expected="UID input with placeholder 'Enter UID'")
def test_usr_015_uid_field(modal):
    _assert_field(modal, "uid", "UID")


@pytest.mark.tc(id="USR_016", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Role dropdown with Default Role",
                expected="Role dropdown showing 'Default Role', other roles available")
def test_usr_016_role_dropdown(modal):
    select = modal.role_select()
    assert select is not None, "No Role dropdown found in the Add User modal"
    assert re.search(r"default", select.inner_text(), re.I), (
        f"Role dropdown does not default to 'Default Role'. Shows: {select.inner_text()!r}"
    )


@pytest.mark.tc(id="USR_017", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Tags field present", expected="Tags input with placeholder 'Add a tag'")
def test_usr_017_tags_field(modal):
    _assert_field(modal, "tags", "Tags")


@pytest.mark.tc(id="USR_018", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Avatar URL field present",
                expected="Avatar URL input with example.com placeholder")
def test_usr_018_avatar_field(modal):
    _assert_field(modal, "avatar", "Avatar URL")


@pytest.mark.tc(id="USR_019", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Link URL field present",
                expected="Link URL input with example.com/profile placeholder")
def test_usr_019_link_field(modal):
    _assert_field(modal, "link", "Link URL")


@pytest.mark.tc(id="USR_020", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Metadata JSON field present",
                expected="Metadata textarea with placeholder 'Enter JSON data'")
def test_usr_020_metadata_field(modal):
    _assert_field(modal, "metadata", "Metadata")


@pytest.mark.tc(id="USR_021", scenario=SCENARIO, sentiment="Positive", priority="Critical",
                title="Verify creating user with required fields only",
                expected="User created and appears in the users list")
def test_usr_021_create_minimal(users, user_factory):
    uid = user_factory(name="E2E Minimal")

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    assert users.row_for_uid(uid) is not None, (
        f"User {uid} was not found in the list after creation. "
        f"Errors shown: {users.form_errors()}"
    )


@pytest.mark.tc(id="USR_022", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify creating user with all fields filled",
                expected="User created with all provided details")
def test_usr_022_create_full(users, user_factory):
    uid = user_factory(
        name="E2E Full Profile",
        tags="qa",
        avatar="https://example.com/avatar.png",
        link="https://example.com/profile",
        metadata='{"team":"qa"}',
    )

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    assert users.row_for_uid(uid) is not None, (
        f"User {uid} created with all fields was not found in the list"
    )


@pytest.mark.tc(id="USR_023", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Cancel button closes modal without saving",
                expected="Modal closes, no user created")
def test_usr_023_cancel_button(users):
    assert users.open_add_user(), "Add User modal did not open"

    uid = make_uid("cancelled")
    users.fill_user_form(name="E2E Cancelled", uid=uid)
    users.cancel_modal()

    assert not users.modal_open(), "Modal is still open after clicking Cancel"

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    assert users.row_for_uid(uid) is None, (
        f"Cancelling the modal still created user {uid}"
    )


@pytest.mark.tc(id="USR_024", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify X button closes modal",
                expected="Modal closes without creating user")
def test_usr_024_close_x(users):
    assert users.open_add_user(), "Add User modal did not open"

    uid = make_uid("closed")
    users.fill_user_form(name="E2E Closed", uid=uid)
    users.close_modal_x()

    assert not users.modal_open(), "Modal is still open after clicking the X"

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    assert users.row_for_uid(uid) is None, f"Closing via X still created user {uid}"


# ---------------------------------------------------------------------------
# Added during review
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_069", scenario=PERSIST_SCENARIO, sentiment="Positive",
                priority="High / Critical",
                title="Verify newly created user persists after reload",
                expected="User still present after reload — persisted server-side")
def test_usr_069_create_persists(users, user_factory):
    uid = user_factory(name="E2E Persist")

    users.page.reload(wait_until="domcontentloaded")
    users.page.wait_for_timeout(3_000)
    users.open()
    if users.search_box() is not None:
        users.search(uid)

    assert users.row_for_uid(uid) is not None, (
        f"User {uid} disappeared after a page reload — it was added to local state "
        "but not persisted server-side"
    )


@pytest.mark.tc(id="USR_070", scenario=PERSIST_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify duplicate Name is accepted when UID differs",
                expected="User created — only UID must be unique")
def test_usr_070_duplicate_name_allowed(users, user_factory):
    shared_name = "E2E Duplicate Name"
    first = user_factory(name=shared_name)
    second = user_factory(name=shared_name)

    users.open()
    for uid in (first, second):
        if users.search_box() is not None:
            users.search(uid)
        assert users.row_for_uid(uid) is not None, (
            f"User {uid} sharing a display name with another user was not created — "
            "name uniqueness should not be enforced, only UID"
        )
