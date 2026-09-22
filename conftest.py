"""Shared pytest fixtures + result collection for the CometChat Dashboard E2E suite."""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


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
    args = ["--disable-dev-shm-usage", "--no-sandbox"]
    if not HEADLESS:
        args.append("--start-maximized")

    browser = playwright_instance.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOWMO,
        args=args,
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


# One context for the whole session. Headed Chromium gives every BrowserContext
# its own OS window, so a per-test context meant one window per test. Sharing the
# context and handing each test a *tab* keeps the run to a single window.
class _SharedContext:
    """Owns the one BrowserContext the whole run shares.

    Tests get a tab in it rather than a context of their own. OV_055 and USR_090
    deliberately clear cookies and localStorage to assert the expired-session
    redirect; that logs the shared context out, so those are detected and the
    context is rebuilt from the saved session file. Rebuilding re-reads
    storage_state.json — it never needs an interactive login.
    """

    def __init__(self, browser: Browser, storage_state_path):
        self._browser = browser
        self._state = storage_state_path
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._dirty = False

    def _build(self) -> BrowserContext:
        # Headed: no fixed viewport, so the page fills the maximized window.
        # Headless: there is no window to fill, so keep an explicit large viewport.
        sizing = (
            {"no_viewport": True} if not HEADLESS else {"viewport": {"width": 1600, "height": 1000}}
        )

        ctx = self._browser.new_context(
            storage_state=self._state,
            permissions=["clipboard-read", "clipboard-write"],
            ignore_https_errors=True,
            **sizing,
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

        return ctx

    def get(self) -> BrowserContext:
        if self._ctx is not None and self._dirty:
            try:
                self._ctx.close()
            except Exception:
                pass
            self._ctx = None
            self._page = None
        if self._ctx is None:
            self._ctx = self._build()
            self._dirty = False
        return self._ctx

    def get_page(self) -> Page:
        """The one tab every test shares.

        Reused rather than recreated so a test that is already on the right page
        can skip the reload entirely — and so the window stays open between tests.
        """
        ctx = self.get()
        if self._page is None or self._page.is_closed():
            self._page = ctx.new_page()

        # Close anything a previous test left behind (popups, opened tabs).
        for other in ctx.pages:
            if other is not self._page:
                try:
                    other.close()
                except Exception:
                    pass
        return self._page

    def note_page_state(self, pg: Page) -> None:
        """Flag a context that the finished test logged out.

        Checked via the JWT in localStorage, not via cookies: the login page sets
        its own analytics cookies the moment a test lands on it, so an emptied
        context looks cookie-populated a second later.
        """
        if self._ctx is None:
            return
        try:
            if BASE_URL.split("//")[-1].split("/")[0] not in pg.url:
                return  # not on the dashboard origin; nothing to judge
            self._dirty = not pg.evaluate(
                """() => Object.keys(localStorage).some(k => {
                    const v = localStorage.getItem(k) || '';
                    return v.startsWith('eyJ') && v.split('.').length === 3;
                })"""
            )
        except Exception:
            self._dirty = True

    def close(self) -> None:
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:
                pass
            self._ctx = None


@pytest.fixture(scope="session")
def shared_context(browser: Browser, storage_state_path) -> _SharedContext:
    holder = _SharedContext(browser, storage_state_path)
    yield holder
    holder.close()


@pytest.fixture(scope="function")
def context(shared_context: _SharedContext) -> BrowserContext:
    return shared_context.get()


@pytest.fixture(scope="function")
def page(shared_context: _SharedContext) -> Page:
    pg = shared_context.get_page()
    yield pg
    shared_context.note_page_state(pg)


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
    """Expose the page object to the report hook so failures get screenshots.

    Attached at setup, not teardown: pytest runs makereport(call) before fixture
    finalisers, so a teardown-time attach always arrived too late.
    """
    if "page" in request.fixturenames:
        try:
            request.node._cc_page = request.getfixturevalue("page")
        except Exception:
            pass
    yield


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "app_id": APP_ID,
        "module": os.environ.get("CC_MODULE_LABEL", "Dashboard"),
        "results": sorted(_RESULTS, key=lambda r: r.get("id") or "zzz"),
    }
    (REPORTS / "results.json").write_text(json.dumps(payload, indent=2))


