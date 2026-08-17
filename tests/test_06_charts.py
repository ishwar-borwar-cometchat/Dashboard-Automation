"""OV_028 - OV_034 : Overview charts."""
from __future__ import annotations

import re

import pytest

from pages.overview_page import CHART_TITLES

SCENARIO = "Overview - Charts"


def _assert_chart(overview, title: str, subtitle: str):
    state = overview.chart_state(title)
    assert state != "missing", f"'{title}' chart panel not found on the page"

    text = overview.chart_panel_text(title)
    assert not re.search(r"error|failed|something went wrong", text, re.I), (
        f"'{title}' chart is rendering an error state: {text[:120]!r}"
    )
    assert re.search(re.escape(subtitle), text, re.I), (
        f"'{title}' chart does not show its '{subtitle}' range label"
    )
    return state


@pytest.mark.tc(
    id="OV_028",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Peak Concurrent Connections chart (Past 30 days)",
    expected="Chart showing PCC over past 30 days with a date axis",
)
def test_ov_028_pcc_chart(overview):
    state = _assert_chart(overview, "Peak concurrent connections", "Past 30 days")
    if state == "rendered":
        assert overview.chart_series_count("Peak concurrent connections") > 0, (
            "PCC chart canvas rendered but contains no series paths"
        )
        text = overview.chart_panel_text("Peak concurrent connections")
        assert any(
            month in text
            for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        ), "PCC chart does not render a date axis"


@pytest.mark.tc(
    id="OV_029",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Monthly Active Users chart (Past 3 months)",
    expected="Chart showing MAU trend over the past 3 months",
)
def test_ov_029_mau_chart(overview):
    _assert_chart(overview, "Monthly Active Users", "Past 3 months")


@pytest.mark.tc(
    id="OV_030",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Voice Minutes chart (Past 30 days)",
    expected="Chart showing voice minutes over past 30 days (or 'No usage as yet')",
)
def test_ov_030_voice_minutes_chart(overview):
    _assert_chart(overview, "Voice Minutes", "Past 30 days")


@pytest.mark.tc(
    id="OV_031",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Video Minutes chart (Past 30 days)",
    expected="Chart showing video minutes over past 30 days (or 'No usage as yet')",
)
def test_ov_031_video_minutes_chart(overview):
    _assert_chart(overview, "Video Minutes", "Past 30 days")


@pytest.mark.tc(
    id="OV_032",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Recording Minutes chart (Past 30 days)",
    expected="Chart showing recording minutes over past 30 days (or 'No usage as yet')",
)
def test_ov_032_recording_minutes_chart(overview):
    _assert_chart(overview, "Recording Minutes", "Past 30 days")


@pytest.mark.tc(
    id="OV_033",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify 'No usage as yet' empty state for charts",
    expected="Charts with no data show 'No usage as yet' with an empty chart icon",
)
def test_ov_033_empty_state(overview):
    empty = [t for t in CHART_TITLES if overview.chart_state(t) == "empty"]
    if not empty:
        pytest.skip(
            "This app currently has data in every chart, so the 'No usage as yet' "
            "empty state cannot be observed. Needs a zero-usage app to verify."
        )

    for title in empty:
        assert "No usage as yet" in overview.chart_panel_text(title), (
            f"'{title}' empty state does not use the expected copy"
        )
        assert overview.chart_empty_icon_present(title), (
            f"'{title}' empty state renders no empty-chart icon"
        )


@pytest.mark.tc(
    id="OV_034",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Low",
    title="Verify chart data points are interactive (hover/tooltip)",
    expected="Tooltip shows the exact value for a hovered date",
)
def test_ov_034_chart_tooltip(overview):
    if overview.chart_state("Peak concurrent connections") != "rendered":
        pytest.skip("PCC chart has no plotted data points to hover in this app")

    assert overview.hover_chart("Peak concurrent connections"), (
        "Hovering across the PCC chart did not activate the ApexCharts tooltip"
    )
