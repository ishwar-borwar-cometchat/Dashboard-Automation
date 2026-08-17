"""USR_061 - USR_065 : pagination and sorting (added during review)."""
from __future__ import annotations

import pytest

SCENARIO = "Users List - Pagination & Sorting"


def _require_pagination(users):
    if not users.has_pagination():
        pytest.skip(
            "No pagination control rendered — this app has fewer users than one page holds. "
            "Seed more users, or point CC_APP_ID at an app with a larger user base."
        )


@pytest.mark.tc(id="USR_061", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify pagination controls appear when users exceed page size",
                expected="Pagination control with page numbers and next/previous")
def test_usr_061_pagination_visible(users):
    _require_pagination(users)

    pag = users.pagination()
    assert pag.is_visible(), "Pagination control is present but not visible"
    assert users.page.locator(".ant-pagination-next").count(), "No next-page control"
    assert users.page.locator(".ant-pagination-prev").count(), "No previous-page control"


@pytest.mark.tc(id="USR_062", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify navigating between pages",
                expected="Next page loads new users; previous returns to the original set")
def test_usr_062_page_navigation(users):
    _require_pagination(users)

    first_page_uids = users.column_values("UID")
    start_page = users.current_page()

    if not users.goto_next_page():
        pytest.skip("Only one page of users available")

    second_page_uids = users.column_values("UID")
    assert second_page_uids, "Next page rendered no rows"
    assert second_page_uids != first_page_uids, (
        "Next page shows exactly the same rows as page 1 — pagination is not fetching"
    )
    assert users.current_page() != start_page, (
        f"Active page indicator did not change from {start_page}"
    )

    assert users.goto_prev_page(), "Could not navigate back to the previous page"
    assert users.column_values("UID") == first_page_uids, (
        "Returning to page 1 did not restore the original rows"
    )


@pytest.mark.tc(id="USR_063", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify changing page size",
                expected="Table renders the newly selected number of rows per page")
def test_usr_063_page_size(users):
    _require_pagination(users)

    before = users.row_count()
    if not users.set_page_size(50):
        pytest.skip("Page-size selector not available on this table")

    after = users.row_count()
    assert after >= before, (
        f"Increasing the page size reduced the rows shown ({before} -> {after})"
    )
    assert after <= 50, f"Page size set to 50 but {after} rows rendered"


@pytest.mark.tc(id="USR_064", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify sorting by Created column",
                expected="Rows sort ascending then descending by created date")
def test_usr_064_sort_by_created(users):
    if users.row_count() < 2:
        pytest.skip("Fewer than 2 users — sorting cannot be observed")

    original = users.column_values("Created")
    if not users.sort_by("Created"):
        pytest.skip("'Created' column header is not present or not clickable")

    first_sort = users.column_values("Created")
    users.sort_by("Created")
    second_sort = users.column_values("Created")

    assert first_sort != original or second_sort != first_sort, (
        "Clicking the Created header twice never reordered the rows — column is not sortable"
    )
    assert first_sort != second_sort, (
        "Ascending and descending sort produced identical row order"
    )


@pytest.mark.tc(id="USR_065", scenario=SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify search/filter results also paginate correctly",
                expected="Pagination reflects the filtered count, not the unfiltered total")
def test_usr_065_pagination_reflects_filter(users):
    _require_pagination(users)

    unfiltered = users.pagination().inner_text()

    if users.search_box() is None:
        pytest.skip("No search input available to produce a filtered result set")
    users.search("zzzz_no_such_user_zzzz")

    assert users.row_count() == 0, "Nonsense search still returned rows"

    pag = users.pagination()
    if pag is None or not pag.is_visible():
        return  # pagination correctly hidden for an empty result set

    filtered = pag.inner_text()
    assert filtered != unfiltered, (
        "Pagination is unchanged for a zero-result search — it appears to reflect the "
        f"unfiltered total rather than the filtered count ({filtered!r})"
    )
