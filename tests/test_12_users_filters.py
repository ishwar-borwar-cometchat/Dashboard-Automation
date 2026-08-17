"""USR_008 - USR_012 : filters.  USR_066 - USR_068 : filter combinations (added)."""
from __future__ import annotations

import re

import pytest

from pages.users_page import FILTER_CHIPS

SCENARIO = "Users List - Filters"
COMBO_SCENARIO = "Users List - Filter Combinations"


def _require_filters(users):
    if not users.open_filters():
        pytest.skip("Filter control not found on the Users page")


@pytest.mark.tc(id="USR_008", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify filter by UIDs",
                expected="Table filters to users matching that UID")
def test_usr_008_filter_by_uid(users, seeded_user):
    users.open()
    _require_filters(users)

    chip = users.filter_chip("UIDs")
    assert chip is not None, f"'UIDs' filter chip not found. Expected one of {FILTER_CHIPS}"
    chip.click()
    users.page.wait_for_timeout(800)

    field = users.page.locator("input:visible").last
    field.fill(seeded_user)
    users.page.keyboard.press("Enter")
    users.page.wait_for_timeout(2_000)

    apply_btn = users.page.get_by_role("button", name=re.compile(r"apply|ok|done", re.I))
    if apply_btn.count():
        apply_btn.first.click()
        users.page.wait_for_timeout(2_000)

    uids = users.column_values("UID")
    assert uids, f"Filtering by UID {seeded_user!r} returned no rows"
    assert all(seeded_user in u for u in uids), (
        f"UID filter returned non-matching rows: {uids[:5]}"
    )


@pytest.mark.tc(id="USR_009", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify filter by Role",
                expected="Table shows only users with that role")
def test_usr_009_filter_by_role(users):
    _require_filters(users)

    chip = users.filter_chip("Role")
    assert chip is not None, "'Role' filter chip not found"
    chip.click()
    users.page.wait_for_timeout(1_000)

    options = users.page.locator(".ant-select-item-option, [role=option]")
    if not options.count():
        pytest.skip("Role filter exposed no selectable options")

    chosen = options.first.inner_text().strip()
    options.first.click()
    users.page.wait_for_timeout(2_000)

    apply_btn = users.page.get_by_role("button", name=re.compile(r"apply|ok|done", re.I))
    if apply_btn.count():
        apply_btn.first.click()
        users.page.wait_for_timeout(2_000)

    roles = users.column_values("Role")
    if not roles:
        pytest.skip("Role column not present in the table, cannot verify the filter result")
    assert all(chosen.lower() in r.lower() for r in roles), (
        f"Role filter '{chosen}' returned rows with other roles: {set(roles)}"
    )


@pytest.mark.tc(id="USR_010", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify filter by Status",
                expected="Table filters by user status")
def test_usr_010_filter_by_status(users):
    _require_filters(users)

    chip = users.filter_chip("Status")
    assert chip is not None, "'Status' filter chip not found"
    chip.click()
    users.page.wait_for_timeout(1_000)

    options = users.page.locator(".ant-select-item-option, [role=option]")
    if not options.count():
        pytest.skip("Status filter exposed no selectable options")

    before = users.row_count()
    options.first.click()
    users.page.wait_for_timeout(2_500)

    apply_btn = users.page.get_by_role("button", name=re.compile(r"apply|ok|done", re.I))
    if apply_btn.count():
        apply_btn.first.click()
        users.page.wait_for_timeout(2_000)

    after = users.row_count()
    assert after <= before, (
        f"Applying a status filter increased the row count ({before} -> {after})"
    )


@pytest.mark.tc(id="USR_011", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify filter by Created At Date",
                expected="Table shows only users created within the range")
def test_usr_011_filter_by_created_date(users):
    _require_filters(users)

    chip = users.filter_chip("Created At Date")
    assert chip is not None, "'Created At Date' filter chip not found"
    chip.click()
    users.page.wait_for_timeout(1_000)

    picker = users.page.locator(".ant-picker")
    assert picker.count(), "Created At Date filter did not expose a date picker"

    before = users.row_count()
    picker.first.click()
    users.page.wait_for_timeout(800)

    today = users.page.locator(".ant-picker-cell-today, .ant-picker-cell-in-view")
    if not today.count():
        pytest.skip("Date picker rendered no selectable cells")
    today.first.click()
    users.page.wait_for_timeout(700)
    if today.count() > 1:
        today.last.click()
    users.page.wait_for_timeout(2_500)

    assert users.row_count() <= before, (
        f"Date filter increased the row count ({before} -> {users.row_count()})"
    )


