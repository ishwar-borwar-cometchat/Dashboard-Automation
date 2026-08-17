"""OV_024 - OV_027 : Operational Data (current month)."""
from __future__ import annotations

import re

import pytest

SCENARIO = "Overview - Operational Data (Current Month)"


def _assert_metric(overview, label: str):
    value = overview.operational_metric(label)
    assert value is not None, f"'{label}' metric not found in the Operational Data section"
    assert re.fullmatch(r"[\d,]+(?:\.\d+)?", value), (
        f"'{label}' is not a numeric value: {value!r}"
    )
    assert float(value.replace(",", "")) >= 0, f"'{label}' is negative: {value!r}"
    return value


@pytest.mark.tc(
    id="OV_024",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Users active this month displayed",
    expected="Shows a count of active users for the current month",
)
def test_ov_024_users_active_this_month(overview):
    _assert_metric(overview, "Users active this month")


@pytest.mark.tc(
    id="OV_025",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Voice minutes today displayed",
    expected="Shows total voice call minutes for today (0 if none)",
)
def test_ov_025_voice_minutes_today(overview):
    _assert_metric(overview, "Voice minutes today")


@pytest.mark.tc(
    id="OV_026",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Video minutes today displayed",
    expected="Shows total video call minutes for today",
)
def test_ov_026_video_minutes_today(overview):
    _assert_metric(overview, "Video minutes today")


@pytest.mark.tc(
    id="OV_027",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Recording minutes today displayed",
    expected="Shows total recording minutes for today",
)
def test_ov_027_recording_minutes_today(overview):
    _assert_metric(overview, "Recording minutes today")
