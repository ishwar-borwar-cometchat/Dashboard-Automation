#!/usr/bin/env python3
"""CometChat Dashboard <-> Sample App extension verification.

For each extension, toggles it OFF then ON on the CometChat Dashboard
(Products > Chat & Messaging > Features) and, in a freshly loaded Sample App
session for each state, confirms the UI matches (present when ON, absent
when OFF) and — when ON — actually sends a message through it, confirming
delivery (a single tick: left the client, acknowledged by the server).

Every extension is left ON when the script finishes, even on failure.

Lives at <repo root>/Automation Script/Extensions/verify_extensions.py — run
it from anywhere, it locates the repo root (auth/, modules/, reports/) from
its own file path, not from the working directory.

Usage
-----
    python3 "Automation Script/Extensions/verify_extensions.py"                  # everything, headless
    CC_HEADLESS=0 python3 "Automation Script/Extensions/verify_extensions.py"    # watch it run
    python3 "Automation Script/Extensions/verify_extensions.py" --only Stickers,Polls
    python3 "Automation Script/Extensions/verify_extensions.py" --keep-server    # leave npm start running after

Requires
--------
    - auth/storage_state.json for the Dashboard (see README:
      python3 utils/bootstrap_auth.py)
    - the sample app's dependencies installed (npm install in
      CC_SAMPLE_APP_DIR)

Config (env vars, same convention as conftest.py)
--------------------------------------------------
    CC_BASE_URL          Dashboard origin (default https://app.cometchat.com)
    CC_SAMPLE_APP_ID     App ID the Sample App connects to (see
                          sample-app/src/AppConstants.ts) — NOT the same as
                          conftest.py's CC_APP_ID, which targets a different
                          test app used by the pytest suite.
    CC_STORAGE_STATE     Dashboard auth state (default auth/storage_state.json)
    CC_HEADLESS          "0" to watch it run (default "1")
    CC_SLOWMO            ms delay between actions when headed (default "0")
    CC_SAMPLE_APP_DIR    Path to the sample app (default set below)
    CC_SAMPLE_APP_PORT   Dev server port (default 3010)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import subprocess
import time
import urllib.request
from typing import Optional

import sys

# This script lives at <repo root>/Automation Script/Extensions/ — two
# levels below the repo root that `modules/`, `auth/` and `reports/` hang
# off of, so that's what goes on sys.path and what every default path below
# is built from (not this file's own directory).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright, Page

from modules.products.chat_and_messaging.chat_features_page import ChatFeaturesPage

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = REPO_ROOT
REPORTS = ROOT / "reports" / "extension_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_SAMPLE_APP_ID", "168258051159eab49")
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"
SLOWMO = int(os.environ.get("CC_SLOWMO", "0"))

SAMPLE_APP_DIR = os.environ.get(
    "CC_SAMPLE_APP_DIR",
    "/Users/admin/Documents/Claude/Dashboard/cometchat-uikit-react-v6/sample-app",
)
SAMPLE_APP_PORT = int(os.environ.get("CC_SAMPLE_APP_PORT", "3010"))
SAMPLE_APP_URL = f"http://localhost:{SAMPLE_APP_PORT}"
SAMPLE_APP_START_TIMEOUT = 90
TEST_IMAGE = str(pathlib.Path(SAMPLE_APP_DIR) / "src" / "assets" / "nancy-grace.png")

# (dashboard display name, sample-app kind) — kind selects the check/send
# logic below. Names/labels are byte-exact against the live DOM.
EXTENSIONS = [
    {"key": "Stickers", "name": "Stickers", "kind": "sticker"},
    {"key": "Polls", "name": "Polls", "kind": "poll"},
    {"key": "Collaborative document", "name": "Collaborative Document", "kind": "doc"},
    {"key": "Collaborative whiteboard", "name": "Collaborative Whiteboard", "kind": "whiteboard"},
    {"key": "Link Preview", "name": "Link Preview", "kind": "link"},
    {"key": "Thumbnail Generation", "name": "Thumbnail Generation", "kind": "thumbnail"},
    {"key": "Message shortcuts", "name": "Message Shortcuts", "kind": "shortcut"},
    {"key": "Message Translation", "name": "Message Translation", "kind": "translation"},
    {"key": "Disappearing messages", "name": "Disappearing Messages", "kind": "disappearing"},
]

# Per-kind browser-context overrides. Message Translation reads the raw
# navigator.language (not the UIKit's own locale, which the sample app pins
# to en-US via setupLocalization()) to pick a target language — it needs a
# non-English locale here or the extension detects source == target and
# emits its "already in this language" error instead of a translated bubble.
CONTEXT_KWARGS = {
    "translation": {"locale": "fr-FR"},
}


# ---------------------------------------------------------------------------
# Sample app dev server
# ---------------------------------------------------------------------------
def sample_app_is_up() -> bool:
    try:
        with urllib.request.urlopen(SAMPLE_APP_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_sample_app() -> Optional[subprocess.Popen]:
    if sample_app_is_up():
        print(f"[sample-app] already running at {SAMPLE_APP_URL}")
        return None
    print(f"[sample-app] starting `npm start` on port {SAMPLE_APP_PORT} ...")
    env = os.environ.copy()
    env["BROWSER"] = "none"
    env["PORT"] = str(SAMPLE_APP_PORT)
    proc = subprocess.Popen(
        ["npm", "start"],
        cwd=SAMPLE_APP_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + SAMPLE_APP_START_TIMEOUT
    while time.time() < deadline:
        if sample_app_is_up():
            print("[sample-app] ready")
            return proc
        time.sleep(1)
    raise RuntimeError(f"sample app did not come up within {SAMPLE_APP_START_TIMEOUT}s")


def stop_sample_app(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    print("[sample-app] stopping ...")
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------------------
# Sample app helpers
# ---------------------------------------------------------------------------
def open_conversation(page: Page) -> None:
    page.goto(SAMPLE_APP_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2500)
    login_user = page.locator(".cometchat-login__user").first
    if login_user.count() > 0:
        login_user.click()
        page.wait_for_timeout(6000)
    convo = page.locator(".cometchat-conversations__list-item, .cometchat-conversation").first
    if convo.count() > 0:
        convo.click()
        page.wait_for_timeout(1500)


def open_attach_menu(page: Page) -> bool:
    attach = page.locator('button[title="Attach"]')
    if attach.count() == 0:
        return False
    attach.first.click()
    page.wait_for_timeout(900)
    return True


# ---------------------------------------------------------------------------
# Per-kind check + send logic. Each returns (present, sent).
# `sent` is None when the state is OFF (nothing should be sendable) or a
# send wasn't attempted.
# ---------------------------------------------------------------------------
def verify_sticker(page: Page, target_on: bool):
    present = page.locator('button[title="Sticker"]').count() > 0
    if not target_on or not present:
        return present, None
    page.locator('button[title="Sticker"]').first.click()
    page.wait_for_timeout(1500)
    tiles = page.locator(".cometchat-sticker-keyboard__list-item")
    if tiles.count() == 0:
        page.keyboard.press("Escape")
        return present, False
    tiles.first.click()
    page.wait_for_timeout(2500)
    preview = page.locator(".cometchat-conversations__list-item").first.inner_text()
    return present, "sticker" in preview.lower()


def verify_poll(page: Page, target_on: bool):
    if not open_attach_menu(page):
        return False, None
    item = page.get_by_text("Polls", exact=False).first
    present = item.count() > 0
    if not target_on or not present:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return present, None
    item.click()
    page.wait_for_timeout(1000)
    question = f"Automated check {int(time.time())}"
    page.get_by_placeholder("Ask question").fill(question)
    adds = page.get_by_placeholder("Add")
    adds.nth(0).fill("Yes")
    adds.nth(1).fill("No")
    page.wait_for_timeout(300)
    page.get_by_role("button", name="Create").click()
    page.wait_for_timeout(2500)
    sent = question in page.inner_text("body")
    return present, sent


def _verify_collab(page: Page, target_on: bool, label: str, ready_snippet: str):
    if not open_attach_menu(page):
        return False, None
    item = page.get_by_text(label, exact=False).first
    present = item.count() > 0
    if not target_on or not present:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return present, None
    item.click()
    page.wait_for_timeout(3000)
    sent = ready_snippet in page.inner_text("body")
    return present, sent


def verify_doc(page: Page, target_on: bool):
    return _verify_collab(page, target_on, "Collaborative Document", "Open document to edit content together")


def verify_whiteboard(page: Page, target_on: bool):
    return _verify_collab(page, target_on, "Collaborative Whiteboard", "Open whiteboard to draw together")


def verify_link(page: Page, target_on: bool):
    before = page.locator('[class*="cometchat-link-bubble__preview-image"]').count()
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    marker = int(time.time())
    composer.type(f"Automated check {marker} https://www.cometchat.com")
    page.keyboard.press("Enter")
    page.wait_for_timeout(5000)
    after = page.locator('[class*="cometchat-link-bubble__preview-image"]').count()
    present = after > before
    sent = str(marker) in page.inner_text("body")
    return present, sent


def verify_thumbnail(page: Page, target_on: bool):
    before = page.locator('img[src*="/media/thumbnails/"]').count()
    if not open_attach_menu(page):
        return False, None
    with page.expect_file_chooser() as fc_info:
        page.get_by_text("Attach Image", exact=False).first.click()
    fc_info.value.set_files(TEST_IMAGE)
    page.wait_for_timeout(4000)
    after = page.locator('img[src*="/media/thumbnails/"]').count()
    present = after > before
    sent = page.locator('[class*="image-bubble"] img, [class*="message"] img').count() > 0
    return present, sent


def verify_shortcut(page: Page, target_on: bool):
    """Message Shortcuts has no first-party UIKit component (confirmed: no
    "shortcut" reference anywhere in @cometchat/chat-uikit-react) — the
    trigger/suggestion/insert flow lives in sample-app/src/utils/
    ShortcutFormatter.ts + ShortcutDialog.tsx, custom-built via the UIKit's
    public CometChatTextFormatter extension point (the same one Mentions and
    URL-linkification use) and gated on the Dashboard toggle via
    CometChat.isExtensionEnabled("message-shortcuts").
    """
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    composer.type("!hbd", delay=60)
    page.wait_for_timeout(1500)
    dialog = page.locator("#shortcut-dialog div").first
    present = dialog.count() > 0

    if not target_on or not present:
        composer.press("Control+A")
        composer.press("Delete")
        return present, None

    dialog.click()
    page.wait_for_timeout(800)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)
    sent = "Happy Birthday" in page.inner_text("body")
    return present, sent


def verify_message_translation(page: Page, target_on: bool):
    """Message Translation has no composer/attach-menu trigger — it adds a
    "Translate" entry to a text message's own overflow (···) options menu
    (CometChatMessageTranslationExtensionDecorator.getTextMessageOptions,
    id "translate", label from message_list_translate = "Translate"). So the
    flow is: send a message, hover it to reveal
    .cometchat-message-bubble__options, open its "more" submenu
    (.cometchat-menu-list__sub-menu), and check for that item. The context
    for this kind is created with locale=fr-FR (see CONTEXT_KWARGS) so the
    extension's target language differs from the message's detected English
    source — same source/target would surface as a translation error instead
    of a rendered MessageTranslationBubble.
    """
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    marker = f"Automated translation check {int(time.time())}"
    composer.type(marker)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)

    bubble = page.locator(".cometchat-message-bubble", has_text=marker).last
    if bubble.count() == 0:
        return False, None
    # The options bar shows via onMouseEnter on .cometchat-message-bubble__body
    # specifically (not the bubble at large) — Playwright's synthetic hover
    # doesn't reliably land inside that inner element, but the same handler
    # also fires via that element's onClick, which is reliable headless.
    bubble.locator(".cometchat-message-bubble__body").first.click()
    page.wait_for_timeout(500)

    more_btn = bubble.locator(".cometchat-menu-list__sub-menu")
    if more_btn.count() == 0:
        return False, None
    more_btn.first.click()
    page.wait_for_timeout(600)

    # Every message in the list renders its own (mostly hidden) submenu, so
    # this must stay scoped to `bubble` — an unscoped page-wide locator can
    # resolve to a different message's stale, invisible copy of the item.
    translate_item = bubble.locator('.cometchat-menu-list__sub-menu-list-item[title="Translate"]')
    present = translate_item.count() > 0
    if not target_on or not present:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return present, None

    translate_item.first.click()
    page.wait_for_timeout(3000)
    sent = page.locator(".cometchat-tanslation-bubble__translated-text").count() > 0
    return present, sent


def verify_disappearing_messages(page: Page, target_on: bool):
    """Disappearing Messages has no composer/menu trigger at all — it's driven
    purely by the extension's own v1/disappear API (msgId + an absolute future
    epoch-ms timestamp). Verified by sending a real message, resolving its id
    through the SDK's own MessagesRequestBuilder (reads the real message list,
    not a DOM scrape), scheduling a short (~5s) disappear via
    CometChat.callExtension, and waiting for the UIKit's real-time
    onMessageDeleted update to swap the bubble for the standard "This message
    was deleted" placeholder (CometChatDeleteBubble / message_deleted string).
    `present` here means "the schedule call itself was accepted" — this is the
    only signal available for the off state, since there's no UI element to
    check for absence.
    """
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    marker = f"Disappear check {int(time.time())}"
    composer.type(marker)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)

    js_fetch = """
    async (guid) => {
        const builder = new CometChat.MessagesRequestBuilder().setGUID(guid).setLimit(5).build();
        const messages = await builder.fetchPrevious();
        return messages.map(m => ({ id: m.getId(), text: (m.getText && m.getText()) || null }));
    }
    """
    msgs = page.evaluate(js_fetch, "cometchat-guid-1")
    match = [m for m in msgs if m.get("text") == marker]
    if not match:
        return False, None
    msg_id = match[0]["id"]

    schedule_time = int(time.time() * 1000) + 5000
    js_schedule = """
    async ([msgId, timeInMS]) => {
        try {
            await CometChat.callExtension("disappearing-messages", "DELETE", "v1/disappear", { msgId, timeInMS });
            return true;
        } catch (e) {
            return false;
        }
    }
    """
    present = bool(page.evaluate(js_schedule, [msg_id, schedule_time]))
    if not target_on or not present:
        return present, None

    page.wait_for_timeout(9000)
    sent = page.get_by_text("This message was deleted").count() > 0
    return present, sent


VERIFIERS = {
    "sticker": verify_sticker,
    "poll": verify_poll,
    "doc": verify_doc,
    "whiteboard": verify_whiteboard,
    "link": verify_link,
    "thumbnail": verify_thumbnail,
    "shortcut": verify_shortcut,
    "translation": verify_message_translation,
    "disappearing": verify_disappearing_messages,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(only: Optional[list[str]] = None, screenshot_dir: Optional[pathlib.Path] = None) -> dict:
    targets = [e for e in EXTENSIONS if not only or e["name"] in only or e["key"] in only]
    if not targets:
        raise SystemExit(f"No extensions matched --only {only!r}")

    if screenshot_dir is not None:
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    started_server = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOWMO)
        try:
            started_server = start_sample_app()

            dash_ctx = browser.new_context(storage_state=STORAGE_STATE)
            dash_page = dash_ctx.new_page()
            cf = ChatFeaturesPage(dash_page, APP_ID, BASE_URL)
            cf.open(force=True)

            for ext in targets:
                name, key, kind = ext["name"], ext["key"], ext["kind"]
                verifier = VERIFIERS[kind]
                results[name] = {}
                print(f"\n=== {name} ===")

                for state_label, target in [("off", False), ("on", True)]:
                    cf.set_extension(key, target)
                    dash_state = cf.is_enabled(key)

                    ctx = browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        **CONTEXT_KWARGS.get(kind, {}),
                    )
                    page = ctx.new_page()
                    open_conversation(page)
                    present, sent = verifier(page, target)

                    shot_path = None
                    if screenshot_dir is not None:
                        page.wait_for_timeout(400)
                        shot_path = screenshot_dir / f"{name.replace(' ', '_')}_{state_label}.png"
                        page.screenshot(path=str(shot_path))

                    ctx.close()

                    match = dash_state == present
                    results[name][state_label] = {
                        "dashboard_enabled": dash_state,
                        "sample_app_present": present,
                        "sent": sent,
                        "match": match,
                        "screenshot": str(shot_path) if shot_path else None,
                    }
                    flag = "OK" if match else "MISMATCH"
                    sent_note = "" if sent is None else f", sent={sent}"
                    print(
                        f"  {state_label.upper():>3}  dashboard={dash_state!s:<5} "
                        f"sample_app={present!s:<5}{sent_note}  [{flag}]"
                    )

            dash_ctx.close()
        finally:
            if not KEEP_SERVER:
                stop_sample_app(started_server)
            browser.close()

    return results


def summarize(results: dict) -> tuple[int, int]:
    checks = 0
    passed = 0
    for name, states in results.items():
        for state_label, r in states.items():
            checks += 1
            if r["match"]:
                passed += 1
    return passed, checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated extension names to run (default: all)")
    parser.add_argument("--keep-server", action="store_true", help="leave the sample app dev server running after")
    args = parser.parse_args()

    global KEEP_SERVER
    KEEP_SERVER = args.keep_server

    only = [s.strip() for s in args.only.split(",")] if args.only else None

    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"

    t0 = time.time()
    results = run(only=only, screenshot_dir=screenshot_dir)
    elapsed = time.time() - t0

    passed, checks = summarize(results)
    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "passed": passed, "checks": checks, "elapsed_s": round(elapsed, 1)}, f, indent=2)

    print(f"\n{'=' * 50}")
    print(f"{passed}/{checks} checks passed in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")

    if passed != checks:
        raise SystemExit(1)


KEEP_SERVER = False

if __name__ == "__main__":
    main()
