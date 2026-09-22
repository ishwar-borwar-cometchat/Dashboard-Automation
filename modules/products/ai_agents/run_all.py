#!/usr/bin/env python3
"""Runs the whole AI Agents suite so that it ENDS with one new agent left on the app.

    python3 modules/products/ai_agents/run_all.py --app-id <id> [--delete-agent] [--only list,builder,variables,kb]

Order
    1. Agent list check:  Add Agent -> Delete Agent -> Add New Agent -> Edit Agent.
       Every agent is named "Knowledge Assistant <random 4 digits>". The check prints RUN_AGENT=<name>:
       the new agent that is left after the edit.
    2. Instructions + Knowledge Base list, Variables, and Knowledge Base retrieval all run ON THAT AGENT
       (they read it from CC_RUN_AGENT and never create or delete their own).
    3. The agent is KEPT at the end (retrieval leaves every Knowledge Base source attached and a normal
       assistant prompt in Instructions). Pass --delete-agent to remove it instead.

Prints one "=== <check> ===" section per check with "[OK]" / "[ERROR]" and the check's own summary line,
so tools/live_progress.py can follow it, and ends with "exit=<code>".
Needs only the saved Dashboard login (auth/storage_state.json). Nothing here is specific to one app.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import random
import re
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402
from modules.products.ai_agents.ai_agents_page import AIAgentsPage  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(REPO_ROOT / "auth" / "storage_state.json"))
BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")

# key, label shown on the dashboard, script, runs on the shared agent?
CHECKS = [
    ("list", "Agent list — add, delete, add new, edit", "verify_ai_agents.py", False),
    ("builder", "Instructions + Knowledge Base list", "verify_ai_agent_builder.py", True),
    ("variables", "Variables — create, use in instructions, substitution", "verify_variable_substitution.py", True),
    ("kb", "Knowledge Base retrieval", "verify_kb_retrieval.py", True),
]


def _agents_page(pw, app_id: str):
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    agents = AIAgentsPage(page, app_id, BASE_URL)
    agents.open(force=True)
    if "/login" in page.url:
        browser.close()
        raise SystemExit("The saved Dashboard login has expired. Run: python3 utils/bootstrap_auth.py --app-id " + app_id)
    return browser, agents


def _create_agent(pw, app_id: str) -> str:
    """Used only when the shared checks run without the list check: make one new 'Knowledge Assistant <random>'."""
    browser, agents = _agents_page(pw, app_id)
    existing = agents.agent_names()
    while True:
        name = f"Knowledge Assistant {random.randint(1000, 9999)}"
        if not any(name in n or n in name for n in existing if n != "Knowledge Assistant"):
            break
    agents.add_agent(name, description="Knowledge Assistant created by the automated run.")
    ok = agents.exists(name)
    browser.close()
    if not ok:
        raise SystemExit(f"Could not create the run agent {name!r}")
    return name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-id", default=os.environ.get("CC_APP_ID", "168258051159eab49"))
    ap.add_argument("--delete-agent", action="store_true", help="delete the run agent at the end (default: keep it)")
    ap.add_argument("--only", help="comma-separated: list,builder,variables,kb (default: all)")
    a = ap.parse_args()
    wanted = [k.strip() for k in a.only.split(",")] if a.only else [c[0] for c in CHECKS]
    checks = [c for c in CHECKS if c[0] in wanted]

    log_dir = REPO_ROOT / "reports" / "ai_agents_run" / time.strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)

    run_agent = os.environ.get("CC_RUN_AGENT", "")
    failures = 0

    with sync_playwright() as pw:
        for key, label, script, shared in checks:
            if shared and not run_agent:
                run_agent = _create_agent(pw, a.app_id)
                print(f"[setup] created a new agent for this run: {run_agent}", flush=True)
            print(f"=== {label} ===", flush=True)
            env = dict(os.environ, CC_APP_ID=a.app_id, PYTHONUNBUFFERED="1")
            env.pop("CC_AGENT_NAME", None)
            if shared:
                env["CC_RUN_AGENT"] = run_agent
                if not a.delete_agent:
                    env["CC_KEEP_AGENT"] = "1"          # final state: sources attached, normal assistant prompt
                else:
                    env.pop("CC_KEEP_AGENT", None)
            log = log_dir / f"{key}.log"
            with open(log, "w") as fh:
                rc = subprocess.run([sys.executable, str(HERE / script)], stdout=fh, stderr=subprocess.STDOUT,
                                    cwd=str(REPO_ROOT), env=env).returncode
            text = log.read_text()
            if key == "list":
                m = re.search(r"^RUN_AGENT=(.+)$", text, re.M)
                if m:
                    run_agent = m.group(1).strip()
                    print(f"[setup] the list check left this new agent: {run_agent}", flush=True)
            summary = next((l.strip() for l in reversed(text.splitlines()) if re.search(r"\d+/\d+", l)), "")
            m = re.search(r"(\d+)/(\d+)", summary)
            partial = bool(m) and int(m.group(1)) < int(m.group(2))
            if rc == 0 and partial:
                failures += 1
                print(f"  [MISMATCH] not every check passed — {summary} (see {log.name})", flush=True)
            elif rc == 0:
                print(f"  [OK] {summary}", flush=True)
            else:
                failures += 1
                print(f"  [ERROR] exited with code {rc} — see {log.name}. {summary}", flush=True)
            if key == "list" and not run_agent and any(c[3] for c in checks):
                print("  [ERROR] the list check did not leave a new agent, so the remaining checks cannot run", flush=True)
                break

        if run_agent and any(c[3] for c in checks):
            try:
                browser, agents = _agents_page(pw, a.app_id)
                if a.delete_agent:
                    agents.delete_agent(run_agent)
                    print(f"[cleanup] deleted the run agent {run_agent}: {not agents.exists(run_agent)}", flush=True)
                else:
                    print(f"[kept] the new agent is left on the app: {run_agent} (present: {agents.exists(run_agent)})", flush=True)
                browser.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[cleanup FAILED] could not check/delete {run_agent!r}: {exc}", flush=True)
    print(f"RUN_AGENT_FINAL={run_agent}", flush=True)
    print(f"logs: {log_dir}", flush=True)
    print(f"exit={1 if failures else 0}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
