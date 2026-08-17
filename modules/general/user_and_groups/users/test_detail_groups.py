"""USR_038 - USR_042 : user detail Groups tab."""
from __future__ import annotations

import re

import pytest

SCENARIO = "User Detail - Groups Tab"


@pytest.fixture
def groups(users, user_detail, seeded_user):
    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    if not users.open_user(seeded_user):
        user_detail.open_uid(seeded_user)
    if not user_detail.switch_tab("Groups"):
        pytest.skip("No Groups tab on the user detail page")
    return user_detail


@pytest.mark.tc(id="USR_038", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Groups tab displays user's groups",
                expected="Table with Name, GUID, Created and a remove button per row")
def test_usr_038_groups_table(groups):
    if groups.list_row_count() == 0:
        assert groups.empty_state_text(), "Groups tab shows neither rows nor an empty state"
        pytest.skip("Seeded user belongs to no groups — covered by USR_042")

    headers = groups.list_headers()
    missing = [
        c for c in ("Name", "GUID", "Created")
        if not any(re.search(c, h, re.I) for h in headers)
    ]
    assert not missing, f"Groups table missing column(s): {missing}. Found: {headers}"


@pytest.mark.tc(id="USR_039", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify + Add Group button", expected="Opens a dialog to add user to a group")
def test_usr_039_add_group_button(groups):
    assert groups.add_button("Group") is not None, "'+ Add Group' button not found"
    assert groups.open_add_dialog("Group"), (
        "Clicking '+ Add Group' did not open a picker dialog"
    )
    groups.close_dialog()


@pytest.mark.tc(id="USR_040", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify search groups", expected="Groups list filters by name or GUID")
def test_usr_040_search_groups(groups):
    if groups.list_row_count() == 0:
        pytest.skip("Seeded user belongs to no groups to search")

    before = groups.list_row_count()
    if not groups.tab_search("zzzz_no_such_group"):
        pytest.skip("No search input on the Groups tab")

    assert groups.list_row_count() < before or groups.list_row_count() == 0, (
        "Searching the groups list for a nonsense term did not reduce the rows"
    )


@pytest.mark.tc(id="USR_041", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify removing user from group",
                expected="User removed from that group")
def test_usr_041_remove_from_group(groups):
    if groups.list_row_count() == 0:
        pytest.skip("Seeded user belongs to no groups to remove")

    before = groups.list_row_count()
    assert groups.remove_row(0), "No remove control on the group row"

    confirm = groups.page.locator(".ant-popconfirm, .ant-modal, [role=dialog]")
    if confirm.count() and confirm.first.is_visible():
        btn = confirm.first.get_by_role("button", name=re.compile(r"ok|yes|confirm|remove", re.I))
        (btn.first if btn.count() else confirm.first.locator("button").last).click()
        groups.page.wait_for_timeout(2_000)

    assert groups.list_row_count() < before, (
        f"Group count did not decrease after removal ({before} -> {groups.list_row_count()})"
    )


@pytest.mark.tc(id="USR_042", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify empty groups list", expected="Empty state displayed")
def test_usr_042_empty_groups(groups):
    if groups.list_row_count() > 0:
        pytest.skip("Seeded user belongs to groups, so the empty state cannot be observed")

    text = groups.empty_state_text()
    assert re.search(r"no .*(group|data|result)|empty", text, re.I), (
        f"Groups tab is empty but shows no empty-state message. Reads: {text[:200]!r}"
    )
