"""OV_018 - OV_023 : Usage (current billing cycle)."""
from __future__ import annotations

import pytest

from modules.general.overview.overview_page import USAGE_METRICS

SCENARIO = "Overview - Usage (Current Billing Cycle)"


def _assert_usage_metric(overview, label: str):
    parsed = overview.usage_metric(label)
    assert parsed is not None, f"'{label}' usage metric not found or not in 'X / Y' format"
    used, limit, raw = parsed
    assert limit > 0, f"'{label}' limit should be greater than 0, got {raw!r}"
    assert used >= 0, f"'{label}' used value should not be negative, got {raw!r}"
    assert used <= limit, f"'{label}' shows usage above its limit: {raw!r}"
    return used, limit, raw


@pytest.mark.tc(
    id="OV_018",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Critical",
    title="Verify Chats section shows MAU usage",
    expected="MAU displays as 'X / Y' (used / limit)",
)
def test_ov_018_mau_usage(overview):
    _assert_usage_metric(overview, "MAU")


@pytest.mark.tc(
    id="OV_019",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Chats section shows PCC usage",
    expected="PCC displays as 'X / Y'",
)
def test_ov_019_pcc_usage(overview):
    _assert_usage_metric(overview, "PCC")


@pytest.mark.tc(
    id="OV_020",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Calls section shows Voice Minutes",
    expected="Voice Minutes displays as 'X / Y'",
)
def test_ov_020_voice_minutes_usage(overview):
    _assert_usage_metric(overview, "Voice Minutes")


@pytest.mark.tc(
    id="OV_021",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify Calls section shows Video Minutes",
    expected="Video Minutes displays as 'X / Y'",
)
def test_ov_021_video_minutes_usage(overview):
    _assert_usage_metric(overview, "Video Minutes")


@pytest.mark.tc(
    id="OV_022",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Medium",
    title="Verify usage progress bars reflect values",
    expected="Progress bars visually represent percentage used vs limit",
)
def test_ov_022_progress_bars(overview):
    """The indicator is a 20-segment bar, so resolution is 5% per segment."""
    checked = 0
    for label in USAGE_METRICS:
        seg = overview.usage_segments(label)
        metric = overview.usage_metric(label)
        if seg is None or metric is None:
            continue
        checked += 1
        used, limit, raw = metric
        assert seg["total"] > 0, f"'{label}' renders no indicator segments"
        expected_filled = int((used / limit) * seg["total"]) if limit else 0
        assert seg["filled"] == expected_filled, (
            f"'{label}' shows {seg['filled']}/{seg['total']} segments filled for {raw}; "
            f"expected {expected_filled} (each segment = {100 / seg['total']:.0f}%)"
        )
    assert checked, "No usage indicator segments found for any metric"


@pytest.mark.tc(
    id="OV_023",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="High",
    title="Verify usage updates reflect actual activity",
    expected="MAU increments after a new user is active in the app",
)
def test_ov_023_usage_reflects_activity(overview):
    pytest.skip(
        "Requires generating real chat traffic via the CometChat SDK/REST API with a fresh "
        "user, then waiting for the billing aggregation to refresh. Not automatable from the "
        "dashboard UI alone — needs an API-driven data-seeding fixture."
    )
