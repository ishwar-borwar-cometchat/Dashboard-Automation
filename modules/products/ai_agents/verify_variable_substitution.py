#!/usr/bin/env python3
"""Verification for Custom Variable RUNTIME SUBSTITUTION — the actual
"reference a variable in Instructions, ask the agent, get the real value
back" flow, as opposed to verify_ai_agent_builder.py's read-only structure
checks.

This is the flow whose first automated attempt (2026-09-18) produced a
false-positive "bug" report, later retracted after the user manually
reproduced correct substitution by hand and a careful re-test traced the
failure to the script's own too-fast editor interaction, not the product.
See ai_agent_builder_page.py's docstrings for that history.

Full sequence, on a disposable test agent:
  1. Create a real Custom Variable (Constant type) with a distinctive value.
  2. Build an Instructions prompt that references it via a REAL @-picker
     chip (not typed placeholder text) — see
     AIAgentBuilderPage.set_instructions_with_variable_chip().
  3. Save & Run, then reload the Instructions page fresh and read back the
     saved instructions from the DOM (not just trust the save click) to
     confirm real persistence before judging anything.
  4. Ask the live chat preview a question that should surface the
     variable's value, and check the actual reply text for the REAL value
     — not the literal "@var-custom:<name>" placeholder string, which
     would mean substitution silently failed.
  5. Clean up: delete the variable (shared resource), delete the agent.

Usage
-----
    python3 "modules/products/ai_agents/verify_variable_substitution.py"
    CC_HEADLESS=0 python3 "modules/products/ai_agents/verify_variable_substitution.py"

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
REPORTS = ROOT / "reports" / "variable_substitution_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "168258051159eab49")
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"

VAR_NAME = "supportEmail"
VAR_VALUE = "support@cometchat.com"
VAR_DESCRIPTION = "Created by verify_variable_substitution.py — safe to delete."

INSTRUCTION_PREFIX = (
    "You are a support agent. If asked for the support email address, "
    "respond with exactly this value and nothing else: "
)
INSTRUCTION_SUFFIX = ""
QUESTION = "What is the support email address?"

PLACEHOLDER_LITERAL = f"@var-custom:{VAR_NAME}"

INTERIM_STATE_TEXTS = {"thinking…", "retrieving relevant information from available sources…"}


def wait_for_stable_reply(page, max_seconds: float = 45.0, interval: float = 0.5, stable_reads: int = 4) -> list[str]:
    """Poll message bubbles until the last one stops changing for
    `stable_reads` consecutive polls AND isn't still one of the known
    interim/loading strings (e.g. "Thinking…") — a fixed-duration or
    naive stability check can mistake a still-generating state for the
    final answer. Same approach as verify_kb_retrieval.py's version.
    """
    bubbles = page.locator("[class*='cometchat-message-bubble']")
    samples: list[str] = []
    same_count = 0
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            texts = [bubbles.nth(i).inner_text().strip() for i in range(bubbles.count())]
            texts = [t for t in texts if t]
        except Exception:
            texts = []
        last = texts[-1] if texts else ""
        if texts and (not samples or samples[-1] != last):
            samples.append(last)
            same_count = 0
        elif texts:
            same_count += 1
            if same_count >= stable_reads and last.strip().lower() not in INTERIM_STATE_TEXTS:
                break
        time.sleep(interval)
    return samples


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

        test_name = f"QA Variable Substitution Test {int(time.time())}"
        agents.add_agent(test_name, description="Created by verify_variable_substitution.py — safe to delete.")
        if not agents.exists(test_name):
            raise RuntimeError(f"Setup failed: '{test_name}' not on the list after add_agent()")

        new_page = agents.manage_agent(test_name)
        agent_id = new_page.url.rstrip("/").split("/ai-agents/")[1].split("/")[0]
        builder = AIAgentBuilderPage(new_page, APP_ID, BASE_URL, agent_id)

        try:
            # ---------------------------------------------------------
            # 1. Create the Custom Variable
            # ---------------------------------------------------------
            builder.open_variables(force=True)
            builder.open_custom_variables_tab()
            builder.add_custom_variable_constant(VAR_NAME, VAR_VALUE, VAR_DESCRIPTION)
            var_created = VAR_NAME in builder.custom_variable_names()
            new_page.screenshot(path=str(screenshot_dir / "01_variable_created.png"), full_page=True)
            results["variable_created"] = {"ok": var_created, "name": VAR_NAME, "value": VAR_VALUE}
            print("Variable created:", var_created)

            # ---------------------------------------------------------
            # 2. Reference it via a real @-picker chip in Instructions
            # ---------------------------------------------------------
            builder.open_instructions(force=True)
            chip_error = None
            try:
                builder.set_instructions_with_variable_chip(INSTRUCTION_PREFIX, VAR_NAME, INSTRUCTION_SUFFIX)
            except Exception as e:
                chip_error = str(e)
            new_page.screenshot(path=str(screenshot_dir / "02_chip_inserted_and_saved.png"), full_page=True)
            results["chip_inserted"] = {"ok": chip_error is None, "error": chip_error}
            print("Chip inserted + Save & Run:", results["chip_inserted"]["ok"], chip_error or "")

            # ---------------------------------------------------------
            # 3. Fresh reload -> confirm REAL persistence (not just DOM state)
            # ---------------------------------------------------------
            builder.open_instructions(force=True)
            new_page.wait_for_timeout(1_500)
            saved_text = builder.get_instructions()
            persisted_ok = PLACEHOLDER_LITERAL in saved_text and INSTRUCTION_PREFIX.strip() in saved_text
            new_page.screenshot(path=str(screenshot_dir / "03_after_reload.png"), full_page=True)
            results["persisted_after_reload"] = {"ok": persisted_ok, "saved_text": saved_text}
            print("Persisted after fresh reload:", persisted_ok, "| saved:", repr(saved_text))

            # ---------------------------------------------------------
            # 4. Ask the live preview and check the REAL reply
            # ---------------------------------------------------------
            reply_text = None
            reply_error = None
            try:
                composer = new_page.locator("[data-placeholder='Ask anything']")
                composer.wait_for(state="visible", timeout=20_000)
                composer.click()
                new_page.keyboard.type(QUESTION)
                new_page.screenshot(path=str(screenshot_dir / "04_question_asked.png"), full_page=True)
                new_page.keyboard.press("Enter")

                samples = wait_for_stable_reply(new_page)
                reply_text = samples[-1] if samples else ""
                results.setdefault("_observed_states", samples)
            except Exception as e:
                reply_error = str(e)
            new_page.screenshot(path=str(screenshot_dir / "05_response.png"), full_page=True)

            real_value_present = bool(reply_text) and VAR_VALUE in reply_text
            placeholder_leaked = bool(reply_text) and PLACEHOLDER_LITERAL in reply_text
            results["runtime_substitution"] = {
                "ok": real_value_present and not placeholder_leaked and reply_error is None,
                "question": QUESTION,
                "reply_text": reply_text,
                "expected_value": VAR_VALUE,
                "real_value_present": real_value_present,
                "placeholder_leaked": placeholder_leaked,
                "error": reply_error,
            }
            print("Runtime substitution worked:", results["runtime_substitution"]["ok"], "| reply:", reply_text)
            if placeholder_leaked:
                print("FLAGGED: reply contains the literal placeholder text — substitution did not happen.")

            # ---------------------------------------------------------
            # 4.5. Back on the Variables tab: the usage badge should have
            # flipped from "Not Used" (screenshot 01) to "Used" now that
            # the variable has actually been referenced in a saved,
            # running instruction.
            # ---------------------------------------------------------
            builder.open_variables(force=True)
            builder.open_custom_variables_tab()
            usage_status = builder.custom_variable_usage_status(VAR_NAME)
            new_page.screenshot(path=str(screenshot_dir / "06_usage_status.png"), full_page=True)
            results["usage_status_after_reference"] = {
                "ok": usage_status.strip().lower() == "in use",
                "status_text": usage_status,
            }
            print("Usage status after being referenced:", usage_status)

        finally:
            # ---------------------------------------------------------
            # 5. Cleanup — delete the variable (shared) then the agent
            # ---------------------------------------------------------
            cleanup_error = None
            try:
                builder.open_variables(force=True)
                builder.open_custom_variables_tab()
                builder.delete_custom_variable(VAR_NAME)
                var_gone = VAR_NAME not in builder.custom_variable_names()
            except Exception as e:
                cleanup_error = str(e)
                var_gone = False
            new_page.close()
            agents.open(force=True)
            agents.delete_agent(test_name)
            agent_gone = not agents.exists(test_name)
            results["cleanup"] = {"ok": var_gone and agent_gone, "variable_deleted": var_gone, "agent_deleted": agent_gone, "error": cleanup_error}
            print("Cleanup (variable + agent deleted):", results["cleanup"]["ok"])

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

    checks = ["variable_created", "chip_inserted", "persisted_after_reload", "runtime_substitution", "usage_status_after_reference", "cleanup"]
    passed = sum(1 for c in checks if results.get(c, {}).get("ok"))
    print(f"\n{'=' * 50}")
    print(f"Variable Substitution: {passed}/{len(checks)} checks passed in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
