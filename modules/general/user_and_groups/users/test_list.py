"""USR_001 - USR_007 : Users list display."""
from __future__ import annotations

import re

import pytest

from modules.general.user_and_groups.users.users_page import TABLE_COLUMNS, TABS

SCENARIO = "Users List - Display"


@pytest.mark.tc(id="USR_001", scenario=SCENARIO, sentiment="Positive", priority="Critical",
                title="Verify Users list page loads with table",
                expected="Table with columns: Name, UID, Role ID, Created, Actions")
def test_usr_001_users_list_loads(raw_users):
    up = raw_users.open()

    assert "/users" in up.page.url, f"Not on the Users URL: {up.page.url}"
    assert up.has_table(), (
        f"No users table rendered. Page shows: {up.main_text()[:200]!r}"
    )

    headers = up.column_headers()
    assert headers, "Users table rendered no column headers"
    missing = [
        col for col in TABLE_COLUMNS
        if not any(re.search(re.escape(col), h, re.I) for h in headers)
    ]
    assert not missing, f"Missing table column(s): {missing}. Found: {headers}"


@pytest.mark.tc(id="USR_002", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Active Users tab is default",
                expected="'Active Users' tab selected by default")
def test_usr_002_active_tab_default(users):
    tabs = users.tabs()
    assert tabs, "No tabs found on the Users page"
    assert any(re.search("active", t, re.I) for t in tabs), (
        f"No 'Active Users' tab present. Tabs: {tabs}"
    )

    active = users.active_tab()
    assert active, "No tab is marked active"
    assert re.search("active", active, re.I), (
        f"Default selected tab is {active!r}, expected 'Active Users'"
    )


@pytest.mark.tc(id="USR_003", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Deactivated Users tab displays deactivated users",
                expected="Table shows only deactivated/disabled users")
def test_usr_003_deactivated_tab(users):
    tabs = users.tabs()
    assert any(re.search("deactivat", t, re.I) for t in tabs), (
        f"No 'Deactivated Users' tab present. Tabs: {tabs}"
    )

    active_uids = set(users.column_values("UID"))
    users.switch_tab("Deactivated")

    assert re.search("deactivat", users.active_tab() or "", re.I), (
        "Clicking 'Deactivated Users' did not activate that tab"
    )

    deactivated_uids = set(users.column_values("UID"))
    if not deactivated_uids:
        assert users.empty_state_text() or users.row_count() == 0, (
            "Deactivated tab shows neither rows nor an empty state"
        )
        return

    overlap = active_uids & deactivated_uids
    assert not overlap, (
        f"{len(overlap)} user(s) appear in BOTH Active and Deactivated tabs: {sorted(overlap)[:5]}"
    )


@pytest.mark.tc(id="USR_004", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify user row shows avatar, name, UID, role, date",
                expected="Row shows avatar, Name, UID, Role ID, Created date, Actions")
def test_usr_004_row_content(users):
    if users.row_count() == 0:
        pytest.skip("No users exist in this app, so row content cannot be verified")

    cells = users.row_cells(0)
    assert len(cells) >= 4, f"Row has only {len(cells)} cells: {cells}"

    populated = [c for c in cells if c.strip()]
    assert len(populated) >= 3, f"Row is mostly empty: {cells}"

    assert users.row_has_avatar(0), "First user row renders no avatar image or placeholder"

    created = users.column_values("Created")
    assert created and created[0].strip(), "Created column is empty for the first row"


@pytest.mark.tc(id="USR_005", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify Actions column has view/deactivate/delete icons",
                expected="Eye (view), deactivate and delete (trash) icons present")
def test_usr_005_action_icons(users):
    if users.row_count() == 0:
        pytest.skip("No users exist in this app, so row actions cannot be verified")

    count = users.row_action_controls(0)
    assert count >= 3, (
        f"Expected at least 3 action controls (view / deactivate / delete), found {count}"
    )


@pytest.mark.tc(id="USR_006", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify + Add User button is visible",
                expected="'+ Add User' button visible")
def test_usr_006_add_user_button(users):
    btn = users.add_user_button()
    assert btn is not None, "'+ Add User' button not found on the Users page"
    assert btn.is_visible(), "'+ Add User' button is present but not visible"


@pytest.mark.tc(id="USR_007", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify Filter button is visible",
                expected="Filter button visible next to Add User")
def test_usr_007_filter_button(users):
    btn = users.filter_button()
    assert btn is not None, "Filter control not found on the Users page"
    assert btn.is_visible(), "Filter control is present but not visible"
