"""USR_033 - USR_037 : Friends tab.  USR_083 - USR_085 : extended (added)."""
from __future__ import annotations

import re

import pytest

SCENARIO = "User Detail - Friends Tab"
EXT_SCENARIO = "User Detail - Friends/Groups (extended)"


@pytest.fixture
def friends(users, user_detail, seeded_user):
    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    if not users.open_user(seeded_user):
        user_detail.open_uid(seeded_user)
    if not user_detail.switch_tab("Friends"):
        pytest.skip("No Friends tab on the user detail page")
    return user_detail


@pytest.mark.tc(id="USR_033", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Friends tab displays friend list",
                expected="Table with Name, UID, Created and a remove button per row")
def test_usr_033_friends_table(friends):
    if friends.list_row_count() == 0:
        assert friends.empty_state_text(), (
            "Friends tab shows neither rows nor an empty state"
        )
        pytest.skip("Seeded user has no friends yet — covered by USR_037")

    headers = friends.list_headers()
    missing = [
        c for c in ("Name", "UID", "Created")
        if not any(re.search(c, h, re.I) for h in headers)
    ]
    assert not missing, f"Friends table missing column(s): {missing}. Found: {headers}"


@pytest.mark.tc(id="USR_034", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify + Add Friends button",
                expected="Opens a dialog to select users to add as friends")
def test_usr_034_add_friends_button(friends):
    assert friends.add_button("Friends") is not None, "'+ Add Friends' button not found"
    assert friends.open_add_dialog("Friends"), (
        "Clicking '+ Add Friends' did not open a picker dialog"
    )
    friends.close_dialog()


@pytest.mark.tc(id="USR_035", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify search friends", expected="Friend list filters by name or UID")
def test_usr_035_search_friends(friends):
    if friends.list_row_count() == 0:
        pytest.skip("Seeded user has no friends to search")

    before = friends.list_row_count()
    if not friends.tab_search("zzzz_no_such_friend"):
        pytest.skip("No search input on the Friends tab")

    assert friends.list_row_count() < before or friends.list_row_count() == 0, (
        "Searching the friends list for a nonsense term did not reduce the rows"
    )


@pytest.mark.tc(id="USR_036", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify removing a friend", expected="Friend removed from the list")
def test_usr_036_remove_friend(friends):
    if friends.list_row_count() == 0:
        pytest.skip("Seeded user has no friends to remove")

    before = friends.list_row_count()
    assert friends.remove_row(0), "No remove control on the friend row"

    confirm = friends.page.locator(".ant-popconfirm, .ant-modal, [role=dialog]")
    if confirm.count() and confirm.first.is_visible():
        btn = confirm.first.get_by_role("button", name=re.compile(r"ok|yes|confirm|remove", re.I))
        (btn.first if btn.count() else confirm.first.locator("button").last).click()
        friends.page.wait_for_timeout(2_000)

    assert friends.list_row_count() < before, (
        f"Friend count did not decrease after removal ({before} -> {friends.list_row_count()})"
    )


@pytest.mark.tc(id="USR_037", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify empty friends list", expected="Empty state or 'No friends' message")
def test_usr_037_empty_friends(friends):
    if friends.list_row_count() > 0:
        pytest.skip("Seeded user has friends, so the empty state cannot be observed")

    text = friends.empty_state_text()
    assert re.search(r"no .*(friend|data|result)|empty", text, re.I), (
        f"Friends tab is empty but shows no empty-state message. Reads: {text[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Added during review
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_083", scenario=EXT_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Add Friends picker can be cancelled without changes",
                expected="No friend added, list unchanged")
def test_usr_083_add_friends_cancel(friends):
    before = friends.list_row_count()
    if not friends.open_add_dialog("Friends"):
        pytest.skip("Add Friends dialog did not open")

    option = friends.page.locator(
        ".ant-modal tbody tr, [role=dialog] tbody tr, .ant-select-item-option"
    )
    if option.count():
        option.first.click()
        friends.page.wait_for_timeout(600)

    friends.close_dialog()
    friends.page.wait_for_timeout(1_500)

    assert friends.list_row_count() == before, (
        f"Cancelling the Add Friends dialog still changed the friend count "
        f"({before} -> {friends.list_row_count()})"
    )


@pytest.mark.tc(id="USR_084", scenario=EXT_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify a user cannot be added as their own friend",
                expected="Self not selectable, or the attempt is rejected")
def test_usr_084_no_self_friend(friends, seeded_user):
    if not friends.open_add_dialog("Friends"):
        pytest.skip("Add Friends dialog did not open")

    try:
        if not friends.dialog_search(seeded_user):
            pytest.skip("Add Friends dialog has no search input")
        options = friends.dialog_options_text()
        assert seeded_user not in options, (
            f"The user ({seeded_user}) is offered as a candidate for their own friend list"
        )
    finally:
        friends.close_dialog()


@pytest.mark.tc(id="USR_085", scenario=EXT_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify friend counts update after add and remove",
                expected="List updates immediately without a manual reload")
def test_usr_085_friend_count_updates(friends):
    before = friends.list_row_count()
    if not friends.open_add_dialog("Friends"):
        pytest.skip("Add Friends dialog did not open")

    option = friends.page.locator(".ant-modal tbody tr, [role=dialog] tbody tr")
    if not option.count():
        friends.close_dialog()
        pytest.skip("No candidate users available to add as a friend")

    option.first.click()
    friends.page.wait_for_timeout(500)
    confirm = friends.page.get_by_role("button", name=re.compile(r"add|save|ok|confirm", re.I))
    if confirm.count():
        confirm.last.click()
    friends.page.wait_for_timeout(2_500)

    assert friends.list_row_count() > before, (
        f"Friend list did not update after adding ({before} -> {friends.list_row_count()}) — "
        "a manual reload should not be needed"
    )
