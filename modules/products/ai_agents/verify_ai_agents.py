#!/usr/bin/env python3
"""Verification for PRODUCTS > AI Agents — the list-page surface only
(`AIAgentsPage`: list/add/edit/delete). The Agent Builder IDE itself
(Instructions, Knowledge Base, Tools, Deploy, Logs — a much bigger, separate
app opened by "Manage Agent") has no page object yet and is NOT covered
here; see modules/products/ai_agents/README.md.

Real write-then-verify for each list-page action, same standard as the
Extensions scripts: never mark PASS from an assumed outcome — read the
actual list back after each action. A uniquely-timestamped test agent name
is used throughout so this can run repeatedly without colliding with a
leftover from a previous run, and pre-existing agents are confirmed
untouched at both baseline and the end.

Usage
-----
    python3 "modules/products/ai_agents/verify_ai_agents.py"
    CC_HEADLESS=0 python3 "modules/products/ai_agents/verify_ai_agents.py"

Requires auth/storage_state.json for the Dashboard (see README:
python3 utils/bootstrap_auth.py) — same session used by the Chat &
Messaging extension scripts, not a Sample App SDK login.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from modules.products.ai_agents.ai_agents_page import AIAgentsPage  # noqa: E402

ROOT = REPO_ROOT
REPORTS = ROOT / "reports" / "ai_agents_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "168258051159eab49")  # same Sample App as Extensions, per module README
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"


def run(screenshot_dir: pathlib.Path) -> dict:
    results: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        ai = AIAgentsPage(page, APP_ID, BASE_URL)

        # -----------------------------------------------------------
        # Auth freshness check — a stale storage_state silently redirects
        # to /login instead of erroring; catch that here rather than
        # mis-reading an empty/login page as "zero agents".
        # -----------------------------------------------------------
        ai.open(force=True)
        if "/login" in page.url:
            raise RuntimeError(
                f"Redirected to {page.url} — auth/storage_state.json is stale. "
                "Run `python3 utils/bootstrap_auth.py` to refresh it (interactive, user-driven)."
            )

        baseline = ai.agent_names()
        page.screenshot(path=str(screenshot_dir / "00_baseline.png"))
        print("Baseline agents:", baseline)
        results["baseline"] = {"agents": baseline, "count": len(baseline)}

        # Flag (don't silently delete) any stray test agent left over from
        # an earlier interrupted run — the README notes this has happened
        # before ("QA Automation Test Agent added by this module's
        # add_agent()"). A fresh timestamped name below avoids colliding
        # with it either way.
        stray = [n for n in baseline if n.lower().startswith("qa automation test agent")]
        results["stray_test_agents_found_at_baseline"] = stray
        if stray:
            print(f"NOTE: {len(stray)} stray test agent(s) already on the list: {stray} "
                  f"(left over from a previous run — not touched by this script)")

        test_name = f"QA Automation Test Agent {int(time.time())}"
        test_desc = "Created by verify_ai_agents.py — safe to delete."

        # -----------------------------------------------------------
        # Add
        # -----------------------------------------------------------
        add_ok = None
        add_error = None
        try:
            ai.add_agent(test_name, description=test_desc)
            add_ok = ai.exists(test_name)
        except Exception as e:
            add_error = str(e)
        page.screenshot(path=str(screenshot_dir / "01_after_add.png"))
        results["add_agent"] = {
            "target_name": test_name,
            "ok": bool(add_ok) and add_error is None,
            "error": add_error,
            "list_after": ai.agent_names(),
        }
        print("Add agent:", results["add_agent"]["ok"], "| list now:", results["add_agent"]["list_after"])

        # -----------------------------------------------------------
        # Edit (only if add succeeded — nothing to edit otherwise)
        # -----------------------------------------------------------
        edited_name = f"{test_name} (edited)"
        if results["add_agent"]["ok"]:
            edit_ok = None
            edit_error = None
            try:
                ai.edit_agent(test_name, new_name=edited_name, description=test_desc + " Edited.")
                edit_ok = ai.exists(edited_name) and not ai.exists(test_name)
            except Exception as e:
                edit_error = str(e)
            page.screenshot(path=str(screenshot_dir / "02_after_edit.png"))
            results["edit_agent"] = {
                "from": test_name, "to": edited_name,
                "ok": bool(edit_ok) and edit_error is None,
                "error": edit_error,
                "list_after": ai.agent_names(),
            }
            print("Edit agent:", results["edit_agent"]["ok"], "| list now:", results["edit_agent"]["list_after"])
        else:
            results["edit_agent"] = {"ok": False, "error": "skipped — add_agent did not succeed", "list_after": ai.agent_names()}
            edited_name = test_name  # nothing was renamed; delete the original below

        # -----------------------------------------------------------
        # Delete (clean up regardless of edit outcome — try both possible names)
        # -----------------------------------------------------------
        delete_target = edited_name if ai.exists(edited_name) else (test_name if ai.exists(test_name) else None)
        if delete_target:
            delete_ok = None
            delete_error = None
            try:
                ai.delete_agent(delete_target)
                delete_ok = not ai.exists(delete_target)
            except Exception as e:
                delete_error = str(e)
            page.screenshot(path=str(screenshot_dir / "03_after_delete.png"))
            results["delete_agent"] = {
                "target": delete_target,
                "ok": bool(delete_ok) and delete_error is None,
                "error": delete_error,
                "list_after": ai.agent_names(),
            }
            print("Delete agent:", results["delete_agent"]["ok"], "| list now:", results["delete_agent"]["list_after"])
        else:
            results["delete_agent"] = {"ok": False, "error": "nothing to delete — neither test name found on list", "list_after": ai.agent_names()}

        # -----------------------------------------------------------
        # Isolation check: every pre-existing agent from baseline (minus
        # any already-flagged stray) is still present at the end.
        # -----------------------------------------------------------
        final = ai.agent_names()
        expected_untouched = [n for n in baseline if n not in stray]
        missing = [n for n in expected_untouched if n not in final]
        results["isolation_check"] = {
            "expected_untouched": expected_untouched,
            "final_list": final,
            "missing": missing,
            "ok": len(missing) == 0,
        }
        print("Isolation check (pre-existing agents untouched):", results["isolation_check"]["ok"])
        if missing:
            print("  MISSING (were on baseline, not on final list):", missing)

        ctx.close()
        browser.close()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    results = run(screenshot_dir)
    elapsed = time.time() - t0

    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "elapsed_s": round(elapsed, 1), "app_id": APP_ID}, f, indent=2, default=str)

    checks = ["add_agent", "edit_agent", "delete_agent", "isolation_check"]
    passed = sum(1 for c in checks if results.get(c, {}).get("ok"))
    print(f"\n{'=' * 50}")
    print(f"AI Agents (list page): {passed}/{len(checks)} checks passed in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
