"""Page Object for the CometChat Dashboard > Overview page.

Selectors verified against the live DOM (Ant Design + CSS-module class names,
ApexCharts for all charts). Notes that matter:

* Product cards and Quick Links are NOT anchors — they are div[role=button]
  elements whose handlers call window.open(). Destination checks therefore use
  `capture_window_open()` rather than reading href.
* Card icons are drawn with CSS mask-image, not <svg>/<img>.
* Every credential value node renders TWICE: a visible node
  (.style_credentialItemLeft) and a hidden sibling (.style_credentialItemRight).
  For the Auth Key the visible node is the mask and the hidden node holds the
  real key — see `auth_key_visible()` / `auth_key_hidden_plaintext()`.
* Sidebar active state uses a CSS-module class ([class*=appNavItemSelected]);
  there is no aria-current / ant-menu-item-selected.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import Locator, Page

from core.base_page import BasePage


# --- Static expectations from the test-case spreadsheet -----------------------

PRODUCT_CARDS = {
    "Chat & Messaging": "Real-time user to user & group chats",
    "Voice & Video Calling": "In-app calling & conferencing",
    "AI Agents": "Full stack AI Agents for your app",
    "BYO Agents": "Integrate an existing AI agent",
}

QUICK_LINKS = [
    "Create Support Ticket", "Developer Docs", "API Docs", "Sample Apps",
    "Help Center", "Slack Support", "Community", "Product Updates",
    "Product Feedback", "Status Page",
]

CHART_TITLES = [
    "Peak concurrent connections", "Monthly Active Users",
    "Voice Minutes", "Video Minutes", "Recording Minutes",
]

OPERATIONAL_METRICS = [
    "Users active this month", "Voice minutes today",
    "Video minutes today", "Recording minutes today",
]

USAGE_METRICS = ["MAU", "PCC", "Voice Minutes", "Video Minutes"]
HEADER_BUTTONS = ["Get Help", "App Credentials", "Documentation"]
VALID_REGIONS = {"US", "EU", "IN", "LONDON", "UK"}

# --- Verified selectors -------------------------------------------------------

SEL_CARD = "[class*=navigationCardLink]"
SEL_QUICK_LINK = "[class*=quickLinksItemWrapper]"
SEL_CRED_ROW = "[class*=credentialItemWrapper]"
SEL_CRED_LABEL = "[class*=credentialItemTitle]"
SEL_CRED_VALUE = "[class*=credentialItemSub]"
SEL_CRED_VISIBLE = "[class*=credentialItemLeft]"
SEL_CRED_HIDDEN = "[class*=credentialItemRight]"
SEL_SEGMENT = "[class*=percentageIndicatorBar]"
SEL_OPS_BLOCK = "[class*=userBlock]"
SEL_OPS_LABEL = "[class*=userHead]:not([class*=userHeadDetail])"
SEL_OPS_VALUE = "[class*=userHeadDetail]"
SEL_SIDEBAR = ".ant-layout-sider"
SEL_SIDEBAR_ACTIVE = "[class*=appNavItemSelected]"
SEL_CHART_CANVAS = ".apexcharts-canvas"

USAGE_PATTERN = re.compile(r"([\d,]+)\s*/\s*([\d,]+)")

# JS installed once per page to record window.open destinations without
# actually opening tabs, and to record clipboard writes without clobbering
# the real clipboard.
_CAPTURE_JS = """
() => {
  if (window.__ccCap) return;
  window.__ccCap = { opens: [], clips: [] };
  const origOpen = window.open;
  window.__ccOrigOpen = origOpen;
  window.open = function (url) {
    window.__ccCap.opens.push(String(url));
    return { closed: false, focus() {}, close() {}, document: {} };
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    const origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
    window.__ccOrigWrite = origWrite;
    navigator.clipboard.writeText = (v) => {
      window.__ccCap.clips.push(String(v));
      return Promise.resolve();
    };
  }
}
"""


class OverviewPage(BasePage):
    PATH = "overview"

    # ------------------------------------------------------------------
    # Navigation / setup
    # ------------------------------------------------------------------
    def open(self) -> "OverviewPage":
        self.goto(self.PATH)
        self.page.wait_for_selector(SEL_CARD, timeout=30_000)
        self.page.wait_for_timeout(1_500)
        return self

    def install_capture(self) -> None:
        """Intercept window.open + clipboard writes (idempotent)."""
        self.page.evaluate(_CAPTURE_JS)

    def reset_capture(self) -> None:
        self.install_capture()
        self.page.evaluate("() => { window.__ccCap.opens = []; window.__ccCap.clips = []; }")

    def captured_opens(self) -> List[str]:
        return self.page.evaluate("() => (window.__ccCap ? window.__ccCap.opens : [])")

    def captured_clips(self) -> List[str]:
        return self.page.evaluate("() => (window.__ccCap ? window.__ccCap.clips : [])")

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    def header_button(self, name: str) -> Optional[Locator]:
        loc = self.page.locator("button").filter(
            has_text=re.compile(rf"^\s*{re.escape(name)}\s*$")
        )
        return loc.first if loc.count() else None

    # ------------------------------------------------------------------
    # Get Started / Integrate
    # ------------------------------------------------------------------
    def product_cards(self) -> Locator:
        return self.page.locator(SEL_CARD)

    def product_card(self, title: str) -> Optional[Locator]:
        loc = self.page.locator(SEL_CARD).filter(has_text=title)
        return loc.first if loc.count() else None

    def product_card_text(self, title: str) -> str:
        card = self.product_card(title)
        return card.inner_text() if card else ""

    def product_card_has_icon(self, title: str) -> bool:
        """Icons are CSS mask-image; also accept svg/img/background-image."""
        card = self.product_card(title)
        if card is None:
            return False
        return card.evaluate(
            """el => {
                if (el.querySelector('svg, img')) return true;
                return [...el.querySelectorAll('*')].some(k => {
                    const s = getComputedStyle(k);
                    const m = s.maskImage || s.webkitMaskImage || 'none';
                    return (m && m !== 'none') ||
                           (s.backgroundImage && s.backgroundImage !== 'none');
                });
            }"""
        )

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    def credentials_card(self) -> Locator:
        return self.page.locator(SEL_CRED_ROW).first.locator("xpath=..")

    def _cred_row(self, label: str) -> Optional[Locator]:
        loc = self.page.locator(SEL_CRED_ROW).filter(
            has=self.page.locator(SEL_CRED_LABEL, has_text=re.compile(rf"^\s*{re.escape(label)}\s*$"))
        )
        return loc.first if loc.count() else None

    def credential_visible_value(self, label: str) -> Optional[str]:
        """The value the user actually sees (masked, for Auth Key)."""
        row = self._cred_row(label)
        if row is None:
            return None
        vis = row.locator(SEL_CRED_VALUE).locator(SEL_CRED_VISIBLE)
        if vis.count():
            return vis.first.inner_text().strip()
        return row.locator(SEL_CRED_VALUE).first.inner_text().strip()

    def credential_hidden_value(self, label: str) -> Optional[str]:
        """Text held in the hidden sibling node, if any."""
        row = self._cred_row(label)
        if row is None:
            return None
        hid = row.locator(SEL_CRED_VALUE).locator(SEL_CRED_HIDDEN)
        return hid.first.inner_text().strip() if hid.count() else None

    def app_id_value(self) -> Optional[str]:
        return self.credential_visible_value("App ID")

    def region_value(self) -> Optional[str]:
        return self.credential_visible_value("Region")

    def auth_key_visible(self) -> Optional[str]:
        return self.credential_visible_value("Auth Key")

    def auth_key_hidden_plaintext(self) -> Optional[str]:
        """OV_052: the real key rendered into a display:none sibling."""
        return self.credential_hidden_value("Auth Key")

    @staticmethod
    def is_masked(value: Optional[str]) -> bool:
        return bool(value) and not re.search(r"[A-Za-z0-9]", value)

    def credential_buttons(self, label: str) -> Locator:
        row = self._cred_row(label)
        return row.locator("button") if row is not None else self.page.locator("nonexistent")

    def auth_key_toggle(self) -> Optional[Locator]:
        btns = self.credential_buttons("Auth Key")
        return btns.nth(0) if btns.count() >= 1 else None

    def auth_key_copy(self) -> Optional[Locator]:
        btns = self.credential_buttons("Auth Key")
        return btns.nth(1) if btns.count() >= 2 else None

    def app_id_copy(self) -> Optional[Locator]:
        btns = self.credential_buttons("App ID")
        return btns.nth(0) if btns.count() >= 1 else None

    def view_all_link(self) -> Optional[Locator]:
        loc = self.page.get_by_role("link", name=re.compile(r"^\s*View All\s*$", re.I))
        return loc.first if loc.count() else None

    def credentials_card_html(self) -> str:
        return self.credentials_card().inner_html()

    # ------------------------------------------------------------------
    # Usage
    # ------------------------------------------------------------------
    def usage_metric(self, label: str) -> Optional[Tuple[int, int, str]]:
        node = self.page.get_by_text(
            re.compile(rf"^\s*{re.escape(label)}\s*$"), exact=False
        ).first
        if node.count() == 0:
            return None
        raw = node.evaluate(
            """el => { let p = el;
                 for (let i = 0; i < 4 && p.parentElement; i++) {
                   p = p.parentElement;
                   if (/\\d[\\d,]*\\s*\\/\\s*\\d/.test(p.textContent)) return p.textContent;
                 }
                 return ''; }"""
        )
        m = USAGE_PATTERN.search(raw or "")
        if not m:
            return None
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", "")), m.group(0)

    def usage_segments(self, label: str) -> Optional[Dict[str, int]]:
        """Return {'total': n, 'filled': n} for a metric's segmented indicator."""
        node = self.page.get_by_text(re.compile(rf"^\s*{re.escape(label)}\s*$")).first
        if node.count() == 0:
            return None
        return node.evaluate(
            """el => { let p = el;
                 for (let i = 0; i < 6 && p.parentElement; i++) {
                   p = p.parentElement;
                   const bars = p.querySelectorAll('[class*=percentageIndicatorBar]');
                   if (bars.length) {
                     const cols = [...bars].map(b => getComputedStyle(b).backgroundColor);
                     const empty = 'rgba(0, 0, 0, 0)';
                     return { total: cols.length,
                              filled: cols.filter(c => c !== empty).length };
                   }
                 }
                 return null; }"""
        )

    # ------------------------------------------------------------------
    # Operational data
    # ------------------------------------------------------------------
    def operational_metric(self, label: str) -> Optional[str]:
        block = self.page.locator(SEL_OPS_BLOCK).filter(has_text=label)
        if block.count() == 0:
            return None
        val = block.first.locator(SEL_OPS_VALUE)
        return val.first.inner_text().strip() if val.count() else None

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------
    def chart_panel(self, title: str) -> Optional[Locator]:
        node = self.page.get_by_text(re.compile(rf"^\s*{re.escape(title)}\s*$")).last
        if node.count() == 0:
            return None
        handle = node.evaluate_handle(
            """el => { let p = el;
                 for (let i = 0; i < 7 && p.parentElement; i++) {
                   p = p.parentElement;
                   if (p.querySelector('.apexcharts-canvas') ||
                       /No usage as yet/.test(p.textContent)) return p;
                 }
                 return null; }"""
        )
        el = handle.as_element()
        return None if el is None else el  # type: ignore[return-value]

    def chart_state(self, title: str) -> str:
        """'rendered' | 'empty' | 'missing'."""
        panel = self.chart_panel(title)
        if panel is None:
            return "missing"
        text = panel.inner_text()
        if re.search(r"no usage as yet|no data", text, re.I):
            return "empty"
        return "rendered" if panel.query_selector(SEL_CHART_CANVAS) else "missing"

    def chart_series_count(self, title: str) -> int:
        panel = self.chart_panel(title)
        if panel is None:
            return 0
        return len(panel.query_selector_all("svg path"))

    def chart_panel_text(self, title: str) -> str:
        panel = self.chart_panel(title)
        return panel.inner_text() if panel is not None else ""

    def chart_empty_icon_present(self, title: str) -> bool:
        panel = self.chart_panel(title)
        if panel is None:
            return False
        return bool(panel.query_selector("img, svg"))

    def hover_chart(self, title: str) -> bool:
        """Real pointer hover; returns True when the ApexCharts tooltip activates."""
        panel = self.chart_panel(title)
        if panel is None:
            return False
        canvas = panel.query_selector(SEL_CHART_CANVAS)
        if canvas is None:
            return False
        box = canvas.bounding_box()
        if not box:
            return False
        y = box["y"] + box["height"] / 2
        for frac in (0.3, 0.5, 0.7, 0.85):
            self.page.mouse.move(box["x"] + box["width"] * frac, y)
            self.page.wait_for_timeout(400)
            tip = canvas.query_selector(".apexcharts-tooltip")
            if tip and "apexcharts-active" in (tip.get_attribute("class") or ""):
                return True
        return False

    # ------------------------------------------------------------------
    # Quick Links
    # ------------------------------------------------------------------
    def quick_link(self, name: str) -> Optional[Locator]:
        loc = self.page.locator(SEL_QUICK_LINK).filter(has_text=name)
        return loc.first if loc.count() else None

    def click_quick_link(self, name: str) -> Dict[str, object]:
        """Click a quick link and report where it tried to go, without navigating."""
        self.reset_capture()
        before = self.page.url
        link = self.quick_link(name)
        if link is None:
            return {"found": False}
        link.click()
        self.page.wait_for_timeout(600)
        modals = self.page.locator(".ant-modal, .ant-drawer, [role=dialog]")
        visible_modals = [
            modals.nth(i).inner_text()[:80]
            for i in range(modals.count())
            if modals.nth(i).is_visible()
        ]
        return {
            "found": True,
            "opened": self.captured_opens(),
            "navigated": self.page.url != before,
            "url": self.page.url,
            "modals": visible_modals,
        }

    def close_any_modal(self) -> None:
        close = self.page.locator(".ant-modal-close, .ant-drawer-close")
        for i in range(close.count()):
            try:
                close.nth(i).click(timeout=2_000)
            except Exception:
                pass
        self.page.wait_for_timeout(400)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def sidebar(self) -> Locator:
        return self.page.locator(SEL_SIDEBAR).first

    def sidebar_text(self) -> str:
        return self.sidebar().inner_text()

    def sidebar_item(self, name: str) -> Optional[Locator]:
        loc = self.sidebar().locator(".ant-menu-item, .ant-menu-submenu").filter(
            has_text=re.compile(rf"^\s*{re.escape(name)}")
        )
        return loc.first if loc.count() else None

    def sidebar_item_is_active(self, name: str) -> bool:
        item = self.sidebar_item(name)
        if item is None:
            return False
        return item.evaluate(
            """el => {
                if (el.matches('[class*=appNavItemSelected]')) return true;
                if (el.querySelector('[class*=appNavItemSelected]')) return true;
                if (el.classList.contains('ant-menu-item-selected')) return true;
                const c = el.getAttribute('aria-current');
                return c === 'page' || c === 'true';
            }"""
        )

    def expand_sidebar_item(self, name: str) -> List[str]:
        """Expand a submenu and return its child item labels."""
        item = self.sidebar_item(name)
        if item is None:
            return []
        title = item.locator(".ant-menu-submenu-title")
        (title.first if title.count() else item).click()
        self.page.wait_for_timeout(1_000)
        kids = item.locator(".ant-menu-item")
        return [kids.nth(i).inner_text().strip() for i in range(kids.count())]

    def collapse_sidebar_item(self, name: str) -> None:
        item = self.sidebar_item(name)
        if item is None:
            return
        if "ant-menu-submenu-open" in (item.get_attribute("class") or ""):
            title = item.locator(".ant-menu-submenu-title")
            (title.first if title.count() else item).click()
            self.page.wait_for_timeout(600)

    # ------------------------------------------------------------------
    # Page-level
    # ------------------------------------------------------------------
    def main_text(self) -> str:
        return self.page.locator("main").first.inner_text()

    def visible_error_banners(self) -> List[str]:
        loc = self.page.locator("[role=alert], [class*=error i]")
        out = []
        for i in range(min(loc.count(), 20)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    out.append(el.inner_text())
            except Exception:
                pass
        return out
