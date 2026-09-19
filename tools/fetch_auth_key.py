#!/usr/bin/env python3
"""Reads an app's Auth Key from its Dashboard Overview -> Credentials card into a private file.

    python3 tools/fetch_auth_key.py --app-id <id> [--out /tmp/_ak]

Uses the saved Dashboard login (auth/storage_state.json). The key is written to --out with
mode 600 and never printed. Delete the file when the job is finished.
"""
import argparse, os, re
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--app-id", required=True)
ap.add_argument("--out", default="/tmp/_ak")
ap.add_argument("--base-url", default=os.environ.get("CC_BASE_URL", "https://app.cometchat.com"))
ap.add_argument("--state", default="auth/storage_state.json")
a = ap.parse_args()
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_context(storage_state=a.state, viewport={"width": 1440, "height": 900}).new_page()
    pg.goto(f"{a.base_url}/app/{a.app_id}/overview", wait_until="domcontentloaded")
    lab = pg.get_by_text(re.compile(r"^\s*Auth Key\s*$", re.I)).first
    lab.wait_for(timeout=30_000)
    pg.wait_for_timeout(2500)
    row = lab.locator("xpath=ancestor::*[.//*[contains(@class,'anticon') or self::button or self::svg]][1]")
    icons = row.locator("[class*=anticon], button, svg")
    key = None
    for i in range(icons.count()):
        try:
            icons.nth(i).click(timeout=2000)
        except Exception:
            continue
        pg.wait_for_timeout(700)
        m = re.findall(r"\b[0-9a-f]{40}\b", row.inner_text())
        if m:
            key = m[0]
            break
    b.close()
if not key:
    raise SystemExit("Could not read the Auth Key (session expired, or the page changed).")
with open(a.out, "w") as f:
    f.write(key)
os.chmod(a.out, 0o600)
print("Auth Key saved to", a.out)
