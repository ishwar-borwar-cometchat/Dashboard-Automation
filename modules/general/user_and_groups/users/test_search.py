"""USR_056 - USR_060 : Users list search (added during review — absent from the original sheet)."""
from __future__ import annotations

import re

import pytest

SCENARIO = "Users List - Search"


@pytest.mark.tc(id="USR_056", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify searching users by name",
                expected="Table filters to users whose name matches the search term")
def test_usr_056_search_by_name(users, seeded_user):
    users.open()
    row = users.row_for_uid(seeded_user)
    if row is None:
        users.search(seeded_user)
        row = users.row_for_uid(seeded_user)
    assert row is not None, f"Seeded user {seeded_user} not present before searching"

    name = users.row_cells(users._row_index_for(seeded_user))[0].strip().splitlines()[0]
    users.clear_search()
    users.search(name)

    assert users.row_count() > 0, f"Searching for name {name!r} returned no rows"
    values = " ".join(users.column_values("Name")).lower()
    assert name.lower()[:8] in values, (
        f"Search for {name!r} returned rows that do not contain it: {users.column_values('Name')[:5]}"
    )


@pytest.mark.tc(id="USR_057", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify searching users by UID",
                expected="Table filters to the user with that UID")
def test_usr_057_search_by_uid(users, seeded_user):
    users.open()
    users.search(seeded_user)

    uids = users.column_values("UID")
    assert uids, f"Searching for UID {seeded_user!r} returned no rows"
    assert any(seeded_user in u for u in uids), (
        f"UID search did not return the seeded user. Got: {uids[:5]}"
    )
    assert len(uids) == 1, f"UID search should match exactly one user, got {len(uids)}"


@pytest.mark.tc(id="USR_058", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify no-results state for a non-matching search",
                expected="'No results' state shown, distinct from empty-list state; term retained")
def test_usr_058_no_results_state(users):
    term = "zzzz_no_such_user_zzzz"
    users.search(term)

    assert users.row_count() == 0, (
        f"Search for a nonsense term returned {users.row_count()} row(s)"
    )

    empty = users.empty_state_text() or users.main_text()
    assert re.search(r"no .*(result|data|user|match)|not found", empty, re.I), (
        f"No recognisable no-results message shown. Page reads: {empty[:200]!r}"
    )

    box = users.search_box()
    assert box is not None and box.input_value() == term, (
        "Search term was cleared from the input after returning no results"
    )


@pytest.mark.tc(id="USR_059", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify clearing the search restores the full list",
                expected="Full unfiltered user list restored")
def test_usr_059_clear_search(users):
    baseline = users.row_count()
    if baseline == 0:
        pytest.skip("No users in this app, so restoring the full list cannot be observed")

    users.search("zzzz_no_such_user_zzzz")
    assert users.row_count() == 0, "Precondition failed: nonsense search still returned rows"

    users.clear_search()
    assert users.row_count() == baseline, (
        f"After clearing search the list shows {users.row_count()} rows, expected {baseline}"
    )


@pytest.mark.tc(id="USR_060", scenario=SCENARIO, sentiment="Positive", priority="Low",
                title="Verify search is debounced and does not fire per keystroke",
                expected="Far fewer requests than characters typed")
def test_usr_060_search_debounced(users):
    if users.search_box() is None:
        pytest.skip("No search input on the Users page")

    term = "abcdef"  # 6 characters
    requests = users.count_requests_while_typing(term)

    if requests == 0:
        pytest.skip(
            "No user-related XHR observed while typing — search may be client-side, "
            "in which case debounce is not applicable"
        )

    assert requests < len(term), (
        f"Search fired {requests} request(s) for {len(term)} characters typed — "
        "input does not appear to be debounced"
    )
