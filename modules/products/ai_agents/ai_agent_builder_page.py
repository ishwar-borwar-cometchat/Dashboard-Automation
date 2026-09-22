"""Page object for the AI Agents "Agent Builder" IDE — the separate app
opened by `AIAgentsPage.manage_agent()` in a new tab, at
`/ai-agents/<agent-id>/<section>`. Distinct from the list page: this is a
per-agent workspace with its own sidebar (Instructions, Knowledge Base,
Tools, Card Builder, Variables, MCP, Deploy, Logs).

Instructions, Knowledge Base, and Variables (including real @-picker chip
insertion + runtime substitution verification) are covered here. Tools,
MCP, Deploy, and Logs remain unautomated — extend this file when one of
them is next.

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
    "var_name_input": 'input[placeholder*="userName, productId"]',
    "var_description_input": 'textarea[placeholder="Describe what this variable is used for"]',
    "var_constant_value_input": 'input[placeholder="Enter the constant value"]',
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
        # "Select all" is Cmd+A on a Mac and Ctrl+A elsewhere. Plain Control+A on a Mac only moves the cursor to
        # the start of the line, which left the OLD prompt in place behind the new one on any agent that already
        # had instructions. ControlOrMeta picks the right key, and Backspace clears the selection.
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Backspace")
        self.page.keyboard.type(text)
        typed = " ".join(editor.inner_text().split())
        if " ".join(text.split()) not in typed or len(typed) > len(" ".join(text.split())) + 5:
            raise RuntimeError(
                "The Instructions editor does not hold exactly the new text (old text left behind?): "
                f"expected {text[:60]!r}, editor shows {typed[:100]!r}"
            )
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
        # exact=True on the specific name cell avoids that. Some apps have
        # the SAME source name added more than once (a real data duplicate,
        # not a script bug) — .first keeps this from raising a Playwright
        # strict-mode error; it always resolves to the same row (the first
        # one in table order) across calls within one page.
        cell = self.page.get_by_text(source_name, exact=True)
        return cell.locator("xpath=ancestor::tr").first

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

    def delete_source(self, source_name: str) -> None:
        """Delete a Knowledge Base source from the whole app (PERMANENT — sources are shared by every agent).
        Clicks the row's trash icon, answers "Do you want to delete this source?" with Yes, then waits until the
        row is gone. Raises if it is still listed afterwards.
        """
        row = self._kb_row(source_name)
        if row.count() != 1:
            raise RuntimeError(f"Expected exactly one Knowledge Base row named {source_name!r}, found {row.count()}")
        row.locator(".style_actionButtons__b9l1r button, td:last-child button").last.click()
        self.page.locator(".ant-popover:visible button:has-text('Yes')").click()
        self.page.wait_for_timeout(2_500)
        self.open_knowledge_base(force=True)
        if source_name in self.kb_source_names():
            raise RuntimeError(f"{source_name!r} is still on the Knowledge Base list after delete_source()")

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

    # Links tab (data-node-key='link'): "Scrape Links" / "Individual Links"
    # radios (Individual is the default) and one input with a fixed
    # "https://" prefix (placeholder www.example.com), submitted via
    # "Add Links". PERMANENT shared write, same caution as add_text_source().
    def add_link_source(self, url: str) -> None:
        bare = url.replace("https://", "").replace("http://", "")
        self.page.get_by_text("Add Source", exact=True).click()
        self.page.wait_for_timeout(800)
        self.page.locator("[data-node-key='link']").click()
        self.page.wait_for_timeout(600)
        self.page.locator('input[placeholder="www.example.com"]').fill(bare)
        self.page.get_by_role("button", name="Add Links").click()
        self.page.wait_for_timeout(2_500)
        if not any(bare in n for n in self.kb_source_names()):
            raise RuntimeError(f"'{url}' not found in Knowledge Base source list after add_link_source()")

    # Files tab (data-node-key='file'): drag-and-drop zone, PDF/DOCX/TXT, max
    # 10 files / 15 MB each, backed by a hidden <input type=file>. PERMANENT
    # shared write.
    def add_file_source(self, path: str) -> None:
        import os
        self.page.get_by_text("Add Source", exact=True).click()
        self.page.wait_for_timeout(800)
        self.page.locator("[data-node-key='file']").click()
        self.page.wait_for_timeout(600)
        self.page.locator("input[type='file']").first.set_input_files(path)
        self.page.wait_for_timeout(1_500)
        for label in ("Upload", "Add Files", "Add File", "Add"):
            btn = self.page.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                break
        self.page.wait_for_timeout(3_000)
        if os.path.basename(path) not in self.kb_source_names():
            raise RuntimeError(f"'{os.path.basename(path)}' not found in Knowledge Base source list after add_file_source()")

    def kb_source_indexed(self, source_name: str) -> bool:
        """True once the source's row shows the 'Indexed' status."""
        cell = self.page.locator("table tbody tr").filter(has_text=source_name)
        return cell.count() > 0 and "Indexed" in cell.first.inner_text()

    def wait_sources_indexed(self, names: list, timeout_s: int = 240) -> dict:
        import time
        deadline = time.time() + timeout_s
        state = {n: False for n in names}
        while time.time() < deadline:
            self.open_knowledge_base(force=True)
            state = {n: self.kb_source_indexed(n) for n in names}
            if all(state.values()):
                break
            self.page.wait_for_timeout(8_000)
        return state

    # ------------------------------------------------------------------
    # Variables — read-only inventory (both Auth and Custom tabs)
    # ------------------------------------------------------------------
    def open_variables(self, force: bool = False) -> "AIAgentBuilderPage":
        self.goto(f"ai-agents/{self.agent_id}/variables", force=force)
        self.page.wait_for_timeout(2_500)
        return self

    def open_custom_variables_tab(self) -> None:
        self.page.get_by_text("Custom Variables", exact=True).click()
        self.page.wait_for_timeout(1_000)

    def custom_variable_names(self) -> list[str]:
        """Names of existing custom variables, or [] if none yet (the
        'No Custom Variables Yet' empty state)."""
        if self.page.get_by_text("No Custom Variables Yet").count():
            return []
        return [t.strip() for t in self.page.locator("table tbody tr td:first-child").all_inner_texts()]

    def custom_variable_usage_status(self, name: str) -> str:
        """Reads the row's usage badge — "Not Used" (gray) until the
        variable has actually been referenced in a SAVED, running
        instruction; flips to "In Use" (green) after — confirmed live
        2026-09-18. The badge is its own <td>, matched here by position
        (second-to-last cell, right before the actions column) rather than
        a hardcoded class name, since the two states use different button
        classes. Call from the Custom Variables tab. Raises if the row
        isn't there.
        """
        row = self.page.get_by_text(name, exact=True).locator("xpath=ancestor::tr")
        if not row.count():
            raise RuntimeError(f"Custom Variable '{name}' not found on the Custom Variables tab")
        cells = row.locator("td")
        return cells.nth(cells.count() - 2).inner_text().strip()

    # ------------------------------------------------------------------
    # Variables — add a Custom Variable (Constant source type only so far;
    # Message Metadata / User Metadata source types are structurally known
    # — a "Source Path" dot-path + optional "Default Value" fallback — but
    # not yet automated).
    #
    # SCOPE, confirmed live 2026-09-18: Custom Variables are APP-LEVEL
    # SHARED, exactly like Knowledge Base sources — NOT per-agent. A
    # variable created on one agent (even a disposable one, even after
    # that agent is deleted) appears on every other agent's Variables tab,
    # verified against both "Knowledge Assistant" and "Weather" (an agent
    # never otherwise touched). Same shared-resource caution applies as
    # Knowledge Base: don't add one casually, and clean up test variables
    # via the row's delete icon (a "Delete Variable" confirm dialog: Yes/No)
    # rather than leaving them in the real shared list.
    #
    # RUNTIME SUBSTITUTION — reliably automatable once the editor is given
    # real waits between steps (see insert_custom_variable_chip below).
    # 2026-09-18 history: first attempt looked like a real bug (chip
    # inserted correctly, but the live reply echoed the literal
    # "@var-custom:..." text instead of the real value); a careful re-test
    # exposed the actual problem was this script's own too-fast interaction
    # with the rich-text editor (visibly duplicated instruction text, a
    # Save & Run that silently failed to persist) — RETRACTED as a false
    # positive, confirmed by the user's own manual reproduction working.
    # A follow-up exploration (same day) proved the mechanism itself is
    # sound when driven slowly: category click -> item click inserts a real
    # `data-mention-token` chip (`isVariable: true`, `variableKey: <name>`),
    # and it survives Save & Run + a fresh page reload intact, no
    # duplication. See insert_custom_variable_chip() for the real, working
    # sequence.
    # ------------------------------------------------------------------
    def add_custom_variable_constant(self, name: str, value: str, description: str = "") -> None:
        self.page.get_by_role("button", name="Add Custom Variable").click()
        self.page.wait_for_timeout(800)

        self.page.locator(SELECTORS["var_name_input"]).fill(name)
        if description:
            self.page.locator(SELECTORS["var_description_input"]).fill(description)
        # Source Type defaults to "Constant" already — no dropdown interaction needed.
        self.page.locator(SELECTORS["var_constant_value_input"]).fill(value)

        self.page.get_by_role("button", name="Add", exact=True).click()
        self.page.wait_for_timeout(1_500)

        if name not in self.custom_variable_names():
            raise RuntimeError(f"'{name}' not found in Custom Variables list after add_custom_variable_constant()")

    def delete_custom_variable(self, name: str) -> None:
        """Delete a Custom Variable via its row's delete icon + Yes confirm.
        Call from the Custom Variables tab (open_variables() +
        open_custom_variables_tab() first). No-ops if the row isn't there.
        """
        row = self.page.get_by_text(name, exact=True).locator("xpath=ancestor::tr")
        if not row.count():
            return
        row.locator(".style_deleteIcon__fZNeS").click()
        self.page.wait_for_timeout(800)
        yes_btn = self.page.get_by_role("button", name="Yes", exact=True)
        if yes_btn.count():
            yes_btn.click()
            self.page.wait_for_timeout(1_200)

    # ------------------------------------------------------------------
    # Instructions — insert a REAL @-picker reference chip (not plain text)
    # for a Custom Variable, then optional trailing text. Confirmed live
    # 2026-09-18: typing "@" opens a categories menu
    # (.styles_categoryName__wP5TP -- Tools/MCP Tools/Front-end
    # Actions/Auth Variables/Custom Variables, each with an item count);
    # clicking "Custom Variables" drills into its item list
    # (.styles_itemName__raxTD spans); clicking the variable's name inserts
    # a `<span data-mention-token='{"isVariable":true,"variableCategory":
    # "custom","variableKey":"<name>",...}'><strong>@var-custom:<name>
    # </strong></span>` chip. This is DIFFERENT from typing the raw
    # "@var-custom:<name>" text, which stays plain text and does NOT
    # substitute at runtime.
    #
    # Timing matters: each step needs a real wait (not zero, not a single
    # huge sleep at the end) — driving this too fast in one burst is what
    # produced duplicated text and silently-failed saves in an earlier
    # attempt (see the retraction note above add_custom_variable_constant).
    # This sequence (300-1200ms between each of: clear, type prefix, type
    # "@", click category, click item, type suffix, Save & Run, reload to
    # verify) was verified to persist correctly with no duplication.
    # ------------------------------------------------------------------
    def set_instructions_with_variable_chip(self, prefix: str, var_name: str, suffix: str = "") -> None:
        editor = self.page.locator(SELECTORS["instructions_editor"])
        editor.click()
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Delete")
        self.page.wait_for_timeout(300)

        if prefix:
            self.page.keyboard.type(prefix)
            self.page.wait_for_timeout(300)

        self.page.keyboard.type("@")
        self.page.wait_for_timeout(1_200)

        self.page.locator(".styles_categoryName__wP5TP", has_text="Custom Variables").first.click()
        self.page.wait_for_timeout(800)

        item = self.page.get_by_text(var_name, exact=True)
        if not item.count():
            raise RuntimeError(f"Custom Variable '{var_name}' not found in the @-picker's Custom Variables category")
        item.first.click()
        self.page.wait_for_timeout(800)

        if suffix:
            self.page.keyboard.type(suffix)
            self.page.wait_for_timeout(300)

        chip_present = editor.evaluate(
            "(el, name) => !!el.querySelector(`[data-mention-token*=\"${name}\"]`)", var_name
        )
        if not chip_present:
            raise RuntimeError(
                f"No real mention-token chip for '{var_name}' found in the editor after the @-picker sequence "
                "— it may have been inserted as plain text instead of a real reference."
            )

        self.page.get_by_text("Save & Run", exact=True).click()
        self.page.wait_for_timeout(4_000)
