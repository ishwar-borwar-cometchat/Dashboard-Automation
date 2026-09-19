#!/usr/bin/env python3
"""Deletes leftover automated-test users and roles from an app (only those whose ID starts with e2e_).

    python3 tools/cleanup_e2e.py --app-id <id> [--dry-run]

Use it after a run that crashed or lost its network during cleanup. Never touches anything else.
"""
import argparse, os, re
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--app-id", required=True)
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--prefix", default="e2e_")
ap.add_argument("--base-url", default=os.environ.get("CC_BASE_URL", "https://app.cometchat.com"))
ap.add_argument("--state", default="auth/storage_state.json")
a = ap.parse_args()

def confirm(pg):
    dlg = pg.locator(".ant-modal:visible, .ant-popconfirm:visible, [role=dialog]:visible").first
    dlg.wait_for(timeout=8000)
    btn = dlg.get_by_role("button", name=re.compile(r"^(delete|ok|yes|confirm|remove)$", re.I))
    (btn.first if btn.count() else dlg.locator("button").last).click()
    pg.wait_for_timeout(1800)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_context(storage_state=a.state, viewport={"width": 1440, "height": 1000}).new_page()
    base = f"{a.base_url}/app/{a.app_id}"
    # users first (roles cannot be removed while users still hold them)
    for _ in range(40):
        pg.goto(f"{base}/users", wait_until="domcontentloaded")
        pg.locator(".ant-table-tbody tr.ant-table-row").first.wait_for(timeout=30000)
        pg.wait_for_timeout(800)
        rows = pg.locator(".ant-table-tbody tr.ant-table-row")
        target = None
        for i in range(rows.count()):
            uid = (rows.nth(i).get_attribute("data-row-key") or "")
            if uid.startswith(a.prefix):
                target = (i, uid); break
        if not target:
            break
        print("user left over:", target[1])
        if a.dry_run:
            break
        rows.nth(target[0]).locator("td:last-child button").nth(2).click()
        confirm(pg)
        print("  deleted user", target[1])
    for _ in range(20):
        pg.goto(f"{base}/roles", wait_until="domcontentloaded")
        pg.locator("tr.ant-table-row").first.wait_for(timeout=30000)
        pg.wait_for_timeout(600)
        rows = pg.locator("tr.ant-table-row")
        target = None
        for i in range(rows.count()):
            rid = rows.nth(i).get_attribute("data-row-key") or ""
            if rid.startswith(a.prefix):
                target = rid; break
        if not target:
            break
        print("role left over:", target)
        if a.dry_run:
            break
        pg.locator(f'tr.ant-table-row[data-row-key="{target}"] button[aria-label^="Delete"]').first.click()
        confirm(pg)
        print("  deleted role", target)
    print("done — nothing else left with prefix", a.prefix)
    b.close()
