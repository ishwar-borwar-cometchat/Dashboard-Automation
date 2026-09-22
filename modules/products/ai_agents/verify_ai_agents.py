#!/usr/bin/env python3
"""Verification for PRODUCTS > AI Agents — the list-page surface only
(`AIAgentsPage`: list/add/edit/delete). The Agent Builder IDE itself
(Instructions, Knowledge Base, Tools, Deploy, Logs — a much bigger, separate
app opened by "Manage Agent") has no page object yet and is NOT covered
here; see modules/products/ai_agents/README.md.

Order of the checks: Add Agent -> Delete Agent -> Add New Agent -> Edit Agent, so the run ends with one new
"Knowledge Assistant <random>" agent left on the app (printed as RUN_AGENT=<name>).

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
import random
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

        # The four actions run in this order, so the run ENDS with one new agent left on the app:
        #   Add Agent -> Delete Agent -> Add New Agent -> Edit Agent
        # Every name is "Knowledge Assistant <random 4 digits>", never one that is already on the list.
        taken = set(baseline)

        def new_name() -> str:
            while True:
                n = f"Knowledge Assistant {random.randint(1000, 9999)}"
                if n not in taken and not any(n in t or t in n for t in taken if t != "Knowledge Assistant"):
                    taken.add(n)
                    return n

        first_name = new_name()
        second_name = new_name()
        edited_name = new_name()
        first_desc = "Created by verify_ai_agents.py — a throw-away agent, deleted right after."
        second_desc = "Knowledge Assistant created by the automated run."

        def step(key: str, shot: str, action, ok_check, **extra) -> bool:
            error = None
            ok = None
            try:
                action()
                ok = ok_check()
            except Exception as e:  # noqa: BLE001
                error = str(e)
            page.screenshot(path=str(screenshot_dir / shot))
            results[key] = {**extra, "ok": bool(ok) and error is None, "error": error, "list_after": ai.agent_names()}
            print(f"{key}:", results[key]["ok"], "| list now:", results[key]["list_after"])
            return results[key]["ok"]

        # 1. Add Agent
        added = step("add_agent", "01_after_add.png",
                     lambda: ai.add_agent(first_name, description=first_desc),
                     lambda: ai.exists(first_name), target_name=first_name)

        # 2. Delete Agent (the one just added)
        if added or ai.exists(first_name):
            step("delete_agent", "02_after_delete.png",
                 lambda: ai.delete_agent(first_name),
                 lambda: not ai.exists(first_name), target=first_name)
        else:
            results["delete_agent"] = {"ok": False, "error": "skipped — add_agent did not succeed", "list_after": ai.agent_names()}

        # 3. Add New Agent (this is the agent that is kept)
        added2 = step("add_new_agent", "03_after_add_new.png",
                      lambda: ai.add_agent(second_name, description=second_desc),
                      lambda: ai.exists(second_name), target_name=second_name)

        # 4. Edit Agent (edit the new one: new name + description; it is still a "Knowledge Assistant …")
        final_name = second_name
        if added2:
            if step("edit_agent", "04_after_edit.png",
                    lambda: ai.edit_agent(second_name, new_name=edited_name, description=second_desc + " Edited."),
                    lambda: ai.exists(edited_name) and not ai.exists(second_name),
                    **{"from": second_name, "to": edited_name}):
                final_name = edited_name
            elif ai.exists(edited_name):
                final_name = edited_name
        else:
            results["edit_agent"] = {"ok": False, "error": "skipped — add_new_agent did not succeed", "list_after": ai.agent_names()}
        results["run_agent"] = {"name": final_name if ai.exists(final_name) else None}
        print(f"RUN_AGENT={final_name if ai.exists(final_name) else ''}")

        # -----------------------------------------------------------
        # Isolation check: every pre-existing agent from baseline (minus
        # any already-flagged stray) is still present at the end, and the
        # only new agent left is the one this run created.
        # -----------------------------------------------------------
        final = ai.agent_names()
        expected_untouched = [n for n in baseline if n not in stray]
        missing = [n for n in expected_untouched if n not in final]
        extra_agents = [n for n in final if n not in baseline]
        results["isolation_check"] = {
            "expected_untouched": expected_untouched,
            "final_list": final,
            "missing": missing,
            "new_agents_left": extra_agents,
            "ok": len(missing) == 0 and extra_agents == ([final_name] if ai.exists(final_name) else []),
        }
        print("Safety check (pre-existing agents untouched, one new agent left):", results["isolation_check"]["ok"])
        if not results["isolation_check"]["ok"]:
            print("WARNING: the agent list is not what this run should leave behind — see isolation_check in the JSON.")
        if missing:
            print("  MISSING (were on baseline, not on final list):", missing)
        page.screenshot(path=str(screenshot_dir / "05_final_list.png"))

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

    checks = ["add_agent", "delete_agent", "add_new_agent", "edit_agent"]   # the edit leaves the final state; isolation is only a safety warning
    passed = sum(1 for c in checks if results.get(c, {}).get("ok"))
    print(f"\n{'=' * 50}")
    print(f"AI Agents (list page): {passed}/{len(checks)} checks passed in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
