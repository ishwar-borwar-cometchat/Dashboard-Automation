"""Shared pytest fixtures + result collection for the CometChat Dashboard E2E suite."""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from pages.overview_page import OverviewPage

ROOT = pathlib.Path(__file__).parent
ARTIFACTS = ROOT / "artifacts"
REPORTS = ROOT / "reports"
ARTIFACTS.mkdir(exist_ok=True)
REPORTS.mkdir(exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "1671876b17a071c54")
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"
SLOWMO = int(os.environ.get("CC_SLOWMO", "0"))

# Optional CI path: supply the dashboard Bearer JWT directly instead of a
# storage-state file. CC_TOKEN_KEY is the localStorage key the dashboard reads
# it from — bootstrap_auth.py prints the correct key when it captures a session.
AUTH_TOKEN = os.environ.get("CC_AUTH_TOKEN", "").strip()
TOKEN_KEY = os.environ.get("CC_TOKEN_KEY", "token").strip()


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "tc(id, scenario, title, priority, sentiment): map a test to a spreadsheet test case",
    )


# ---------------------------------------------------------------------------
# Browser / context / page fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance) -> Browser:
    browser = playwright_instance.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOWMO,
        args=["--disable-dev-shm-usage", "--no-sandbox"],
    )
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def storage_state_path():
    """Path to the saved session, or None when CC_AUTH_TOKEN is used instead."""
    if AUTH_TOKEN:
        return None

    path = pathlib.Path(STORAGE_STATE)
    if not path.exists():
        pytest.exit(
            f"\nNo authenticated session found.\n\n"
            f"  Expected storage state at: {path}\n\n"
            f"  Capture one with:  python utils/bootstrap_auth.py\n"
            f"  (opens Chrome, you log in by hand, it saves the session)\n\n"
            f"  Or set CC_AUTH_TOKEN + CC_TOKEN_KEY for a headless/CI run.\n",
            returncode=4,
        )
    return str(path)


@pytest.fixture(scope="function")
def context(browser: Browser, storage_state_path) -> BrowserContext:
    ctx = browser.new_context(
        storage_state=storage_state_path,
        viewport={"width": 1600, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(15_000)

    if AUTH_TOKEN:
        # Seed the token before any app JS runs, and attach it to API calls.
        ctx.add_init_script(
            f"""() => {{
                try {{
                    localStorage.setItem({json.dumps(TOKEN_KEY)}, {json.dumps(AUTH_TOKEN)});
                }} catch (e) {{}}
            }}"""
        )
        ctx.set_extra_http_headers({"authorization": f"Bearer {AUTH_TOKEN}"})

    yield ctx
    ctx.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext) -> Page:
    pg = context.new_page()
    yield pg


@pytest.fixture(scope="function")
def overview(page: Page) -> OverviewPage:
    """Overview page, already opened and settled."""
    ov = OverviewPage(page, app_id=APP_ID, base_url=BASE_URL)
    ov.open()
    if "/login" in page.url or "signin" in page.url.lower():
        pytest.exit(
            "\nRedirected to login — the exported session has expired.\n"
            "Re-export storage_state.json and re-run.\n",
            returncode=4,
        )
    ov.install_capture()
    return ov


@pytest.fixture(scope="function")
def raw_overview(page: Page) -> OverviewPage:
    """Overview page object WITHOUT auto-navigation (for load/negative tests)."""
    return OverviewPage(page, app_id=APP_ID, base_url=BASE_URL)


@pytest.fixture(scope="session")
def app_config() -> Dict[str, Any]:
    return {"base_url": BASE_URL, "app_id": APP_ID}


# ---------------------------------------------------------------------------
# Result collection -> results.json (consumed by utils/report.py)
# ---------------------------------------------------------------------------
_RESULTS: List[Dict[str, Any]] = []


def _tc_meta(item: pytest.Item) -> Dict[str, Any]:
    marker = item.get_closest_marker("tc")
    if not marker:
        return {}
    meta = dict(marker.kwargs)
    if marker.args:
        meta.setdefault("id", marker.args[0])
    return meta


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" and not (report.when == "setup" and report.outcome == "skipped"):
        return

    meta = _tc_meta(item)
    status = report.outcome  # passed | failed | skipped
    reason = ""

    if status == "skipped":
        if isinstance(report.longrepr, tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2]).replace("Skipped: ", "")
        else:
            reason = str(report.longrepr or "")
    elif status == "failed":
        reason = str(report.longreprtext or report.longrepr or "").strip()

    # Capture a screenshot on failure if a page is available.
    shot = ""
    if status == "failed":
        pg = getattr(item, "_cc_page", None)
        if pg is not None:
            try:
                fname = f"{meta.get('id', item.name)}.png"
                pg.screenshot(path=str(ARTIFACTS / fname), full_page=True)
                shot = f"artifacts/{fname}"
            except Exception:
                pass

    _RESULTS.append(
        {
            "id": meta.get("id", ""),
            "scenario": meta.get("scenario", ""),
            "title": meta.get("title", item.name),
            "priority": meta.get("priority", ""),
            "sentiment": meta.get("sentiment", ""),
            "expected": meta.get("expected", ""),
            "nodeid": item.nodeid,
            "status": status,
            "reason": reason,
            "duration": round(getattr(report, "duration", 0.0), 3),
            "screenshot": shot,
        }
    )


@pytest.fixture(autouse=True)
def _attach_page_for_screenshots(request):
    """Expose the page object to the report hook so failures get screenshots."""
    yield
    for name in ("page",):
        if name in request.fixturenames:
            try:
                request.node._cc_page = request.getfixturevalue(name)
            except Exception:
                pass


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "app_id": APP_ID,
        "module": "Overview",
        "results": sorted(_RESULTS, key=lambda r: r.get("id") or "zzz"),
    }
    (REPORTS / "results.json").write_text(json.dumps(payload, indent=2))
