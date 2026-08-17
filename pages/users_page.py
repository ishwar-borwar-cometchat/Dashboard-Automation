"""Page Object for CometChat Dashboard > User & Groups > Users (list view).

SELECTOR STATUS
---------------
The Overview module's selectors were verified against the live DOM. The Users
page could not be scanned (browser bridge unavailable), so the app-specific
selectors below are *inferred* from what the Overview scan established about
this dashboard:

    * Ant Design 5  -> .ant-table, .ant-modal, .ant-pagination, .ant-tabs,
                       .ant-select, .ant-picker, .ant-btn
    * CSS modules   -> style_<name>__<hash>, matched with [class*=<name>]
    * Controls are often div[role=button] rather than <button>/<a>

Every inferred selector is grouped in SELECTORS below with a `# INFERRED` tag.
Run utils/scan_users_page.js against the live page and correct that block —
nothing outside it should need touching.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from playwright.sync_api import Locator, Page

from .base_page import BasePage

# --- Expectations drawn from the test-case sheet ------------------------------

TABLE_COLUMNS = ["Name", "UID", "Role", "Created", "Actions"]
TABS = ["Active Users", "Deactivated Users"]
FILTER_CHIPS = ["UIDs", "Role", "Status", "Created At Date"]

ADD_USER_FIELDS = {
    "name": "Enter user name",
    "uid": "Enter UID",
    "tags": "Add a tag",
    "avatar": "https://example.com/avatar.png",
    "link": "https://example.com/profile",
    "metadata": "Enter JSON data",
}

SELECTORS = {
    # --- Ant Design primitives (high confidence) -----------------------------
    "table": ".ant-table",
    "table_body": ".ant-table-tbody",
    "row": ".ant-table-tbody tr.ant-table-row",
    "header_cell": ".ant-table-thead th",
    "pagination": ".ant-pagination",
    "page_next": ".ant-pagination-next",
    "page_prev": ".ant-pagination-prev",
    "page_size": ".ant-pagination-options",
    "tab": ".ant-tabs-tab",
    "tab_active": ".ant-tabs-tab-active",
    "modal": ".ant-modal",
    "modal_close": ".ant-modal-close",
    "modal_title": ".ant-modal-title",
    "form_error": ".ant-form-item-explain-error",
    "select": ".ant-select",
    "select_option": ".ant-select-item-option",
    "date_picker": ".ant-picker",
    "empty": ".ant-empty",
    "spin": ".ant-spin",
    "skeleton": ".ant-skeleton",
    "message": ".ant-message-notice",
    "popconfirm": ".ant-popconfirm",
    # --- App-specific, INFERRED — correct these after the scan ---------------
    "search_input": "input[placeholder*='Search' i]",          # INFERRED
    "filter_button": "button:has-text('Filter')",              # INFERRED
    "add_user_button": "button:has-text('Add User')",          # INFERRED
    "row_actions": "td:last-child",                            # INFERRED
    "toolbar": "[class*=toolbar i], [class*=tableHeader i]",   # INFERRED
}


class UsersPage(BasePage):
    PATH = "users"

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open(self) -> "UsersPage":
        self.goto(self.PATH)
        # Either the table or an empty state must settle before we assert.
        try:
            self.page.wait_for_selector(
                f"{SELECTORS['table']}, {SELECTORS['empty']}", timeout=30_000
            )
        except Exception:
            pass
        self.page.wait_for_timeout(1_200)
        return self

    def open_via_sidebar(self) -> "UsersPage":
        sidebar = self.page.locator(".ant-layout-sider").first
        parent = sidebar.locator(".ant-menu-submenu").filter(has_text="User & Groups").first
        if "ant-menu-submenu-open" not in (parent.get_attribute("class") or ""):
            parent.locator(".ant-menu-submenu-title").click()
            self.page.wait_for_timeout(800)
        parent.locator(".ant-menu-item").filter(has_text=re.compile(r"^\s*Users\s*$")).click()
        self.wait_for_network_idle()
        return self

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------
    def table(self) -> Locator:
        return self.page.locator(SELECTORS["table"]).first

    def has_table(self) -> bool:
        return self.page.locator(SELECTORS["table"]).count() > 0

    def column_headers(self) -> List[str]:
        cells = self.page.locator(SELECTORS["header_cell"])
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def rows(self) -> Locator:
        return self.page.locator(SELECTORS["row"])

    def row_count(self) -> int:
        return self.rows().count()

    def row_for_uid(self, uid: str) -> Optional[Locator]:
        loc = self.rows().filter(has_text=uid)
        return loc.first if loc.count() else None

    def row_cells(self, index: int = 0) -> List[str]:
        row = self.rows().nth(index)
        cells = row.locator("td")
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def row_has_avatar(self, index: int = 0) -> bool:
        row = self.rows().nth(index)
        return row.evaluate(
            """el => {
                if (el.querySelector('img, .ant-avatar')) return true;
                return [...el.querySelectorAll('*')].some(k => {
                    const s = getComputedStyle(k);
                    return (s.backgroundImage && s.backgroundImage !== 'none') ||
                           ((s.maskImage || s.webkitMaskImage || 'none') !== 'none');
                });
            }"""
        )

    def row_action_controls(self, index: int = 0) -> int:
        row = self.rows().nth(index)
        return row.locator(
            f"{SELECTORS['row_actions']} button, {SELECTORS['row_actions']} [role=button], "
            f"{SELECTORS['row_actions']} svg, {SELECTORS['row_actions']} img"
        ).count()

    def row_action(self, index: int, position: int) -> Optional[Locator]:
        """Action control by position: 0=view, 1=deactivate, 2=delete (per USR_005)."""
        row = self.rows().nth(index)
        controls = row.locator(
            f"{SELECTORS['row_actions']} button, {SELECTORS['row_actions']} [role=button]"
        )
        if controls.count() > position:
            return controls.nth(position)
        icons = row.locator(f"{SELECTORS['row_actions']} svg, {SELECTORS['row_actions']} img")
        return icons.nth(position) if icons.count() > position else None

    def open_user(self, uid: str) -> bool:
        row = self.row_for_uid(uid)
        if row is None:
            return False
        idx = self._row_index_for(uid)
        control = self.row_action(idx, 0)
        if control is None:
            return False
        control.click()
        self.page.wait_for_timeout(2_000)
        return True

    def _row_index_for(self, uid: str) -> int:
        rows = self.rows()
        for i in range(rows.count()):
            if uid in rows.nth(i).inner_text():
                return i
        return -1

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def tabs(self) -> List[str]:
        loc = self.page.locator(SELECTORS["tab"])
        return [loc.nth(i).inner_text().strip() for i in range(loc.count())]

    def active_tab(self) -> Optional[str]:
        loc = self.page.locator(SELECTORS["tab_active"])
        return loc.first.inner_text().strip() if loc.count() else None

    def switch_tab(self, name: str) -> None:
        self.page.locator(SELECTORS["tab"]).filter(has_text=name).first.click()
        self.page.wait_for_timeout(1_800)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search_box(self) -> Optional[Locator]:
        loc = self.page.locator(SELECTORS["search_input"])
        return loc.first if loc.count() else None

    def search(self, term: str) -> None:
        box = self.search_box()
        if box is None:
            raise AssertionError("No search input found on the Users page")
        box.fill(term)
        self.page.wait_for_timeout(1_800)  # allow debounce + fetch

    def clear_search(self) -> None:
        box = self.search_box()
        if box is not None:
            box.fill("")
            self.page.wait_for_timeout(1_800)

    def count_requests_while_typing(self, term: str, url_fragment: str = "user") -> int:
        """Type a term and count matching XHRs — evidence for debounce (USR_060)."""
        hits: List[str] = []

        def on_request(req):
            if req.resource_type in ("xhr", "fetch") and url_fragment in req.url.lower():
                hits.append(req.url)

        box = self.search_box()
        if box is None:
            raise AssertionError("No search input found")
        box.fill("")
        self.page.wait_for_timeout(1_200)
        self.page.on("request", on_request)
        box.type(term, delay=60)
        self.page.wait_for_timeout(2_500)
        self.page.remove_listener("request", on_request)
        return len(hits)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    def filter_button(self) -> Optional[Locator]:
        loc = self.page.locator(SELECTORS["filter_button"])
        if loc.count():
            return loc.first
        alt = self.page.get_by_role("button", name=re.compile("filter", re.I))
        return alt.first if alt.count() else None

    def open_filters(self) -> bool:
        btn = self.filter_button()
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(1_000)
        return True

    def filter_chip(self, name: str) -> Optional[Locator]:
        loc = self.page.get_by_text(re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
        return loc.first if loc.count() else None

    def active_filter_indicators(self) -> List[str]:
        loc = self.page.locator(".ant-tag, [class*=chip i], [class*=badge i], .ant-badge")
        out = []
        for i in range(min(loc.count(), 20)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    out.append(el.inner_text().strip())
            except Exception:
                pass
        return [t for t in out if t]

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def pagination(self) -> Optional[Locator]:
        loc = self.page.locator(SELECTORS["pagination"])
        return loc.first if loc.count() else None

    def has_pagination(self) -> bool:
        pag = self.pagination()
        return pag is not None and pag.is_visible()

    def goto_next_page(self) -> bool:
        nxt = self.page.locator(SELECTORS["page_next"])
        if not nxt.count() or "disabled" in (nxt.first.get_attribute("class") or ""):
            return False
        nxt.first.click()
        self.page.wait_for_timeout(2_000)
        return True

    def goto_prev_page(self) -> bool:
        prev = self.page.locator(SELECTORS["page_prev"])
        if not prev.count() or "disabled" in (prev.first.get_attribute("class") or ""):
            return False
        prev.first.click()
        self.page.wait_for_timeout(2_000)
        return True

    def current_page(self) -> Optional[str]:
        active = self.page.locator(".ant-pagination-item-active")
        return active.first.inner_text().strip() if active.count() else None

    def set_page_size(self, size: int) -> bool:
        opts = self.page.locator(SELECTORS["page_size"])
        if not opts.count():
            return False
        opts.first.click()
        self.page.wait_for_timeout(700)
        option = self.page.locator(SELECTORS["select_option"]).filter(has_text=str(size))
        if not option.count():
            return False
        option.first.click()
        self.page.wait_for_timeout(2_000)
        return True

    def sort_by(self, column: str) -> bool:
        header = self.page.locator(SELECTORS["header_cell"]).filter(has_text=column)
        if not header.count():
            return False
        header.first.click()
        self.page.wait_for_timeout(1_800)
        return True

    def column_values(self, column: str) -> List[str]:
        headers = self.column_headers()
        idx = next((i for i, h in enumerate(headers) if column.lower() in h.lower()), None)
        if idx is None:
            return []
        rows = self.rows()
        return [rows.nth(i).locator("td").nth(idx).inner_text().strip() for i in range(rows.count())]

    # ------------------------------------------------------------------
    # Add User modal
    # ------------------------------------------------------------------
    def add_user_button(self) -> Optional[Locator]:
        loc = self.page.locator(SELECTORS["add_user_button"])
        if loc.count():
            return loc.first
        alt = self.page.get_by_role("button", name=re.compile(r"add user", re.I))
        return alt.first if alt.count() else None

    def open_add_user(self) -> bool:
        btn = self.add_user_button()
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(1_200)
        return self.modal_open()

    def modal(self) -> Locator:
        return self.page.locator(SELECTORS["modal"]).first

    def modal_open(self) -> bool:
        loc = self.page.locator(SELECTORS["modal"])
        return loc.count() > 0 and loc.first.is_visible()

    def modal_title(self) -> str:
        loc = self.page.locator(SELECTORS["modal_title"])
        return loc.first.inner_text().strip() if loc.count() else ""

    def modal_field(self, key: str) -> Optional[Locator]:
        """Find a form field by its documented placeholder."""
        placeholder = ADD_USER_FIELDS.get(key)
        if not placeholder:
            return None
        loc = self.modal().locator(
            f"input[placeholder='{placeholder}'], textarea[placeholder='{placeholder}']"
        )
        if loc.count():
            return loc.first
        token = placeholder.split()[0]
        loose = self.modal().locator(
            f"input[placeholder*='{token}' i], textarea[placeholder*='{token}' i]"
        )
        return loose.first if loose.count() else None

    def modal_placeholders(self) -> List[str]:
        loc = self.modal().locator("input, textarea")
        out = []
        for i in range(loc.count()):
            ph = loc.nth(i).get_attribute("placeholder")
            if ph:
                out.append(ph)
        return out

    def role_select(self) -> Optional[Locator]:
        loc = self.modal().locator(SELECTORS["select"])
        return loc.first if loc.count() else None

    def fill_user_form(self, **values: str) -> None:
        for key, value in values.items():
            field = self.modal_field(key)
            if field is not None:
                field.fill(value)

    def save_modal(self) -> None:
        btn = self.modal().get_by_role("button", name=re.compile(r"save|create|add|submit", re.I))
        (btn.first if btn.count() else self.modal().locator("button").last).click()
        self.page.wait_for_timeout(2_500)

    def cancel_modal(self) -> None:
        btn = self.modal().get_by_role("button", name=re.compile(r"cancel", re.I))
        if btn.count():
            btn.first.click()
            self.page.wait_for_timeout(1_000)

    def close_modal_x(self) -> None:
        loc = self.page.locator(SELECTORS["modal_close"])
        if loc.count():
            loc.first.click()
            self.page.wait_for_timeout(1_000)

    def form_errors(self) -> List[str]:
        loc = self.page.locator(SELECTORS["form_error"])
        errors = [loc.nth(i).inner_text().strip() for i in range(loc.count())]
        toast = self.page.locator(SELECTORS["message"])
        for i in range(toast.count()):
            try:
                if toast.nth(i).is_visible():
                    errors.append(toast.nth(i).inner_text().strip())
            except Exception:
                pass
        return [e for e in errors if e]

    # ------------------------------------------------------------------
    # Row actions / confirmations
    # ------------------------------------------------------------------
    def confirm_dialog(self) -> Optional[Locator]:
        for sel in (SELECTORS["popconfirm"], SELECTORS["modal"], "[role=dialog]"):
            loc = self.page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return loc.first
        return None

    def confirm_dialog_text(self) -> str:
        dlg = self.confirm_dialog()
        return dlg.inner_text() if dlg is not None else ""

    def accept_confirm(self) -> None:
        dlg = self.confirm_dialog()
        if dlg is None:
            return
        btn = dlg.get_by_role(
            "button", name=re.compile(r"^(ok|yes|confirm|delete|deactivate|remove)$", re.I)
        )
        (btn.first if btn.count() else dlg.locator("button").last).click()
        self.page.wait_for_timeout(2_500)

    def dismiss_confirm(self) -> None:
        dlg = self.confirm_dialog()
        if dlg is None:
            return
        btn = dlg.get_by_role("button", name=re.compile(r"^(cancel|no)$", re.I))
        if btn.count():
            btn.first.click()
        else:
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(1_200)

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def empty_state_text(self) -> str:
        loc = self.page.locator(SELECTORS["empty"])
        if loc.count():
            return loc.first.inner_text().strip()
        return ""

    def is_loading(self) -> bool:
        for sel in (SELECTORS["spin"], SELECTORS["skeleton"]):
            loc = self.page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return True
        return False

    def visible_error_banners(self) -> List[str]:
        loc = self.page.locator("[role=alert], .ant-alert-error, [class*=error i]")
        out = []
        for i in range(min(loc.count(), 20)):
            try:
                if loc.nth(i).is_visible():
                    out.append(loc.nth(i).inner_text().strip())
            except Exception:
                pass
        return [t for t in out if t]

    def main_text(self) -> str:
        return self.page.locator("main").first.inner_text()
