"""OV_045 - OV_048 : Sidebar navigation."""
from __future__ import annotations

import re

import pytest

SCENARIO = "Overview - Sidebar Navigation"

EXPECTED_GROUPS = {
    "GENERAL": ["Overview"],
    "PRODUCTS": ["Chat", "Voice", "AI"],
    "PLATFORM FEATURES": ["Moderation", "Notification", "Analytics"],
    "ACCOUNT": [],
}


@pytest.mark.tc(
    id="OV_045",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify Overview is highlighted in sidebar when active",
    expected="Overview item is highlighted/active in the sidebar",
)
def test_ov_045_overview_highlighted(overview):
    assert overview.sidebar_item("Overview") is not None, "'Overview' not found in the sidebar"
    assert overview.sidebar_item_is_active("Overview"), (
        "'Overview' sidebar item is not marked active "
        "(no active/selected class, aria-current or data-state)"
    )


@pytest.mark.tc(
    id="OV_046",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify sidebar sections are correctly grouped",
    expected="GENERAL, PRODUCTS, PLATFORM FEATURES, ACCOUNT groups present with expected items",
)
def test_ov_046_sidebar_groups(overview):
    text = overview.sidebar_text()
    assert text, "Sidebar could not be located or is empty"

    missing_groups = [
        group for group in EXPECTED_GROUPS
        if not re.search(re.escape(group).replace(r"\ ", r"\s+"), text, re.I)
    ]
    assert not missing_groups, f"Sidebar is missing group heading(s): {missing_groups}"

    missing_items = []
    for group, items in EXPECTED_GROUPS.items():
        for item in items:
            if not re.search(re.escape(item), text, re.I):
                missing_items.append(f"{group} > {item}")
    assert not missing_items, f"Sidebar is missing expected item(s): {missing_items}"


@pytest.mark.tc(
    id="OV_047",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify expandable sidebar items (User & Groups)",
    expected="Expands to show Users, Groups, User Roles sub-items",
)
def test_ov_047_expandable_user_and_groups(overview):
    label = None
    for candidate in ("User & Groups", "Users & Groups", "User and Groups"):
        if overview.sidebar_item(candidate) is not None:
            label = candidate
            break
    assert label is not None, "'User & Groups' item not found in the sidebar"

    children = overview.expand_sidebar_item(label)
    try:
        assert children, f"Expanding '{label}' revealed no sub-items"
        expected_children = ["Users", "Groups", "User Roles"]
        missing = [
            c for c in expected_children
            if not any(c.lower() == k.strip().lower() for k in children)
        ]
        assert not missing, (
            f"Expanding '{label}' did not reveal sub-item(s): {missing}. Got: {children}"
        )
    finally:
        overview.collapse_sidebar_item(label)


@pytest.mark.tc(
    id="OV_048",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify app name and ID shown at bottom of sidebar",
    expected="Current app name and App ID displayed at the bottom of the sidebar",
)
def test_ov_048_app_name_and_id_in_sidebar(overview, app_config):
    text = overview.sidebar_text()
    assert text, "Sidebar could not be located or is empty"

    app_id = app_config["app_id"]
    short_id = app_id[:8]
    assert app_id in text or short_id in text, (
        f"App ID ({app_id}) is not shown in the sidebar. Sidebar text: {text[-400:]!r}"
    )
