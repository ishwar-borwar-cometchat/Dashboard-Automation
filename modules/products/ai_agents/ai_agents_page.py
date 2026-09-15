"""Page object for PRODUCTS > AI Agents.

The list page (`/ai-agents`) shows one card per agent — icon, name, a
Status switch, delete/edit icons, and a "Manage Agent" button. Each card's
outer container carries a CSS-module class containing "aiAgentBuilderCard"
(the hash suffix changes per build, the base name has not) — that's what
`CARD` below matches, rather than fragile ancestor-index xpaths.

"Manage Agent" opens a full Agent Builder IDE in a *new tab* — its own URL
(`/ai-agents/<agent-id>/instructions`), with sibling sections Knowledge
Base, Tools, Card Builder, Variables, MCP, Deploy, Logs each their own
route under the same agent id. That builder is a separate surface from
this list page and gets its own page object once more of it is automated.

"Add AI Agent" opens a side drawer (name + icon URL + description, name
and icon required, icon pre-filled with a sensible default) and, on
success, navigates the *same* tab straight into the new agent's builder —
different from Manage Agent's new-tab behavior. `add_agent()` below
navigates back to the list afterward so its post-condition is always
"back on the list, new card visible" regardless of that difference.

The edit icon opens an "Edit AI Agent" drawer — the same three fields as
Add, plus a read-only UID — and stays on the list after Save.

The delete icon has **no confirmation dialog** — clicking it deletes the
agent immediately (toast: "AI Agent deleted successfully"). Confirmed live
2026-09-15. `delete_agent()` reflects that: there's no confirm step to
drive, it just clicks and verifies removal.
"""
from __future__ import annotations

from typing import Optional

from playwright.sync_api import Page

from core.base_page import BasePage

SELECTORS = {
    "card": '[class*="aiAgentBuilderCard"]',
    "manage_agent_button": 'button:has-text("Manage Agent")',
    "delete_icon_button": 'button:has([class*="deleteIcon"])',
    "edit_icon_button": 'button:has([class*="editIcon"])',
    "add_agent_trigger": 'text="Add AI Agent"',
    "name_input": 'input[placeholder="Enter the agent name"]',
    "icon_input": 'input[placeholder="https://example.com/icon.png"]',
    "description_input": 'textarea[placeholder="Enter the description"]',
    "drawer_add_button": 'button:has-text("Add")',
    "drawer_save_button": 'button:has-text("Save")',
}


class AIAgentsPage(BasePage):
    PATH = "ai-agents"

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open(self, force: bool = False) -> "AIAgentsPage":
        self.goto(self.PATH, force=force)
        self._wait_for_list_settled()
        return self

    def _wait_for_list_settled(self, timeout_ms: int = 10_000) -> None:
        """The page renders a loading spinner with no cards and no empty-state
        text for a moment after navigation — reading either too early
        misreads that ambiguous frame. Wait for the add-agent trigger (always
        present once loaded) rather than a fixed sleep.
        """
        self.page.locator(SELECTORS["add_agent_trigger"]).first.wait_for(
            state="visible", timeout=timeout_ms
        )
        self.page.wait_for_timeout(500)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    def agent_names(self) -> list[str]:
        """Every agent name currently shown on the list page, in card order."""
        cards = self.page.locator(SELECTORS["card"])
        names = []
        for i in range(cards.count()):
            text = cards.nth(i).inner_text()
            # card text is "<name>\nManage Agent" (icon/toggle carry no text)
            names.append(text.split("\n")[0].strip())
        return names

    def exists(self, name: str) -> bool:
        return name in self.agent_names()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def add_agent(
        self,
        name: str,
        icon_url: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Open the Add AI Agent drawer, create `name`, and return to the list.

        Icon URL is left at its pre-filled default when `icon_url` is None.
        Raises if `name` isn't on the list afterward.
        """
        self.page.get_by_text("Add AI Agent", exact=False).click()
        self.page.wait_for_timeout(1_000)

        self.page.locator(SELECTORS["name_input"]).fill(name)

        if icon_url is not None:
            self.page.locator(SELECTORS["icon_input"]).first.fill(icon_url)

        if description is not None:
            self.page.locator(SELECTORS["description_input"]).fill(description)

        self.page.get_by_role("button", name="Add", exact=True).click()
        # Success navigates this same tab into the new agent's builder —
        # wait for that, then come back to the list so callers always land
        # on a consistent post-condition.
        self.page.wait_for_url("**/ai-agents/*/instructions", timeout=10_000)
        self.open(force=True)

        if not self.exists(name):
            raise RuntimeError(f"'{name}' not found on the AI Agents list after add_agent()")

    # ------------------------------------------------------------------
    # Manage (opens a new tab — caller owns its lifecycle)
    # ------------------------------------------------------------------
    def manage_agent(self, name: str) -> Page:
        """Click `name`'s Manage Agent button and return the new tab's Page."""
        card = self.page.locator(SELECTORS["card"], has_text=name)
        with self.page.context.expect_page() as new_page_info:
            card.locator(SELECTORS["manage_agent_button"]).click()
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        return new_page

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------
    def edit_agent(
        self,
        current_name: str,
        new_name: Optional[str] = None,
        icon_url: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Open `current_name`'s Edit AI Agent drawer and update the given
        fields (leaving any field not passed untouched). Stays on the list —
        unlike add_agent, editing does not navigate into the builder.
        """
        card = self.page.locator(SELECTORS["card"], has_text=current_name)
        card.locator(SELECTORS["edit_icon_button"]).click()
        self.page.wait_for_timeout(1_000)

        if new_name is not None:
            field = self.page.locator(SELECTORS["name_input"])
            field.fill("")
            field.fill(new_name)

        if icon_url is not None:
            field = self.page.locator(SELECTORS["icon_input"]).first
            field.fill("")
            field.fill(icon_url)

        if description is not None:
            field = self.page.locator(SELECTORS["description_input"])
            field.fill("")
            field.fill(description)

        self.page.get_by_role("button", name="Save", exact=True).click()
        self.page.wait_for_timeout(2_000)

        expect_name = new_name if new_name is not None else current_name
        if not self.exists(expect_name):
            raise RuntimeError(f"'{expect_name}' not found on the AI Agents list after edit_agent()")

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def delete_agent(self, name: str) -> None:
        """Click `name`'s delete icon. No confirmation dialog appears — this
        removes the agent immediately, so callers should be sure first.
        """
        card = self.page.locator(SELECTORS["card"], has_text=name)
        card.locator(SELECTORS["delete_icon_button"]).click()
        self.page.wait_for_timeout(2_000)

        if self.exists(name):
            raise RuntimeError(f"'{name}' still on the AI Agents list after delete_agent()")
