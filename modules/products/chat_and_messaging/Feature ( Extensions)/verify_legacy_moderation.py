#!/usr/bin/env python3
"""CometChat Dashboard <-> Sample App verification for the 5 extensions that
live only on Platform Features > Moderation > Moderation (Legacy):
Profanity Filter, Image Moderation, Sentiment Analysis, Virus & Malware
Scanner, and In-Flight Message Moderation.

These 5 can't use verify_extensions.py's generic OFF/ON toggle framework:
their row-level Status switch on the Legacy page must never be turned off
(the Dashboard team's own warning — doing so makes the extension disappear
from the Dashboard entirely, not just disable it). Isolating behavior here
instead means:

  1. Switching off the *new* Moderation engine's master toggle
     (Platform Features > Moderation > Settings), since it has its own
     same-named rules (Profanity Filter, AI Image Moderation, ...) that would
     otherwise confound which system actually blocked a message.
  2. For In-Flight Message Moderation specifically, using its own nested
     "All Messages" criterion inside its gear-icon Extension Settings panel
     (not its row Status switch) to isolate it from the other four — this
     criterion silently blocks *every* message when on, which otherwise
     makes Profanity Filter/Image Moderation/etc. look broken.

Both settings are restored to whatever state they were found in when the
script finishes, even on failure.

Lives at <repo root>/modules/products/chat_and_messaging/Feature ( Extensions)/verify_legacy_moderation.py
— run it from anywhere, it locates the repo root the same way
verify_extensions.py does.

Usage
-----
    python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_legacy_moderation.py"
    CC_HEADLESS=0 python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_legacy_moderation.py"

Requires
--------
    - auth/storage_state.json for the Dashboard (see README:
      python3 utils/bootstrap_auth.py)
    - the sample app's dependencies installed (npm install in
      CC_SAMPLE_APP_DIR)
    - the project's own test asset library for the flagged image and the
      EICAR test file (see project memory: Documents,Images,Videos,Audios/)

Config (env vars, same convention as verify_extensions.py)
------------------------------------------------------------
    CC_BASE_URL          Dashboard origin (default https://app.cometchat.com)
    CC_SAMPLE_APP_ID     App ID the Sample App connects to
    CC_STORAGE_STATE     Dashboard auth state (default auth/storage_state.json)
    CC_HEADLESS          "0" to watch it run (default "1")
    CC_TEST_ASSETS_DIR   Root of the moderation test asset library
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright, Page, Frame  # noqa: E402

import verify_extensions  # noqa: E402
from verify_extensions import (  # noqa: E402
    start_sample_app,
    stop_sample_app,
    open_conversation,
    open_attach_menu,
    BASE_URL,
    STORAGE_STATE,
    HEADLESS,
    SLOWMO,
)
# APP_ID is NOT imported by value above — it's read live via
# verify_extensions.APP_ID everywhere below instead. A plain `from ... import
# APP_ID` would snapshot the value at import time and go stale the moment
# verify_extensions.main()'s --app-id handling reassigns the real one.

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = REPO_ROOT
REPORTS = ROOT / "reports" / "legacy_moderation_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

TEST_ASSETS_DIR = pathlib.Path(os.environ.get(
    "CC_TEST_ASSETS_DIR",
    "/Users/admin/Documents/Claude/Dashboard/Documents,Images,Videos,Audios",
))
IMG_SAFE = str(TEST_ASSETS_DIR / "Images" / "file_example_JPG_2500kB.jpg")
IMG_FLAGGED = str(TEST_ASSETS_DIR / "Moderation Images" / "360_F_1752166918_0EWnCyjiExzhsh5nqQRtkZhClgXJDPzc.jpg")
EICAR_FILE = str(TEST_ASSETS_DIR / "Virus and Malware Files" / "eicar_com.zip")

# No hardcoded GUID here (2026-09-17 fix) — every call site below reads
# verify_extensions.CURRENT_GUID, resolved dynamically by open_conversation()
# from whatever CC_TARGET_CONVERSATION/--target-conversation names, so this
# script works against any app's seed data, not just one with a group
# literally named "cometchat-guid-1".

JS_FETCH = """
async (guid) => {
    const builder = new CometChat.MessagesRequestBuilder().setGUID(guid).setLimit(20).build();
    const messages = await builder.fetchPrevious();
    return messages.map(m => ({
        id: m.getId(), text: (m.getText && m.getText()) || null,
        type: m.getType ? m.getType() : null,
        metadata: m.getMetadata ? m.getMetadata() : null
    }));
}
"""

# guid is now passed as a real page.evaluate() argument (not baked in via
# Python string formatting at import time), so it always reflects the
# currently-resolved conversation, not whatever it was when this module
# first loaded.
JS_SEND_TEXT = """
async ([guid, text]) => {
    try {
        const msg = new CometChat.TextMessage(guid, text, "group");
        const sent = await CometChat.sendMessage(msg);
        return {ok: true, id: sent.getId(), text: sent.getText()};
    } catch (e) {
        return {ok: false, error: (e && (e.message || JSON.stringify(e))) || String(e)};
    }
}
"""


# ---------------------------------------------------------------------------
# Dashboard control — new Moderation engine master toggle
# ---------------------------------------------------------------------------
def get_new_engine_master_state(dash_page: Page) -> bool:
    dash_page.goto(f"{BASE_URL}/app/{verify_extensions.APP_ID}/moderation/rules", wait_until="networkidle", timeout=60_000)
    dash_page.wait_for_timeout(2500)
    master = dash_page.locator('[class*="ant-switch"]').first
    return master.evaluate('el => el.classList.contains("ant-switch-checked")')


def set_new_engine_master_state(dash_page: Page, enabled: bool) -> None:
    dash_page.goto(f"{BASE_URL}/app/{verify_extensions.APP_ID}/moderation/rules", wait_until="networkidle", timeout=60_000)
    dash_page.wait_for_timeout(2500)
    master = dash_page.locator('[class*="ant-switch"]').first
    if master.evaluate('el => el.classList.contains("ant-switch-checked")') != enabled:
        master.click()
        dash_page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Dashboard control — In-Flight Message Moderation's nested "All Messages"
# criterion (its own Extension Settings gear, NOT the row Status switch)
# ---------------------------------------------------------------------------
def _open_inflight_settings_frame(dash_page: Page) -> Frame:
    dash_page.goto(f"{BASE_URL}/app/{verify_extensions.APP_ID}/moderation/legacy", wait_until="domcontentloaded", timeout=60_000)
    dash_page.wait_for_timeout(2500)
    row = dash_page.locator("tr", has_text="In-flight Message Moderation")
    row.locator('a[role="button"]').first.click()
    dash_page.wait_for_timeout(6000)
    for f in dash_page.frames:
        if "human-moderation" in f.url:
            return f
    raise RuntimeError("In-flight Message Moderation settings frame did not load")


def get_inflight_all_messages_state(dash_page: Page) -> bool:
    frame = _open_inflight_settings_frame(dash_page)
    return frame.locator("#allMessages").is_checked()


def set_inflight_all_messages_state(dash_page: Page, enabled: bool) -> None:
    frame = _open_inflight_settings_frame(dash_page)
    checkbox = frame.locator("#allMessages")
    if checkbox.is_checked() != enabled:
        checkbox.evaluate("el => el.click()")
        dash_page.wait_for_timeout(500)
        frame.locator("#save").click()
        dash_page.wait_for_timeout(2500)


# ---------------------------------------------------------------------------
# Sample App checks — each returns a result dict, screenshots optional
# ---------------------------------------------------------------------------
def check_profanity_filter(page: Page, screenshot_dir: Optional[pathlib.Path]) -> dict:
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    composer.type("Clean control message, no bad words", delay=15)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)

    composer.click()
    composer.type("Blocked check aman word test", delay=15)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2500)

    if screenshot_dir is not None:
        page.screenshot(path=str(screenshot_dir / "profanity_filter.png"))

    clean_result = page.evaluate(JS_SEND_TEXT, [verify_extensions.CURRENT_GUID, "SDK re-check: clean message"])
    bad_result = page.evaluate(JS_SEND_TEXT, [verify_extensions.CURRENT_GUID, "SDK re-check: aman blocked test"])
    return {"clean_send": clean_result, "bad_word_send": bad_result}


def check_image_moderation(page: Page, screenshot_dir: Optional[pathlib.Path]) -> dict:
    if not open_attach_menu(page):
        return {"error": "attach menu did not open"}
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("Attach Image", exact=True).click()
    fc_info.value.set_files(IMG_SAFE)
    page.wait_for_timeout(4000)

    if not open_attach_menu(page):
        return {"error": "attach menu did not open on second attempt"}
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("Attach Image", exact=True).click()
    fc_info.value.set_files(IMG_FLAGGED)
    page.wait_for_timeout(4000)

    if screenshot_dir is not None:
        page.screenshot(path=str(screenshot_dir / "image_moderation.png"))

    msgs = page.evaluate(JS_FETCH, verify_extensions.CURRENT_GUID)
    image_msgs = [m for m in msgs if m.get("type") == "image"]
    return {"image_messages_delivered_in_last_20": len(image_msgs)}


def check_sentiment_analysis(page: Page, screenshot_dir: Optional[pathlib.Path]) -> dict:
    pos_marker = f"I absolutely love this hiking trip, best day ever! {int(time.time())}"
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    composer.type(pos_marker, delay=10)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)

    neg_result = page.evaluate(
        JS_SEND_TEXT, [verify_extensions.CURRENT_GUID, f"I hate this, this trip has been terrible and awful {int(time.time())}"]
    )

    if screenshot_dir is not None:
        page.screenshot(path=str(screenshot_dir / "sentiment_analysis.png"))

    msgs = page.evaluate(JS_FETCH, verify_extensions.CURRENT_GUID)
    pos_msg = next((m for m in msgs if m["text"] == pos_marker), None)
    sentiment = None
    if pos_msg and pos_msg.get("metadata"):
        sentiment = (
            pos_msg["metadata"]
            .get("@injected", {})
            .get("extensions", {})
            .get("sentiment-analysis")
        )
    return {"positive_message_sentiment": sentiment, "negative_message_send_result": neg_result}


def check_virus_scanner(page: Page, screenshot_dir: Optional[pathlib.Path]) -> dict:
    if not open_attach_menu(page):
        return {"error": "attach menu did not open"}
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("Attach File", exact=True).click()
    fc_info.value.set_files(EICAR_FILE)
    page.wait_for_timeout(5000)

    if screenshot_dir is not None:
        page.screenshot(path=str(screenshot_dir / "virus_scanner_send.png"))

    # the scan verdict lands moments later as an app_system edit, not on the
    # initial send — poll a few times before giving up.
    verdict = None
    for _ in range(6):
        msgs = page.evaluate(JS_FETCH, verify_extensions.CURRENT_GUID)
        eicar_msg = next((m for m in msgs if m.get("type") == "file"), None)
        if eicar_msg and eicar_msg.get("metadata"):
            scanner = (
                eicar_msg["metadata"]
                .get("@injected", {})
                .get("extensions", {})
                .get("virus-malware-scanner")
            )
            if scanner and scanner.get("scan_results"):
                verdict = scanner
                break
        page.wait_for_timeout(2000)
    return {"scan_verdict": verdict}


def check_inflight_moderation(
    dash_page: Page, page: Page, screenshot_dir: Optional[pathlib.Path]
) -> dict:
    marker = f"In-flight moderation test message {int(time.time())}"
    send_result = page.evaluate(JS_SEND_TEXT, [verify_extensions.CURRENT_GUID, marker])

    dash_page.goto(
        f"{BASE_URL}/app/{verify_extensions.APP_ID}/moderation/in-flight-moderation",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    # The page renders a brief loading spinner (neither "No Message Logs
    # Available" nor any row content) right after navigation — a short wait
    # can land inside that ambiguous frame and misread it as "has content".
    # 4s reliably clears it (proven across many manual checks); poll a
    # little past that as a safety margin rather than trusting a single read.
    dash_page.wait_for_timeout(4000)
    queue_has_entry = True
    for _ in range(4):
        queue_text = dash_page.locator("body").inner_text()
        if "No Message Logs Available" in queue_text:
            queue_has_entry = False
            break
        dash_page.wait_for_timeout(1000)

    if screenshot_dir is not None:
        dash_page.screenshot(path=str(screenshot_dir / "inflight_queue.png"), full_page=True)

    return {"send_result": send_result, "appeared_in_review_queue": queue_has_entry}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(screenshot_dir: Optional[pathlib.Path] = None) -> dict:
    if screenshot_dir is not None:
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    results: dict = {}
    started_server = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOWMO)
        try:
            started_server = start_sample_app()

            dash_ctx = browser.new_context(storage_state=STORAGE_STATE)
            dash_page = dash_ctx.new_page()

            original_new_engine_state = get_new_engine_master_state(dash_page)
            original_inflight_all_messages = get_inflight_all_messages_state(dash_page)
            print(f"[state] new-engine master was {'ON' if original_new_engine_state else 'OFF'}")
            print(f"[state] in-flight 'All Messages' was {'ON' if original_inflight_all_messages else 'OFF'}")

            set_new_engine_master_state(dash_page, False)
            set_inflight_all_messages_state(dash_page, False)

            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            open_conversation(page)

            print("\n=== Profanity Filter ===")
            results["profanity-filter"] = check_profanity_filter(page, screenshot_dir)
            print(json.dumps(results["profanity-filter"], indent=2, default=str))

            print("\n=== Image Moderation ===")
            results["image-moderation"] = check_image_moderation(page, screenshot_dir)
            print(json.dumps(results["image-moderation"], indent=2, default=str))

            print("\n=== Sentiment Analysis ===")
            results["sentiment-analysis"] = check_sentiment_analysis(page, screenshot_dir)
            print(json.dumps(results["sentiment-analysis"], indent=2, default=str))

            print("\n=== Virus & Malware Scanner ===")
            results["virus-malware-scanner"] = check_virus_scanner(page, screenshot_dir)
            print(json.dumps(results["virus-malware-scanner"], indent=2, default=str))

            print("\n=== In-Flight Message Moderation ===")
            set_inflight_all_messages_state(dash_page, True)
            results["human-moderation"] = check_inflight_moderation(dash_page, page, screenshot_dir)
            print(json.dumps(results["human-moderation"], indent=2, default=str))

            ctx.close()

            print("\n[restore] setting in-flight 'All Messages' back to "
                  f"{'ON' if original_inflight_all_messages else 'OFF'}")
            set_inflight_all_messages_state(dash_page, original_inflight_all_messages)

            print("[restore] setting new-engine master back to "
                  f"{'ON' if original_new_engine_state else 'OFF'}")
            set_new_engine_master_state(dash_page, original_new_engine_state)

            dash_ctx.close()
        finally:
            if not verify_extensions.KEEP_SERVER:
                stop_sample_app(started_server)
            browser.close()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-server", action="store_true", help="leave the sample app dev server running after")
    parser.add_argument("--app-id", help="switch to a different app (overrides CC_SAMPLE_APP_ID)")
    parser.add_argument("--region", help="region for --app-id (overrides CC_SAMPLE_APP_REGION, default 'eu')")
    parser.add_argument("--auth-key", help="Auth Key for --app-id (overrides CC_SAMPLE_APP_AUTH_KEY) — "
                         "required whenever --app-id differs from the EU default")
    parser.add_argument("--target-conversation", help="conversation name to run checks in "
                         "(overrides CC_TARGET_CONVERSATION, default 'Hiking Group') — must exist in --app-id's app")
    args = parser.parse_args()

    if args.keep_server:
        verify_extensions.KEEP_SERVER = True
    # Assigned on the verify_extensions module directly (not local names) so
    # every function in this file that reads verify_extensions.APP_ID/etc.
    # live sees the override — see the import-time-snapshot note near the
    # top of this file for why a local rebind wouldn't be enough.
    if args.app_id:
        verify_extensions.APP_ID = args.app_id
    if args.region:
        verify_extensions.REGION = args.region
    if args.auth_key:
        verify_extensions.AUTH_KEY = args.auth_key
    if args.target_conversation:
        verify_extensions.TARGET_CONVERSATION = args.target_conversation

    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"

    t0 = time.time()
    results = run(screenshot_dir=screenshot_dir)
    elapsed = time.time() - t0

    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "elapsed_s": round(elapsed, 1)}, f, indent=2, default=str)

    print(f"\n{'=' * 50}")
    print(f"Legacy Moderation check finished in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
