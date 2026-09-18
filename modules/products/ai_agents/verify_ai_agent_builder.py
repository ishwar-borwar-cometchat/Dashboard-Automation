#!/usr/bin/env python3
"""Verification for the AI Agents "Agent Builder" IDE (`AIAgentBuilderPage`):
Instructions and Knowledge Base only — see modules/products/ai_agents/
ai_agent_builder_page.py for why the rest of the builder (Tools, Card
Builder, Variables, MCP, Deploy, Logs) isn't covered here.

Instructions is a full write-then-verify: set a distinctive system prompt
on a disposable test agent, Save & Run, send a real message in the live
chat preview, and check the model's actual reply reflects the instruction
— not just that the save call succeeded.

Knowledge Base is read-only here: the source list is app-level shared
(confirmed live 2026-09-18 — the same sources show up regardless of which
agent's builder you're in), so this only verifies the list is readable and
that the test agent's own "Attach to Agent" switches start unchecked. It
does not attach/detach anything against the real shared sources — do not
mistake "not covered" here for "known broken"; see the page object's
docstring for what's needed before that becomes safe to automate (a
throwaway source via `add_source()`, not yet built).

Usage
-----
    python3 "modules/products/ai_agents/verify_ai_agent_builder.py"
    CC_HEADLESS=0 python3 "modules/products/ai_agents/verify_ai_agent_builder.py"

Requires auth/storage_state.json (see README: python3 utils/bootstrap_auth.py).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from modules.products.ai_agents.ai_agent_builder_page import AIAgentBuilderPage  # noqa: E402
from modules.products.ai_agents.ai_agents_page import AIAgentsPage  # noqa: E402

ROOT = REPO_ROOT
REPORTS = ROOT / "reports" / "ai_agent_builder_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "168258051159eab49")
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"

TEST_INSTRUCTION = "You are a QA probe agent. Always reply with the single word: PONG"
EXPECTED_REPLY = "PONG"
KNOWN_KB_SOURCES = ["https://www.cometchat.com/docs", "Complete_Manual-Testing.pdf", "test"]


def run(screenshot_dir: pathlib.Path) -> dict:
    results: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        agents = AIAgentsPage(page, APP_ID, BASE_URL)

        agents.open(force=True)
        if "/login" in page.url:
            raise RuntimeError(
                f"Redirected to {page.url} — auth/storage_state.json is stale. "
                "Run `python3 utils/bootstrap_auth.py` to refresh it."
            )

        test_name = f"QA Builder Test Agent {int(time.time())}"
        agents.add_agent(test_name, description="Created by verify_ai_agent_builder.py — safe to delete.")
        if not agents.exists(test_name):
            raise RuntimeError(f"Setup failed: '{test_name}' not on the list after add_agent()")

        new_page = agents.manage_agent(test_name)
        agent_id = new_page.url.rstrip("/").split("/ai-agents/")[1].split("/")[0]
        builder = AIAgentBuilderPage(new_page, APP_ID, BASE_URL, agent_id)

        try:
            # ---------------------------------------------------------
            # Instructions: set prompt -> save & run -> real chat round trip
            # ---------------------------------------------------------
            builder.open_instructions(force=True)
            new_page.screenshot(path=str(screenshot_dir / "00_instructions_blank.png"), full_page=True)

            set_ok = None
            set_error = None
            try:
                builder.set_instructions(TEST_INSTRUCTION)
                saved_text = builder.get_instructions()
                set_ok = TEST_INSTRUCTION in saved_text
            except Exception as e:
                set_error = str(e)
            new_page.screenshot(path=str(screenshot_dir / "01_instructions_saved.png"), full_page=True)
            results["set_instructions"] = {"ok": bool(set_ok) and set_error is None, "error": set_error}
            print("Set instructions:", results["set_instructions"]["ok"])

            reply_ok = None
            reply_text = None
            reply_error = None
            try:
                reply_text = builder.send_preview_message("ping")
                reply_ok = EXPECTED_REPLY in reply_text.upper()
            except Exception as e:
                reply_error = str(e)
            new_page.screenshot(path=str(screenshot_dir / "02_chat_reply.png"), full_page=True)
            results["live_preview_reply"] = {
                "ok": bool(reply_ok) and reply_error is None,
                "reply_text": reply_text,
                "expected_contains": EXPECTED_REPLY,
                "error": reply_error,
            }
            print("Live preview reply:", results["live_preview_reply"]["ok"], "| got:", reply_text)

            # ---------------------------------------------------------
            # Knowledge Base: read-only inventory + per-agent switch baseline
            # ---------------------------------------------------------
            builder.open_knowledge_base(force=True)
            new_page.screenshot(path=str(screenshot_dir / "03_knowledge_base.png"), full_page=True)

            kb_names = builder.kb_source_names()
            kb_list_ok = all(name in kb_names for name in KNOWN_KB_SOURCES)
            results["kb_source_list"] = {"ok": kb_list_ok, "names_found": kb_names, "expected_subset": KNOWN_KB_SOURCES}
            print("KB source list readable:", kb_list_ok, "| found:", kb_names)

            kb_baseline_unattached = all(not builder.kb_is_attached(name) for name in kb_names if name)
            results["kb_new_agent_starts_unattached"] = {"ok": kb_baseline_unattached}
            print("New agent starts with no KB sources attached:", kb_baseline_unattached)

        finally:
            new_page.close()
            agents.open(force=True)
            agents.delete_agent(test_name)
            results["cleanup"] = {"ok": not agents.exists(test_name)}
            print("Cleanup (test agent deleted):", results["cleanup"]["ok"])

        ctx.close()
        browser.close()

    return results


def main() -> None:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    results = run(screenshot_dir)
    elapsed = time.time() - t0

    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "elapsed_s": round(elapsed, 1), "app_id": APP_ID}, f, indent=2, default=str)

    checks = ["set_instructions", "live_preview_reply", "kb_source_list", "kb_new_agent_starts_unattached", "cleanup"]
    passed = sum(1 for c in checks if results.get(c, {}).get("ok"))
    print(f"\n{'=' * 50}")
    print(f"AI Agent Builder (Instructions + Knowledge Base): {passed}/{len(checks)} checks passed in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
