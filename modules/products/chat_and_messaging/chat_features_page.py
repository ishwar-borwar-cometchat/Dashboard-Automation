"""Page object for PRODUCTS > Chat & Messaging > Features.

The page is one Ant Design table with two blocks of rows: CORE (always-on,
non-toggleable features) and EXTENSIONS (toggleable, grouped under category
header rows like "USER EXPERIENCE" / "USER ENGAGEMENT"). Every row's switch
carries an aria-label equal to the feature's exact display name — VERIFIED
against the live DOM on 2 Sep 2026 — so every lookup here goes through that
label rather than a CSS class, which is shared indiscriminately by both core
and extension rows.
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import Locator, Page

from core.base_page import BasePage

SELECTORS = {
    "table": ".ant-table",
    "switch_any": 'button[role="switch"]',
    # A toast reading "<Feature> has been enabled/disabled." appears bottom-right
    # after every toggle. Matched by text, not class — the class name is a
    # generated CSS-module hash not worth pinning.
    "toast": re.compile(r"has been (enabled|disabled)", re.I),
    # Some extensions refuse to enable and explain why in a blocking modal
    # instead (e.g. Smart Chat Features need AI Settings configured first).
    "modal": ".ant-modal",
    "modal_title": ".cc-modal__title",
    "modal_description": ".cc-modal__description",
    "modal_close": "button.cc-modal__close",
}


class ChatFeaturesPage(BasePage):
    PATH = "chat-features"

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open(self, force: bool = False) -> "ChatFeaturesPage":
        navigated = self.goto(self.PATH, force=force, ready_selector=SELECTORS["switch_any"])
        self.page.wait_for_selector(SELECTORS["table"], timeout=30_000)
        self.page.wait_for_selector(SELECTORS["switch_any"], timeout=30_000)
        if navigated:
            self.page.wait_for_timeout(1_500)  # only a fresh load needs to settle
        return self

    # ------------------------------------------------------------------
    # Row lookups
    # ------------------------------------------------------------------
    def switch(self, feature_name: str) -> Locator:
        return self.page.locator(f'button[role="switch"][aria-label="{feature_name}"]')

    def details_button(self, feature_name: str) -> Locator:
        return self.page.locator(f'button[aria-label="Open {feature_name} details"]')

    def settings_button(self, feature_name: str) -> Locator:
        return self.page.locator(f'button[aria-label="Open {feature_name} settings"]')

    def has_settings(self, feature_name: str) -> bool:
        return self.settings_button(feature_name).count() > 0

    def exists(self, feature_name: str) -> bool:
        return self.switch(feature_name).count() > 0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def is_enabled(self, feature_name: str) -> bool:
        return self.switch(feature_name).get_attribute("aria-checked") == "true"

    def is_locked(self, feature_name: str) -> bool:
        """True for CORE features: their switch is rendered `disabled`."""
        return self.switch(feature_name).get_attribute("disabled") is not None

    def wait_for_state(self, feature_name: str, expected: bool, timeout: int = 12_000) -> None:
        """Poll aria-checked until it matches `expected`.

        The dashboard applies a toggle over the network — aria-checked does not
        flip on click, only once that call round-trips (observed 1.5-3s).
        """
        want = "true" if expected else "false"
        self.page.wait_for_function(
            """([label, want]) => {
                const el = document.querySelector(
                    `button[role="switch"][aria-label="${label}"]`
                );
                return !!el && el.getAttribute('aria-checked') === want;
            }""",
            arg=[feature_name, want],
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def toggle(self, feature_name: str) -> None:
        self.switch(feature_name).click()

    def set_extension(self, feature_name: str, enabled: bool, timeout: int = 12_000) -> None:
        """Toggle `feature_name` to `enabled` if it is not already there."""
        if self.is_enabled(feature_name) == enabled:
            return
        self.toggle(feature_name)
        self.wait_for_state(feature_name, enabled, timeout=timeout)

    def toast_text(self, timeout: int = 6_000) -> Optional[str]:
        try:
            loc = self.page.get_by_text(SELECTORS["toast"]).first
            loc.wait_for(timeout=timeout)
            return loc.inner_text()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Blocking "can't enable this yet" modal
    # ------------------------------------------------------------------
    def modal_visible(self, timeout: int = 6_000) -> bool:
        try:
            self.page.locator(SELECTORS["modal"]).first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def modal_text(self) -> str:
        modal = self.page.locator(SELECTORS["modal"]).first
        title = modal.locator(SELECTORS["modal_title"]).inner_text()
        desc = modal.locator(SELECTORS["modal_description"]).inner_text()
        return f"{title} {desc}"

    def close_modal(self) -> None:
        self.page.locator(SELECTORS["modal_close"]).first.click()
        self.page.locator(SELECTORS["modal"]).first.wait_for(state="hidden", timeout=6_000)
