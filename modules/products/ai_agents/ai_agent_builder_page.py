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
scoped to that agent. `attach_source()`/`detach_source()` have since been
verified end-to-end (2026-09-18) against real shared sources, with the
harness's shared-resource permission explicitly granted for the specific
scripts that do it (see Dashboard-Automation/.claude/settings.local.json).
`add_text_source()` (2026-09-18) adds a brand-new, PERMANENT Text source
to the shared Knowledge Base — not disposable like a throwaway test
agent. Don't call it for routine test isolation; only when the intent is
actually to add real, lasting KB content.
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
    "kb_add_source_title": 'input[placeholder*="What This Text Represents"]',
    "kb_add_source_body": ".tiptap.ProseMirror",
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

    # ------------------------------------------------------------------
    # Knowledge Base — add a new Text source (PERMANENT shared write: this
    # adds a real, persistent source to the app-level Knowledge Base, not
    # something scoped to the current agent — every agent's builder will
    # see it afterward, same as the pre-existing sources. Confirmed live
    # 2026-09-18: "+ Add Source" opens a right-side drawer with Files/Text/
    # Links/Integrate tabs; the Text tab has a Title input
    # (placeholder "What This Text Represents eg. Product Documentation")
    # and a tiptap/ProseMirror rich-text body editor, submitted via an
    # "Add" button.
    # ------------------------------------------------------------------
    def add_text_source(self, title: str, body: str) -> None:
        self.page.get_by_text("Add Source", exact=True).click()
        self.page.wait_for_timeout(800)
        self.page.locator("[data-node-key='text']").click()
        self.page.wait_for_timeout(500)

        self.page.locator(SELECTORS["kb_add_source_title"]).fill(title)
        editor = self.page.locator(SELECTORS["kb_add_source_body"])
        editor.click()
        self.page.keyboard.type(body)

        self.page.get_by_role("button", name="Add", exact=True).click()
        self.page.wait_for_timeout(2_000)

        if title not in self.kb_source_names():
            raise RuntimeError(f"'{title}' not found in Knowledge Base source list after add_text_source()")
