"""OV_049, OV_050, OV_053, OV_054, OV_055 : negative / resilience scenarios."""
from __future__ import annotations

import re

import pytest

from modules.general.overview.overview_page import CHART_TITLES, OPERATIONAL_METRICS, USAGE_METRICS

NO_USAGE_SCENARIO = "Overview - No Usage Data"
STATE_SCENARIO = "Overview - Loading/Error States"

USAGE_API_KEYWORDS = re.compile(r"usage|billing|plan|quota|subscription", re.I)


@pytest.mark.tc(
    id="OV_049",
    scenario=NO_USAGE_SCENARIO,
    sentiment="Negative",
    priority="High",
    title="Verify overview handles zero usage gracefully",
    expected="All metrics show 0/limit, charts show 'No usage as yet', no errors",
)
def test_ov_049_zero_usage_graceful(overview):
    zero_usage = True
    for label in USAGE_METRICS:
        parsed = overview.usage_metric(label)
        if parsed and parsed[0] != 0:
            zero_usage = False
            break

    if not zero_usage:
        pytest.skip(
            "This app already has non-zero usage, so the brand-new-app zero-state cannot be "
            "observed here. Point CC_APP_ID at a freshly created app to run this case."
        )

    for label in OPERATIONAL_METRICS:
        value = overview.operational_metric(label)
        assert value is not None, f"'{label}' did not render on a zero-usage app"
        assert float(value.replace(",", "")) == 0, f"'{label}' should be 0, got {value!r}"

    for title in CHART_TITLES:
        assert overview.chart_state(title) != "missing", f"'{title}' chart missing entirely"

    errors = overview.visible_error_banners()
    assert not errors, f"Error state(s) displayed on a zero-usage app: {errors}"


@pytest.mark.tc(
    id="OV_050",
    scenario=NO_USAGE_SCENARIO,
    sentiment="Negative",
    priority="Medium",
    title="Verify charts don't crash with no data",
    expected="Charts render an empty state gracefully, not a broken/error state",
)
def test_ov_050_empty_charts_dont_crash(overview):
    empty = [t for t in CHART_TITLES if overview.chart_state(t) == "empty"]
    if not empty:
        pytest.skip(
            "No chart on this app is currently in its empty state, so graceful no-data "
            "rendering cannot be observed. Needs an app with at least one metric unused."
        )

    for title in empty:
        text = overview.chart_panel_text(title)
        assert not re.search(r"error|failed|something went wrong", text, re.I), (
            f"'{title}' shows an error state instead of a graceful empty state"
        )
        assert re.search(r"no usage as yet|no data", text, re.I), (
            f"'{title}' empty state copy is missing: {text!r}"
        )
        assert not re.search(r"NaN|undefined|null", text), (
            f"'{title}' empty state leaks placeholder values: {text!r}"
        )


@pytest.mark.tc(
    id="OV_053",
    scenario=STATE_SCENARIO,
    sentiment="Negative",
    priority="Medium",
    title="Verify loading state on slow network",
    expected="Loading skeletons/spinners appear while data fetches",
)
def test_ov_053_loading_state_on_slow_network(raw_overview, app_config):
    page = raw_overview.page
    client = page.context.new_cdp_session(page)
    client.send("Network.enable")
    client.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": 400,
            "downloadThroughput": 50 * 1024 // 8,   # ~50 kbps
            "uploadThroughput": 50 * 1024 // 8,
        },
    )

    skeleton_selector = (
        "[class*='skeleton' i], [class*='shimmer' i], [class*='spinner' i], "
        "[class*='loading' i], [role='progressbar'][aria-busy='true'], [aria-busy='true']"
    )

    seen = False
    try:
        page.goto(
            f"{app_config['base_url']}/app/{app_config['app_id']}/overview",
            wait_until="commit",
            timeout=90_000,
        )
        for _ in range(60):
            try:
                loc = page.locator(skeleton_selector)
                if loc.count() > 0 and loc.first.is_visible():
                    seen = True
                    break
            except Exception:
                pass
            page.wait_for_timeout(250)
    finally:
        try:
            client.send(
                "Network.emulateNetworkConditions",
                {"offline": False, "latency": 0,
                 "downloadThroughput": -1, "uploadThroughput": -1},
            )
        except Exception:
            pass

    assert seen, (
        "No loading skeleton/spinner was observed while the Overview page fetched data "
        "over a throttled (~50 kbps / 400 ms latency) connection"
    )


@pytest.mark.tc(
    id="OV_054",
    scenario=STATE_SCENARIO,
    sentiment="Negative",
    priority="High",
    title="Verify error state when usage API fails",
    expected="Error state displays without crashing the entire page",
)
def test_ov_054_usage_api_failure(raw_overview, app_config):
    page = raw_overview.page

    # 1. Discover the real usage endpoints on a clean load.
    seen_urls = []
    page.on("request", lambda req: seen_urls.append(req.url)
            if req.resource_type in ("xhr", "fetch") else None)
    raw_overview.open()
    usage_endpoints = [u for u in seen_urls if USAGE_API_KEYWORDS.search(u)]

    if not usage_endpoints:
        pytest.skip(
            "Could not identify a usage/billing XHR endpoint to fail. The metrics may be "
            "server-rendered or bundled into a generic endpoint; needs a known API contract."
        )

    # 2. Reload with those endpoints forced to 500.
    page.route(
        lambda url: bool(USAGE_API_KEYWORDS.search(url)),
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"error":{"message":"Injected failure for OV_054"}}',
        ),
    )
    raw_overview.open()

    # Page must survive.
    body = page.locator("body").inner_text()
    assert re.search(r"Quick Links|Credentials", body, re.I), (
        "The whole Overview page failed to render when the usage API returned 500"
    )

    # And it must surface the failure somewhere.
    errors = raw_overview.visible_error_banners()
    has_error_copy = bool(
        re.search(r"error|failed|unable|try again|something went wrong|retry", body, re.I)
    )
    assert errors or has_error_copy, (
        "Usage API returned 500 but the Overview page shows no error state at all — "
        "the failure is silent"
    )


@pytest.mark.tc(
    id="OV_055",
    scenario=STATE_SCENARIO,
    sentiment="Negative",
    priority="High",
    title="Verify page works with expired/invalid session",
    expected="Redirects to login rather than showing stale data or errors",
)
def test_ov_055_expired_session_redirects(raw_overview, app_config):
    page = raw_overview.page

    raw_overview.open()  # establish a good session first

    # Simulate expiry: drop cookies and client-side auth storage.
    page.context.clear_cookies()
    try:
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass

    page.goto(
        f"{app_config['base_url']}/app/{app_config['app_id']}/overview",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_timeout(5_000)

    url = page.url
    body = page.locator("body").inner_text()

    redirected = bool(re.search(r"login|signin|sign-in|auth", url, re.I))
    shows_login = bool(re.search(r"log ?in|sign ?in|password|continue with", body, re.I))

    assert redirected or shows_login, (
        f"Expired session did not redirect to login. Landed on {url} showing: {body[:300]!r}"
    )
    assert app_config["app_id"] not in body or redirected, (
        "Stale app data is still rendered after the session was invalidated"
    )
