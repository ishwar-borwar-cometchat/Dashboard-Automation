"""One-time interactive auth capture for the CometChat Dashboard E2E suite.

Opens a real Chrome window, waits for you to log in by hand, then saves the full
session (cookies + localStorage, including the Bearer JWT the dashboard stores)
to auth/storage_state.json.

    python utils/bootstrap_auth.py

Re-run it whenever the saved session expires (the dashboard JWT lasts ~7 days).
No credentials are ever typed by the script or written anywhere except the
storage-state file.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "auth" / "storage_state.json"

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--app-id", default=APP_ID)
    args = ap.parse_args()

    target = f"{args.base_url}/app/{args.app_id}/overview" if args.app_id else args.base_url

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("CometChat Dashboard — auth capture")
    print("=" * 70)
    print("A Chrome window will open. Log in as you normally would.")
    print("When you can see the Overview page, come back here and press Enter.")
    print("=" * 70)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport=None)
        page = context.new_page()
        page.goto(target, wait_until="domcontentloaded", timeout=120_000)

        try:
            input("\n>>> Logged in and on the dashboard? Press Enter to save... ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            browser.close()
            return 1

        url = page.url
        if "login" in url.lower() or "signin" in url.lower():
            print(f"\n!! Still on a login page ({url}). Not saving — log in first, then re-run.")
            browser.close()
            return 2

        context.storage_state(path=str(out))
        browser.close()

    state = json.loads(out.read_text())
    n_cookies = len(state.get("cookies", []))
    n_ls = sum(len(o.get("localStorage", [])) for o in state.get("origins", []))

    print(f"\nSaved {out}")
    print(f"  cookies: {n_cookies}")
    print(f"  localStorage keys: {n_ls}")

    if n_cookies == 0 and n_ls == 0:
        print("\n!! Captured an empty session — the tests will fail to authenticate.")
        return 3

    # Surface which key holds the bearer token, useful for debugging.
    for origin in state.get("origins", []):
        for item in origin.get("localStorage", []):
            if "eyJ" in str(item.get("value", ""))[:64]:
                print(f"  JWT found under localStorage key: {item['name']!r}")

    print("\nNext:  ./run_tests.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
