"""Page Object for CometChat Dashboard > Users > <user> detail page.

Covers the General, Friends and Groups tabs (USR_025–USR_042, USR_075–USR_085).
Selectors marked `# INFERRED` need confirming against the live DOM — see the
note at the top of users_page.py.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from playwright.sync_api import Locator

from .base_page import BasePage
from .users_page import SELECTORS

DETAIL_TABS = ["General", "Friends", "Groups"]

DETAIL_FIELDS = ["Name", "UID", "Role", "Tags", "Avatar", "Link", "Metadata", "Created"]


class UserDetailPage(BasePage):
    """Assumes navigation already happened (via UsersPage.open_user or a deep link)."""

    def open_uid(self, uid: str) -> "UserDetailPage":
        self.goto(f"users/{uid}")
        self.page.wait_for_timeout(2_500)
        return self

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    def header_text(self) -> str:
        header = self.page.locator("header, [class*=Head i], [class*=header i]").first
        try:
            return header.inner_text()
        except Exception:
            return self.page.locator("main").first.inner_text()[:200]

    def back_button(self) -> Optional[Locator]:
        candidates = [
            self.page.get_by_role("button", name=re.compile(r"back|←|arrow", re.I)),
            self.page.locator("[class*=back i]"),
            self.page.locator("[aria-label*='back' i]"),
        ]
        for loc in candidates:
            if loc.count():
                return loc.first
        return None

    def go_back(self) -> bool:
        btn = self.back_button()
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(2_000)
        return True

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def tabs(self) -> List[str]:
        loc = self.page.locator(SELECTORS["tab"])
        return [loc.nth(i).inner_text().strip() for i in range(loc.count())]

    def active_tab(self) -> Optional[str]:
        loc = self.page.locator(SELECTORS["tab_active"])
        return loc.first.inner_text().strip() if loc.count() else None

    def switch_tab(self, name: str) -> bool:
        loc = self.page.locator(SELECTORS["tab"]).filter(has_text=name)
        if not loc.count():
            return False
        loc.first.click()
        self.page.wait_for_timeout(2_000)
        return True

    # ------------------------------------------------------------------
    # General tab — Details card
    # ------------------------------------------------------------------
    def details_card(self) -> Locator:
        card = self.page.locator(".ant-card, [class*=detail i], [class*=Details i]").filter(
            has_text=re.compile("UID", re.I)
        )
        return card.first if card.count() else self.page.locator("main").first

    def detail_value(self, label: str) -> Optional[str]:
        """Read a labelled value from the Details card."""
        node = self.details_card().get_by_text(
            re.compile(rf"^\s*{re.escape(label)}\s*:?\s*$", re.I)
        )
        if not node.count():
            return None
        return node.first.evaluate(
            """el => {
                 const sib = el.nextElementSibling;
                 if (sib && sib.textContent.trim()) return sib.textContent.trim();
                 let p = el.parentElement;
                 for (let i = 0; i < 3 && p; i++) {
                   const t = p.textContent.trim();
                   const stripped = t.replace(el.textContent.trim(), '').trim();
                   if (stripped) return stripped.split('\\n')[0].trim();
                   p = p.parentElement;
                 }
                 return null;
               }"""
        )

    def detail_labels_present(self) -> List[str]:
        text = self.details_card().inner_text()
        return [f for f in DETAIL_FIELDS if re.search(rf"\b{re.escape(f)}\b", text, re.I)]

    def edit_button(self) -> Optional[Locator]:
        loc = self.details_card().get_by_role("button", name=re.compile(r"^\s*edit\s*$", re.I))
        if loc.count():
            return loc.first
        alt = self.page.get_by_role("button", name=re.compile(r"^\s*edit\s*$", re.I))
        return alt.first if alt.count() else None

    def click_edit(self) -> bool:
        btn = self.edit_button()
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(1_500)
        return True

    # ------------------------------------------------------------------
    # General tab — Auth Tokens
    # ------------------------------------------------------------------
    def auth_tokens_section(self) -> Optional[Locator]:
        loc = self.page.locator("section, .ant-card, div").filter(
            has_text=re.compile(r"Auth Tokens", re.I)
        )
        return loc.last if loc.count() else None

    def auth_tokens_visible(self) -> bool:
        return bool(re.search(r"Auth Tokens", self.page.locator("main").first.inner_text(), re.I))

    def create_token_button(self) -> Optional[Locator]:
        loc = self.page.get_by_role("button", name=re.compile(r"create auth token", re.I))
        if loc.count():
            return loc.first
        alt = self.page.get_by_text(re.compile(r"\+?\s*Create Auth Token", re.I))
        return alt.first if alt.count() else None

    def token_rows(self) -> Locator:
        section = self.auth_tokens_section()
        base = section if section is not None else self.page
        return base.locator("tbody tr")

    def token_row_count(self) -> int:
        try:
            return self.token_rows().count()
        except Exception:
            return 0

    def create_token(self) -> bool:
        btn = self.create_token_button()
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(2_500)
        return True

    def token_cell_text(self, index: int = 0) -> str:
        rows = self.token_rows()
        if rows.count() <= index:
            return ""
        return rows.nth(index).inner_text().strip()

    def token_is_masked(self, index: int = 0) -> bool:
        """USR_082 — token should not be shown in full by default."""
        text = self.token_cell_text(index)
        if not text:
            return False
        if re.search(r"[*•·●]{4,}|\.\.\.|…", text):
            return True
        # No long unbroken token-shaped run visible == effectively masked/truncated.
        return not re.search(r"[A-Za-z0-9]{24,}", text)

    def token_plaintext_in_dom(self) -> List[int]:
        """USR_081 — lengths of token-shaped runs in the section markup.

        Mirrors the OV_052 check that caught the Auth Key sitting in a
        display:none node on the Overview page.
        """
        section = self.auth_tokens_section()
        if section is None:
            return []
        html = section.inner_html()
        return [len(m) for m in re.findall(r"[A-Za-z0-9]{24,}", html)]

    def token_hidden_nodes(self) -> int:
        """Count non-displayed nodes inside the tokens section holding token-shaped text."""
        section = self.auth_tokens_section()
        if section is None:
            return 0
        return section.evaluate(
            """el => [...el.querySelectorAll('*')].filter(n => {
                 if (n.children.length) return false;
                 const t = (n.textContent || '').trim();
                 if (!/[A-Za-z0-9]{24,}/.test(t)) return false;
                 const s = getComputedStyle(n);
                 return s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0';
               }).length"""
        )

    def copy_token(self, index: int = 0) -> bool:
        rows = self.token_rows()
        if rows.count() <= index:
            return False
        row = rows.nth(index)
        btn = row.get_by_role("button", name=re.compile(r"copy", re.I))
        target = btn.first if btn.count() else row.locator("button, [role=button]").first
        if not target.count():
            return False
        target.click()
        self.page.wait_for_timeout(900)
        return True

    def delete_token(self, index: int = 0) -> bool:
        rows = self.token_rows()
        if rows.count() <= index:
            return False
        row = rows.nth(index)
        btn = row.get_by_role("button", name=re.compile(r"delete|remove|trash", re.I))
        target = btn.first if btn.count() else row.locator("button, [role=button]").last
        if not target.count():
            return False
        target.click()
        self.page.wait_for_timeout(1_200)
        return True

    # ------------------------------------------------------------------
    # Friends / Groups tabs
    # ------------------------------------------------------------------
    def list_rows(self) -> Locator:
        return self.page.locator(f"{SELECTORS['row']}, tbody tr")

    def list_row_count(self) -> int:
        try:
            return self.list_rows().count()
        except Exception:
            return 0

    def list_headers(self) -> List[str]:
        loc = self.page.locator(SELECTORS["header_cell"])
        return [loc.nth(i).inner_text().strip() for i in range(loc.count())]

    def add_button(self, kind: str) -> Optional[Locator]:
        """kind: 'Friends' or 'Group'."""
        loc = self.page.get_by_role("button", name=re.compile(rf"add {kind}", re.I))
        if loc.count():
            return loc.first
        alt = self.page.get_by_text(re.compile(rf"\+?\s*Add {kind}", re.I))
        return alt.first if alt.count() else None

    def open_add_dialog(self, kind: str) -> bool:
        btn = self.add_button(kind)
        if btn is None:
            return False
        btn.click()
        self.page.wait_for_timeout(1_500)
        loc = self.page.locator(f"{SELECTORS['modal']}, [role=dialog]")
        return loc.count() > 0 and loc.first.is_visible()

    def dialog_search(self, term: str) -> bool:
        dlg = self.page.locator(f"{SELECTORS['modal']}, [role=dialog]").first
        box = dlg.locator("input")
        if not box.count():
            return False
        box.first.fill(term)
        self.page.wait_for_timeout(1_500)
        return True

    def dialog_options_text(self) -> str:
        dlg = self.page.locator(f"{SELECTORS['modal']}, [role=dialog]")
        return dlg.first.inner_text() if dlg.count() else ""

    def close_dialog(self) -> None:
        close = self.page.locator(SELECTORS["modal_close"])
        if close.count():
            close.first.click()
        else:
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(1_000)

    def tab_search(self, term: str) -> bool:
        """Search box on the Friends/Groups tab itself (not the add dialog)."""
        box = self.page.locator("main input[placeholder*='Search' i]")
        if not box.count():
            return False
        box.first.fill(term)
        self.page.wait_for_timeout(1_500)
        return True

    def remove_row(self, index: int = 0) -> bool:
        rows = self.list_rows()
        if rows.count() <= index:
            return False
        row = rows.nth(index)
        btn = row.get_by_role("button", name=re.compile(r"remove|delete|×|x", re.I))
        target = btn.first if btn.count() else row.locator("button, [role=button]").last
        if not target.count():
            return False
        target.click()
        self.page.wait_for_timeout(1_200)
        return True

    def empty_state_text(self) -> str:
        loc = self.page.locator(SELECTORS["empty"])
        if loc.count():
            return loc.first.inner_text().strip()
        return self.page.locator("main").first.inner_text()

    def main_text(self) -> str:
        return self.page.locator("main").first.inner_text()
