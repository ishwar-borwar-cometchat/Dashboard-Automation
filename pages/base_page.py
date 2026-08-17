"""Base page object with shared helpers for CometChat Dashboard pages."""
from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import Locator, Page, expect


DEFAULT_TIMEOUT = 15_000


class BasePage:
    """Common behaviour shared by every dashboard page object."""

    def __init__(self, page: Page, app_id: str, base_url: str):
        self.page = page
        self.app_id = app_id
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def goto(self, path: str = "", wait_until: str = "domcontentloaded") -> None:
        url = f"{self.base_url}/app/{self.app_id}/{path.lstrip('/')}".rstrip("/")
        self.page.goto(url, wait_until=wait_until, timeout=60_000)
        self.wait_for_network_idle()

    def wait_for_network_idle(self, timeout: int = 20_000) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # Dashboards with polling/websockets may never reach true idle.
            self.page.wait_for_timeout(1_500)

    # ------------------------------------------------------------------
    # Locator helpers
    # ------------------------------------------------------------------
    def text(self, value: str, exact: bool = False) -> Locator:
        return self.page.get_by_text(value, exact=exact).first

    def any_visible(self, *locators: Locator) -> Optional[Locator]:
        """Return the first locator that is actually visible, else None."""
        for loc in locators:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        return None

    def is_visible(self, locator: Locator, timeout: int = 5_000) -> bool:
        try:
            expect(locator).to_be_visible(timeout=timeout)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Section helper: the card/panel that contains a given heading
    # ------------------------------------------------------------------
    def section_for(self, heading: str) -> Locator:
        """Best-effort container lookup: nearest ancestor of a heading."""
        heading_loc = self.page.get_by_text(re.compile(re.escape(heading), re.I)).first
        return heading_loc.locator(
            "xpath=ancestor-or-self::*[self::section or self::div][1]"
        )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def read_clipboard(self) -> str:
        """Read clipboard text. Requires clipboard-read permission granted on context."""
        return self.page.evaluate("() => navigator.clipboard.readText()")

    def new_tab_url_after(self, action) -> Optional[str]:
        """Run `action`; if it opens a popup/new tab, return its URL."""
        try:
            with self.page.context.expect_page(timeout=8_000) as popup_info:
                action()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=20_000)
            url = popup.url
            popup.close()
            return url
        except Exception:
            return None
