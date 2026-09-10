"""CHF_001 : Chat & Messaging > Features page load."""
from __future__ import annotations

import pytest

SCENARIO = "Chat & Messaging - Features - Page Load"


@pytest.mark.tc(
    id="CHF_001",
    scenario=SCENARIO,
    sentiment="Positive",
    priority="Critical",
    title="Verify the Features page loads with Core and Extensions sections",
    expected="Feature table renders with CORE and EXTENSIONS row groups, each row showing a switch",
)
def test_chf_001_features_page_loads(raw_chat_features):
    cf = raw_chat_features.open(force=True)

    assert "chat-features" in cf.page.url, f"Not on the Features URL: {cf.page.url}"

    body = cf.page.locator(".ant-table").first.inner_text()
    for required in ("CORE", "EXTENSIONS", "Instant Messaging", "Bitly"):
        assert required in body, f"Features table is missing expected content: {required!r}"
