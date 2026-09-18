"""Page object for the AI Agents "Agent Builder" IDE — the separate app
opened by `AIAgentsPage.manage_agent()` in a new tab, at
`/ai-agents/<agent-id>/<section>`. Distinct from the list page: this is a
per-agent workspace with its own sidebar (Instructions, Knowledge Base,
Tools, Card Builder, Variables, MCP, Deploy, Logs).

Only Instructions and Knowledge Base are covered here (the two sections
investigated 2026-09-18). The rest (Tools, Variables, MCP, Deploy, Logs)
remain unautomated — extend this file when one of them is next.

**Instructions** (fully covered): a model picker, a contenteditable system
prompt editor (`data-placeholder="Start typing instructions here..."`),
"Save & Run", and a genuine live chat preview on the right — the actual
CometChat message composer widget (`cometchat-message-composer__input`,
`data-placeholder="Ask anything"`). It takes ~10-15s after navigation to
finish mounting (a real websocket connection, same as the Sample App) —
wait for the composer to be visible rather than a fixed sleep. Sending a
message there is a real round trip to the configured model; the agent's
reply can be read back from the message bubbles
(`[class*="cometchat-message-bubble"]`) to verify instructions actually
took effect, not just that Save & Run returned success.

**Knowledge Base** (read-only here): the source list is APP-LEVEL SHARED,
not per-agent — the same sources (`https://www.cometchat.com/docs`,
`Complete_Manual-Testing.pdf`, `test`) appear regardless of which agent's
builder you're in. What's per-agent is only the "Attach to Agent" switch
in each row (`button[role="switch"]`, `aria-checked`). Confirmed live
2026-09-18. Writing to that switch on a pre-existing production source
(e.g. `Complete_Manual-Testing.pdf`, which belongs to the real "Customer
Support Agent") was deliberately not exercised here — it was blocked by
the harness's own shared-resource safety check when first tried, which is
the right call: toggling a real KB source's attachment is a shared-state
write, not an isolated one, even though a different agent's toggle is
scoped to that agent. `attach_source()`/`detach_source()`/`is_attached()`
below are implemented and DOM-verified structurally, but have not been
exercised against a real toggle end-to-end. Do that first against a
throwaway source added by `add_source()` (not yet implemented — the "Add
Source" flow itself hasn't been investigated) before trusting them in a
verification script, rather than against an existing shared source.
"""
from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage

SELECTORS = {
    "instructions_editor": "[data-placeholder='Start typing instructions here...']",
    "save_and_run_button": 'button:has-text("Save & Run")',
    "chat_composer": "[data-placeholder='Ask anything']",
    "message_bubble": "[class*='cometchat-message-bubble']",
    "kb_row_for": lambda name: f"xpath=//tr[.//*[contains(text(), {name!r})]]",
    "kb_attach_switch": "button[role='switch']",
}


class AIAgentBuilderPage(BasePage):
    """Driven with a real agent id — construct fresh per agent, unlike the
    list page whose PATH is fixed. `page` should be the NEW TAB returned by
    `AIAgentsPage.manage_agent()`.
    """

    def __init__(self, page: Page, app_id: str, base_url: str, agent_id: str):
        super().__init__(page, app_id, base_url)
        self.agent_id = agent_id

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open_instructions(self, force: bool = False) -> "AIAgentBuilderPage":
        self.goto(f"ai-agents/{self.agent_id}/instructions", force=force)
        self.page.wait_for_function(
            "() => !document.body.innerText.includes('Loading...')", timeout=15_000
        )
        return self

    def open_knowledge_base(self, force: bool = False) -> "AIAgentBuilderPage":
        self.goto(f"ai-agents/{self.agent_id}/knowledge-base", force=force)
        self.page.wait_for_timeout(4_500)  # table has no reliable "settled" marker yet
        return self

    # ------------------------------------------------------------------
    # Instructions — system prompt
    # ------------------------------------------------------------------
    def get_instructions(self) -> str:
        return self.page.locator(SELECTORS["instructions_editor"]).inner_text()

    def set_instructions(self, text: str) -> None:
        """Replace the system prompt with `text` and click Save & Run.
        Does not wait for the live preview to reflect it — call
        `send_preview_message()` afterward for that.
        """
        editor = self.page.locator(SELECTORS["instructions_editor"])
        editor.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.type(text)
        self.page.get_by_text("Save & Run", exact=True).click()
        self.page.wait_for_timeout(2_000)

    # ------------------------------------------------------------------
    # Instructions — live chat preview (real model round trip)
    # ------------------------------------------------------------------
    def send_preview_message(self, text: str, timeout_ms: int = 15_000) -> str:
        """Type `text` into the live preview composer, send it, and return
        the agent's reply text (the last non-empty message bubble).
        The composer takes ~10-15s to mount after navigation — this waits
        for it rather than assuming it's ready.
        """
        composer = self.page.locator(SELECTORS["chat_composer"])
        composer.wait_for(state="visible", timeout=20_000)
        composer.click()
        self.page.keyboard.type(text)
        self.page.keyboard.press("Enter")

        bubbles = self.page.locator(SELECTORS["message_bubble"])
        self.page.wait_for_timeout(timeout_ms)
        texts = [bubbles.nth(i).inner_text().strip() for i in range(bubbles.count())]
        texts = [t for t in texts if t]
        if not texts:
            raise RuntimeError("No reply appeared in the live chat preview after sending a message")
        return texts[-1]

    # ------------------------------------------------------------------
    # Knowledge Base — read-only inventory
    # ------------------------------------------------------------------
    def kb_source_names(self) -> list[str]:
        cells = self.page.locator("table tbody tr td:first-child .textEllipsis")
        return [cells.nth(i).inner_text().strip() for i in range(cells.count())]

    def _kb_row(self, source_name: str):
        # get_by_text with exact=False substring-matches case-insensitively
        # (e.g. "test" matches inside "Complete_Manual-Testing.pdf") —
        # exact=True on the specific name cell avoids that.
        cell = self.page.get_by_text(source_name, exact=True)
        return cell.locator("xpath=ancestor::tr")

    def kb_is_attached(self, source_name: str) -> bool:
        switch = self._kb_row(source_name).locator(SELECTORS["kb_attach_switch"])
        return switch.get_attribute("aria-checked") == "true"

    # ------------------------------------------------------------------
    # Knowledge Base — attach/detach (structurally verified, not yet
    # exercised end-to-end — see module docstring)
    # ------------------------------------------------------------------
    def attach_source(self, source_name: str) -> None:
        if self.kb_is_attached(source_name):
            return
        self._kb_row(source_name).locator(SELECTORS["kb_attach_switch"]).click()
        self.page.wait_for_timeout(1_500)

    def detach_source(self, source_name: str) -> None:
        if not self.kb_is_attached(source_name):
            return
        self._kb_row(source_name).locator(SELECTORS["kb_attach_switch"]).click()
        self.page.wait_for_timeout(1_500)