@pytest.mark.tc(id="USR_012", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify clearing all filters",
                expected="Full unfiltered user list restored")
def test_usr_012_clear_filters(users):
    baseline = users.row_count()
    if baseline == 0:
        pytest.skip("No users in this app, so restoring the unfiltered list cannot be observed")

    _require_filters(users)
    chip = users.filter_chip("Status")
    if chip is None:
        pytest.skip("No filter available to apply before clearing")
    chip.click()
    users.page.wait_for_timeout(1_000)
    options = users.page.locator(".ant-select-item-option, [role=option]")
    if options.count():
        options.first.click()
        users.page.wait_for_timeout(2_000)

    clear = users.page.get_by_role("button", name=re.compile(r"clear|reset|remove all", re.I))
    assert clear.count(), "No clear/reset control found for filters"
    clear.first.click()
    users.page.wait_for_timeout(2_500)

    assert users.row_count() == baseline, (
        f"After clearing filters the list shows {users.row_count()} rows, expected {baseline}"
    )


# ---------------------------------------------------------------------------
# Added during review
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_066", scenario=COMBO_SCENARIO, sentiment="Positive", priority="High",
                title="Verify combining two filters applies AND logic",
                expected="Only users matching BOTH filters are listed")
def test_usr_066_combined_filters(users):
    _require_filters(users)

    applied = 0
    counts = [users.row_count()]
    for chip_name in ("Role", "Status"):
        chip = users.filter_chip(chip_name)
        if chip is None:
            continue
        chip.click()
        users.page.wait_for_timeout(1_000)
        options = users.page.locator(".ant-select-item-option, [role=option]")
        if not options.count():
            continue
        options.first.click()
        users.page.wait_for_timeout(2_200)
        applied += 1
        counts.append(users.row_count())

    if applied < 2:
        pytest.skip("Could not apply two filters simultaneously on this page")

    assert counts[-1] <= counts[-2], (
        f"Adding a second filter widened the result set ({counts[-2]} -> {counts[-1]}), "
        "which suggests OR rather than AND semantics"
    )


@pytest.mark.tc(id="USR_067", scenario=COMBO_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify active filters are visibly indicated",
                expected="Applied filters shown as chips/badges or a count")
def test_usr_067_active_filter_indicator(users):
    before = users.active_filter_indicators()
    _require_filters(users)

    chip = users.filter_chip("Status")
    if chip is None:
        pytest.skip("No filter available to apply")
    chip.click()
    users.page.wait_for_timeout(1_000)
    options = users.page.locator(".ant-select-item-option, [role=option]")
    if not options.count():
        pytest.skip("Filter exposed no selectable options")
    options.first.click()
    users.page.wait_for_timeout(2_200)

    after = users.active_filter_indicators()
    assert len(after) > len(before), (
        "Applying a filter produced no visible chip, badge or count — the user cannot "
        f"tell the list is filtered. Before: {before}, after: {after}"
    )


@pytest.mark.tc(id="USR_068", scenario=COMBO_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify filter behaviour after page reload",
                expected="Filters persist, or reset cleanly with the full list shown")
def test_usr_068_filters_after_reload(users):
    baseline = users.row_count()
    _require_filters(users)

    chip = users.filter_chip("Status")
    if chip is None:
        pytest.skip("No filter available to apply")
    chip.click()
    users.page.wait_for_timeout(1_000)
    options = users.page.locator(".ant-select-item-option, [role=option]")
    if not options.count():
        pytest.skip("Filter exposed no selectable options")
    options.first.click()
    users.page.wait_for_timeout(2_200)
    filtered = users.row_count()

    users.page.reload(wait_until="domcontentloaded")
    users.page.wait_for_timeout(3_000)

    after = users.row_count()
    indicators = users.active_filter_indicators()

    if after == filtered and filtered != baseline:
        assert indicators, (
            "Filter survived the reload but no active-filter indicator is shown — "
            "the list looks unfiltered while it is not"
        )
    else:
        assert after == baseline, (
            f"After reload the list shows {after} rows — neither the filtered count "
            f"({filtered}) nor the full list ({baseline})"
        )
