#!/usr/bin/env python3
"""CometChat Dashboard <-> Sample App extension verification.

For each extension, toggles it OFF then ON on the CometChat Dashboard
(Products > Chat & Messaging > Features) and, in a freshly loaded Sample App
session for each state, confirms the UI matches (present when ON, absent
when OFF) and — when ON — actually sends a message through it, confirming
delivery (a single tick: left the client, acknowledged by the server).

Every extension is left ON when the script finishes, even on failure.

Lives at <repo root>/modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py — run
it from anywhere, it locates the repo root (auth/, modules/, reports/) from
its own file path, not from the working directory.

Usage
-----
    python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py"                  # everything, headless
    CC_HEADLESS=0 python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py"    # watch it run
    python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py" --only Stickers,Polls
    python3 "modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py" --keep-server    # leave npm start running after

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
    CC_SAMPLE_APP_REGION      Region for CC_SAMPLE_APP_ID (default "eu")
    CC_SAMPLE_APP_AUTH_KEY    Auth Key for CC_SAMPLE_APP_ID — required
                              whenever CC_SAMPLE_APP_ID is overridden; there
                              is no safe default for an app this script has
                              never seen. Or pass --app-id/--region/--auth-key.
    CC_TARGET_CONVERSATION    Name of the conversation to run checks in
                              (default "Hiking Group" — the CometChat Sample
                              App's stock seed group). Must exist in
                              whichever app CC_SAMPLE_APP_ID points to; its
                              real GUID is resolved dynamically at the start
                              of each run, never hardcoded.
    CC_STORAGE_STATE     Dashboard auth state (default auth/storage_state.json)
    CC_HEADLESS          "0" to watch it run (default "1")
    CC_SLOWMO            ms delay between actions when headed (default "0")
    CC_SAMPLE_APP_DIR    Path to the sample app (default set below)
    CC_SAMPLE_APP_PORT   Dev server port (default 3010)

Switching to a different app ID (2026-09-17)
---------------------------------------------
Pass --app-id/--region/--auth-key (or the matching env vars above) and this
script rewrites sample-app/src/AppConstants.ts itself, restarts the dev
server if one was already running against the old config, and resolves
CC_TARGET_CONVERSATION's real GUID fresh via the SDK — no manual file edits
needed. If the named conversation doesn't exist in the new app, pass
--target-conversation with one that does (a DM or group name visible in
that app's Sample App sidebar).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import signal
import subprocess
import time
import urllib.request
from typing import Optional

import sys

# This script lives at <repo root>/modules/products/chat_and_messaging/Feature ( Extensions)/ — four
# levels below the repo root that `modules/`, `auth/` and `reports/` hang
# off of, so that's what goes on sys.path and what every default path below
# is built from (not this file's own directory).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
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
# REGION has a convenience default (not a secret). AUTH_KEY does not, and
# never should — no credential is stored in this file. It's only required
# when actually switching to a different app than what's already configured
# on disk in AppConstants.ts; sync_sample_app_config() reads the existing
# key straight from that file when APP_ID/REGION match what's already
# there, and fails loudly asking for --auth-key only when they don't.
REGION = os.environ.get("CC_SAMPLE_APP_REGION", "eu")
AUTH_KEY = os.environ.get("CC_SAMPLE_APP_AUTH_KEY", "")
TARGET_CONVERSATION = os.environ.get("CC_TARGET_CONVERSATION", "Hiking Group")
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
APP_CONSTANTS_PATH = pathlib.Path(SAMPLE_APP_DIR) / "src" / "AppConstants.ts"

# Resolved once per run by open_conversation() (real SDK lookup, never
# hardcoded) and read by verifiers that need a GUID directly, e.g.
# verify_disappearing_messages. None until a conversation has been opened.
# Each extension's Dashboard state before this run touched it; restored afterwards so a run
# never leaves an app changed. Also written to the results JSON.
ORIGINAL_STATES: dict = {}
CURRENT_RECEIVER_TYPE: str = "group"      # 'group' or 'user' — what CURRENT_GUID is
_RESOLVED_FOR: Optional[str] = None   # target name CURRENT_GUID was resolved for (cached across states)
CURRENT_GUID: Optional[str] = None

# Resolved once per run by resolve_second_user() — a real UID belonging to
# someone other than the logged-in test account, for checks that need a
# second real person (report-user, e2ee's identity lookup). Added
# 2026-09-17 after report-user/e2ee were caught hardcoding "cometchat-uid-2"
# from this one app's seed data, which would silently target a nonexistent
# user on any other app. None until resolved.
CURRENT_SECOND_UID: Optional[str] = None
CURRENT_SELF_UID: Optional[str] = None

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


def read_sample_app_config() -> tuple[str, str, str]:
    """Current (app_id, region, auth_key) actually baked into AppConstants.ts
    on disk — the source of truth for what the Sample App will connect to,
    independent of what this script's own APP_ID/REGION/AUTH_KEY vars say.
    """
    text = APP_CONSTANTS_PATH.read_text()
    app_id = re.search(r'APP_ID:\s*"([^"]*)"', text).group(1)
    region = re.search(r'REGION:\s*"([^"]*)"', text).group(1)
    auth_key = re.search(r'AUTH_KEY:\s*"([^"]*)"', text).group(1)
    return app_id, region, auth_key


def sync_sample_app_config() -> bool:
    """Rewrites AppConstants.ts in place if APP_ID/REGION don't already
    match what's on disk. Returns True if it changed anything, so the
    caller can force a full dev-server restart rather than trust webpack's
    hot-reload to safely re-run index.tsx's one-time CometChat.init() call.
    Fixed 2026-09-17: this used to be a manual, by-hand file edit every time
    the app under test changed — easy to forget, and easy to leave stale.

    No credential is stored in this script (fixed 2026-09-17, before the
    first push to the public GitHub remote — an earlier version of this
    function hardcoded a real Auth Key as AUTH_KEY's default, which would
    have shipped a live credential in plain text). AUTH_KEY is only required
    when APP_ID/REGION actually differ from what's already configured on
    disk — continuing to use whatever app is already set up needs nothing
    extra, matching the "AppConstants.ts on disk is the source of truth"
    read in read_sample_app_config().
    """
    current_app_id, current_region, current_auth_key = read_sample_app_config()
    if (current_app_id, current_region) == (APP_ID, REGION):
        return False

    if not AUTH_KEY:
        raise RuntimeError(
            f"CC_SAMPLE_APP_ID/--app-id is {APP_ID!r}, which differs from what's currently "
            f"configured on disk ({current_app_id!r}) — pass --auth-key (or "
            "CC_SAMPLE_APP_AUTH_KEY) explicitly for the new app. No default key is stored "
            "in this script; refusing to guess rather than connect with a stale/wrong one."
        )

    print(f"[sample-app] config differs — rewriting AppConstants.ts: "
          f"{current_app_id}/{current_region} -> {APP_ID}/{REGION}")
    text = APP_CONSTANTS_PATH.read_text()
    text = re.sub(r'(APP_ID:\s*")[^"]*(")', rf'\g<1>{APP_ID}\g<2>', text, count=1)
    text = re.sub(r'(REGION:\s*")[^"]*(")', rf'\g<1>{REGION}\g<2>', text, count=1)
    text = re.sub(r'(AUTH_KEY:\s*")[^"]*(")', rf'\g<1>{AUTH_KEY}\g<2>', text, count=1)
    APP_CONSTANTS_PATH.write_text(text)
    return True


def _kill_process_on_port(port: int) -> None:
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for pid in out.splitlines():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass
    if out:
        time.sleep(1)


def start_sample_app() -> Optional[subprocess.Popen]:
    config_changed = sync_sample_app_config()
    if sample_app_is_up():
        if config_changed:
            print("[sample-app] config changed — restarting the running dev server to pick it up")
            _kill_process_on_port(SAMPLE_APP_PORT)
        else:
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
def resolve_receiver_by_name(page: Page, target_name: str) -> Optional[tuple]:
    """Like resolve_guid_by_name, but returns (id, 'group'|'user') so callers can pick the right
    SDK call (setGUID vs setUID) when the conversation under test is a 1:1 chat."""
    r = page.evaluate(
        """
        async (name) => {
            for (const kind of ['group', 'user']) {
                try {
                    const b = kind === 'group' ? new CometChat.GroupsRequestBuilder() : new CometChat.UsersRequestBuilder();
                    const list = await b.setLimit(30).setSearchKeyword(name).build().fetchNext();
                    const hit = list.find(x => x.getName() === name);
                    if (hit) return [kind === 'group' ? hit.getGuid() : hit.getUid(), kind];
                } catch (e) {}
            }
            for (const kind of ['group', 'user']) {
                try {
                    const b = kind === 'group' ? new CometChat.GroupsRequestBuilder() : new CometChat.UsersRequestBuilder();
                    const list = await b.setLimit(30).build().fetchNext();
                    const hit = list.find(x => x.getName() === name);
                    if (hit) return [kind === 'group' ? hit.getGuid() : hit.getUid(), kind];
                } catch (e) {}
            }
            return null;
        }
        """,
        target_name,
    )
    return tuple(r) if r else None


def resolve_guid_by_name(page: Page, target_name: str) -> Optional[str]:
    """Resolves target_name to its real GUID/UID via the SDK — groups first,
    then users — never hardcoded. Added 2026-09-17 so a different app's seed
    data (different real IDs, possibly not even a group) doesn't require a
    code change here; only CC_TARGET_CONVERSATION needs to change.
    """
    return page.evaluate(
        """
        async (name) => {
            // Search by keyword first: on an app with many users/groups the first page of 30
            // (alphabetical) need not contain the target. Then fall back to the plain first page.
            try {
                const groups = await new CometChat.GroupsRequestBuilder().setLimit(30).setSearchKeyword(name).build().fetchNext();
                const g = groups.find(x => x.getName() === name);
                if (g) return g.getGuid();
            } catch (e) {}
            try {
                const users = await new CometChat.UsersRequestBuilder().setLimit(30).setSearchKeyword(name).build().fetchNext();
                const u = users.find(x => x.getName() === name);
                if (u) return u.getUid();
            } catch (e) {}
            try {
                const groups = await new CometChat.GroupsRequestBuilder().setLimit(30).build().fetchNext();
                const g = groups.find(x => x.getName() === name);
                if (g) return g.getGuid();
            } catch (e) {}
            try {
                const users = await new CometChat.UsersRequestBuilder().setLimit(30).build().fetchNext();
                const u = users.find(x => x.getName() === name);
                if (u) return u.getUid();
            } catch (e) {}
            return null;
        }
        """,
        target_name,
    )


def resolve_second_user(page: Page) -> tuple[Optional[str], Optional[str]]:
    """Returns (self_uid, second_uid) — the logged-in account's own UID and
    a real UID belonging to someone else in this app, both via the SDK.
    Added 2026-09-17 after report-user/e2ee were caught hardcoding
    "cometchat-uid-2" (this one app's seed data) as "some other real user" —
    a different app's real second user has a different, unpredictable UID.
    second_uid is None if this app genuinely has only one user.
    """
    return page.evaluate(
        """
        async () => {
            let selfUid = null;
            try {
                const me = await CometChat.getLoggedinUser();
                selfUid = me ? me.getUid() : null;
            } catch (e) {}
            let secondUid = null;
            try {
                const users = await new CometChat.UsersRequestBuilder().setLimit(30).build().fetchNext();
                const other = users.find(u => u.getUid() !== selfUid);
                secondUid = other ? other.getUid() : null;
            } catch (e) {}
            return [selfUid, secondUid];
        }
        """
    )


def open_conversation(page: Page, target_name: Optional[str] = None) -> None:
    """Opens a specific, named conversation rather than trusting `.first` on
    the conversation list. Fixed 2026-09-17: this app is actively used by
    other test flows in the same session, which reorders the list by recent
    activity — `.first` silently landed on whatever conversation someone else
    had just messaged, so a verifier's composer/attach-menu actions and any
    GUID-scoped SDK readback (e.g. legacy moderation's checks) could end up
    targeting two different conversations without either side erroring.

    Also resolves target_name's real GUID, plus a real second user, via the
    SDK and stashes them on the module-level CURRENT_GUID / CURRENT_SECOND_UID
    / CURRENT_SELF_UID for verifiers that need one directly (e.g.
    verify_disappearing_messages, report-user, e2ee) — replaces what used to
    be hardcoded IDs specific to this one app's seed data.
    """
    global CURRENT_GUID, CURRENT_SECOND_UID, CURRENT_SELF_UID, CURRENT_RECEIVER_TYPE, _RESOLVED_FOR
    if target_name is None:
        target_name = TARGET_CONVERSATION  # read at call time, not def time — CLI args can override this after import
    page.goto(SAMPLE_APP_URL, wait_until="domcontentloaded", timeout=60_000)
    # Wait for whichever comes first — the login screen or an already-logged-in
    # conversation list — instead of sleeping a fixed 2.5s + 6s.
    try:
        page.wait_for_selector(".cometchat-login__user, .cometchat-conversations__list-item", timeout=30_000)
    except Exception:
        pass
    login_user = page.locator(".cometchat-login__user").first
    if login_user.count() > 0:
        login_user.click()
        try:
            page.wait_for_selector(".cometchat-conversations__list-item", timeout=30_000)
        except Exception:
            page.wait_for_timeout(3000)
    items = page.locator(".cometchat-conversations__list-item")
    row = items.filter(has_text=target_name).first
    for i in range(items.count()):                       # exact title match wins over a preview-text match
        lines = [ln.strip() for ln in items.nth(i).inner_text().split("\n") if ln.strip()]
        if lines and lines[0] == target_name:
            row = items.nth(i)
            break
    if row.count() == 0:
        # fall back to whatever's first rather than hard-failing every kind
        row = page.locator(".cometchat-conversations__list-item, .cometchat-conversation").first
    if row.count() > 0:
        row.click()
        try:
            page.locator('[contenteditable="true"]').first.wait_for(state="visible", timeout=10_000)   # composer up = chat open
        except Exception:
            page.wait_for_timeout(1500)

    # The real GUID / second user never change between states of one run, so look
    # them up once (an SDK round trip each) and reuse them for the other states.
    if CURRENT_GUID is not None and _RESOLVED_FOR == target_name:
        return
    try:
        _r = resolve_receiver_by_name(page, target_name)
        CURRENT_GUID, CURRENT_RECEIVER_TYPE = (_r if _r else (None, "group"))
    except Exception:
        CURRENT_GUID, CURRENT_RECEIVER_TYPE = None, "group"
    if CURRENT_GUID is None:
        print(f"[open_conversation] WARNING: could not resolve a real GUID for "
              f"{target_name!r} via the SDK — disappearing-messages check will fail "
              f"cleanly rather than silently target the wrong conversation.")

    try:
        CURRENT_SELF_UID, CURRENT_SECOND_UID = resolve_second_user(page)
    except Exception:
        CURRENT_SELF_UID, CURRENT_SECOND_UID = None, None
    if CURRENT_SECOND_UID is None:
        print("[open_conversation] WARNING: could not resolve a second real user via "
              "the SDK — report-user/e2ee checks that need one will fail cleanly "
              "rather than silently target a nonexistent UID.")
    if CURRENT_GUID is not None:
        _RESOLVED_FOR = target_name


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
# Optional human-readable reason a verifier wants attached to its result
# (read and cleared by run()); keeps every verifier's (present, sent) tuple
# signature unchanged.
LAST_REASON: dict = {}


class ProbeBlocked(Exception):
    """The verifier's own test message was blocked by the app's moderation policies, so the
    extension could not be exercised at all. That is neither a pass nor a failure of the
    extension — run() records it as "untestable" with the reason."""


def last_bubble(page: Page):
    """The most recent message bubble in the open conversation (or None)."""
    bubbles = page.locator(".cometchat-message-bubble")
    n = bubbles.count()
    return bubbles.nth(n - 1) if n else None


def last_send_failed(page: Page) -> bool:
    """Did the MOST RECENT message fail to send? Scoped to the last bubble on purpose: a
    conversation's history keeps older blocked messages (with their error marker), and a
    page-wide check turned that stale history into a false "not sent" for every extension."""
    b = last_bubble(page)
    return bool(b and b.locator(".cometchat-receipts-error").count() > 0)


def probe_id() -> str:
    """A short unique id for test messages. NOT a 10-digit epoch: apps with a phone-number /
    contact-details moderation rule block a message that contains one (found on a real app where
    every "…check 1789803062" probe was blocked), which made whole extensions untestable."""
    return f"{int(time.time()) % 100000:05d}"


def wait_send_outcome(page: Page, timeout_ms: int = 8000) -> str:
    """Wait until the newest bubble shows a failure marker or a delivery receipt ('failed' /
    'sent' / 'unknown' on timeout) — moderation blocks are only reported after a round trip."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        b = last_bubble(page)
        if b:
            if b.locator(".cometchat-receipts-error").count():
                return "failed"
            if b.locator('[class*="cometchat-receipts"]').count():
                return "sent"
        page.wait_for_timeout(400)
    return "unknown"


def last_bubble_text(page: Page) -> str:
    b = last_bubble(page)
    return b.inner_text() if b else ""


def verify_sticker(page: Page, target_on: bool):
    present = page.locator('button[title="Sticker"]').count() > 0
    if not target_on or not present:
        return present, None
    page.locator('button[title="Sticker"]').first.click()
    page.wait_for_timeout(1500)
    tiles = page.locator(".cometchat-sticker-keyboard__list-item")
    if tiles.count() == 0:
        # Extension is ON and the tray opens, but the app has no sticker packs
        # ("No Stickers Available") — nothing can be sent. That is NOT a pass.
        LAST_REASON["sticker"] = "Sticker tray is empty (\"No Stickers Available\") — no sticker packs on this app, so nothing could be sent."
        page.keyboard.press("Escape")
        return present, False
    tiles.first.click()
    page.wait_for_timeout(2500)
    preview = page.locator(".cometchat-conversations__list-item").first.inner_text()
    # See _verify_collab for why the receipts-error check matters here too.
    sent = "sticker" in preview.lower() and not last_send_failed(page)
    return present, sent


def verify_poll(page: Page, target_on: bool):
    if not open_attach_menu(page):
        return False, None
    # Scoped to the actual attach action-sheet, not a bare page-wide text
    # search — fixed 2026-09-17: `get_by_text(..., exact=False)` could match
    # an identically-worded <label> left inside an OLD, already-sent message
    # bubble elsewhere in the conversation instead of the live menu item,
    # producing a false PASS (click "succeeds" on an off-screen stale
    # element, real menu item never touched).
    item = page.locator(".cometchat-action-sheet__item", has_text="Polls").first
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
    # Fixed 2026-09-17: a blocked/failed create leaves the modal open with an
    # inline "Something went wrong. Please try again." error instead of
    # closing — check for that first rather than trusting body text, since
    # the typed question text is still visible inside the open modal either
    # way (it's the form field's own value, not proof of a successful send).
    modal_error = page.locator("text=Something went wrong").count() > 0
    sent = not modal_error and question in page.inner_text("body")
    if modal_error:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return present, sent


def _verify_collab(page: Page, target_on: bool, label: str, ready_snippet: str):
    if not open_attach_menu(page):
        return False, None
    # Same fix as verify_poll: scope to the real attach action-sheet item,
    # not a bare page-wide text match that can hit a stale old bubble label.
    item = page.locator(".cometchat-action-sheet__item", has_text=label).first
    present = item.count() > 0
    if not target_on or not present:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return present, None
    item.click()
    page.wait_for_timeout(3000)
    # Fixed 2026-09-17: text presence alone is a false-positive risk — an
    # optimistic local bubble renders the same text whether or not the send
    # actually succeeded server-side (proven with In-flight Message
    # Moderation active: a blocked send still showed "Happy Birthday" text,
    # just with a `cometchat-receipts-error` marker instead of `-sent`).
    # A fresh context is opened per state in run(), so any error marker seen
    # here belongs to this action, not stale history.
    sent = ready_snippet in last_bubble_text(page) and not last_send_failed(page)
    return present, sent


def verify_doc(page: Page, target_on: bool):
    return _verify_collab(page, target_on, "Collaborative Document", "Open document to edit content together")


def verify_whiteboard(page: Page, target_on: bool):
    return _verify_collab(page, target_on, "Collaborative Whiteboard", "Open whiteboard to draw together")


def verify_link(page: Page, target_on: bool):
    # The link-preview card is populated by an async out-of-band fetch (the
    # extension calls out to iframely/opengraph resolution before returning
    # title/description/image) — confirmed via a direct SDK write+readback
    # test (2026-09-16) that this can take up to ~15-20s even though the
    # server accepts the message and returns 200 immediately. A short wait
    # here reads a real, working card as absent. 20s is deliberately
    # generous rather than tuned to the minimum that passes.
    before = page.locator('[class*="cometchat-link-bubble__preview-image"]').count()
    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    marker = probe_id()
    composer.type(f"Automated check {marker} https://www.cometchat.com")
    page.keyboard.press("Enter")
    # ON: return the moment the card appears. OFF: absence can only be shown by
    # waiting out the whole window, so that stays at the full 20s.
    if target_on:
        try:
            page.wait_for_function(
                "n => document.querySelectorAll('[class*=\"cometchat-link-bubble__preview-image\"]').length > n",
                arg=before, timeout=20000)
        except Exception:
            pass
    else:
        page.wait_for_timeout(20000)
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
    # See _verify_collab for why the receipts-error check matters here too.
    sent = "Happy Birthday" in last_bubble_text(page) and not last_send_failed(page)
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
    marker = f"Automated translation check {probe_id()}"
    composer.type(marker)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)

    bubble = page.locator(".cometchat-message-bubble", has_text=marker).last
    try:
        bubble.wait_for(state="attached", timeout=6000)
    except Exception:
        raise ProbeBlocked("The probe message never appeared in the chat, so it could not be checked whether Translate is offered — inconclusive, not a failure.")
    if wait_send_outcome(page) == "failed":
        raise ProbeBlocked("The probe message was blocked by this app's moderation policies, so this extension could not be tested.")
    # The options bar shows via onMouseEnter on .cometchat-message-bubble__body
    # specifically (not the bubble at large) — Playwright's synthetic hover
    # doesn't reliably land inside that inner element, but the same handler
    # also fires via that element's onClick, which is reliable headless.
    body = bubble.locator(".cometchat-message-bubble__body").first
    more_btn = bubble.locator(".cometchat-menu-list__sub-menu")
    # Opening the options menu is the flaky part of this check (the bar only shows
    # on hover/click of the bubble body). Try up to 3 times before deciding, and if
    # the menu never opens report "inconclusive" — never "Translate is missing".
    opened = False
    for _attempt in range(3):
        body.scroll_into_view_if_needed()
        try:
            body.click(timeout=5000)
        except Exception:
            body.dispatch_event("click")   # newest bubble can sit under the composer toolbar
        try:
            more_btn.first.wait_for(state="attached", timeout=2500)
        except Exception:
            pass
        if more_btn.count() > 0:
            opened = True
            break
        try:
            bubble.hover(timeout=2000)
        except Exception:
            pass
        page.wait_for_timeout(400)
    if not opened:
        raise ProbeBlocked("The message's options menu did not open after 3 attempts, so it could not be checked whether Translate is offered — inconclusive, not a failure.")
    try:
        more_btn.first.click(timeout=5000)
    except Exception:
        more_btn.first.dispatch_event("click")
    page.wait_for_timeout(500)

    # Every message in the list renders its own (mostly hidden) submenu, so
    # this must stay scoped to `bubble` — an unscoped page-wide locator can
    # resolve to a different message's stale, invisible copy of the item.
    translate_item = bubble.locator('.cometchat-menu-list__sub-menu-list-item[title="Translate"]')
    present = translate_item.count() > 0
    if not target_on or not present:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return present, None

    try:
        translate_item.first.click(timeout=5000)
    except Exception:
        translate_item.first.dispatch_event("click")   # item can sit under the composer toolbar
    try:
        page.locator(".cometchat-tanslation-bubble__translated-text").first.wait_for(timeout=6000)
    except Exception:
        pass
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

    Uses the module-level CURRENT_GUID (resolved dynamically by
    open_conversation from CC_TARGET_CONVERSATION, not hardcoded) — fixed
    2026-09-17 so this works against any app's seed data, not just the one
    with a group literally named "cometchat-guid-1".
    """
    if not CURRENT_GUID:
        return False, None

    composer = page.locator('[contenteditable="true"]').first
    composer.click()
    marker = f"Disappear check {probe_id()}"
    composer.type(marker)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)

    if wait_send_outcome(page) == "failed":
        raise ProbeBlocked("The probe message was blocked by this app's moderation policies, so this extension could not be tested.")

    # A 1:1 conversation is addressed by UID, a group by GUID.
    js_fetch = """
    async ([id, kind]) => {
        const b = new CometChat.MessagesRequestBuilder();
        (kind === 'user' ? b.setUID(id) : b.setGUID(id)).setLimit(5);
        const messages = await b.build().fetchPrevious();
        return messages.map(m => ({ id: m.getId(), text: (m.getText && m.getText()) || null }));
    }
    """
    msgs = page.evaluate(js_fetch, [CURRENT_GUID, CURRENT_RECEIVER_TYPE])
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
def restore_original_states(browser) -> None:
    """Put every extension this run touched back to the Dashboard state it started in.
    Runs from run()'s finally, so it also happens after a crash mid-run."""
    if not ORIGINAL_STATES:
        return
    ctx = browser.new_context(storage_state=STORAGE_STATE)
    try:
        page = ctx.new_page()
        cf = ChatFeaturesPage(page, APP_ID, BASE_URL)
        cf.open(force=True)
        for ext in EXTENSIONS:
            name, key = ext["name"], ext["key"]
            if name in ORIGINAL_STATES and cf.exists(key) and cf.is_enabled(key) != ORIGINAL_STATES[name]:
                cf.set_extension(key, ORIGINAL_STATES[name])
                print(f"[restore] {name} set back to {'ON' if ORIGINAL_STATES[name] else 'OFF'}")
    except Exception as e:  # never mask the real run result
        print(f"[restore] WARNING: could not restore original extension states: {e}")
    finally:
        ctx.close()


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
                # Not provisioned on this app (no row on the Dashboard list): it
                # cannot be toggled, so don't try — record it and move on.
                if not cf.exists(key):
                    dash_page.wait_for_timeout(2500)          # one settle-and-recheck, in case the list was still rendering
                if not cf.exists(key):
                    results[name] = {"not_available": True,
                                     "reason": "Not available on this app — not listed on its Extensions page (not enabled from the backend), so it was skipped, not tested."}
                    print(f"\n=== {name} ===\n  NOT AVAILABLE on this app — skipped")
                    continue
                results[name] = {}
                ORIGINAL_STATES[name] = cf.is_enabled(key)
                print(f"\n=== {name} ===  (starting state: {'ON' if ORIGINAL_STATES[name] else 'OFF'})")

                for state_label, target in [("off", False), ("on", True)]:
                    _t0 = time.perf_counter()
                    cf.set_extension(key, target)
                    dash_state = cf.is_enabled(key)
                    _t1 = time.perf_counter()

                    ctx = browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        **CONTEXT_KWARGS.get(kind, {}),
                    )
                    page = ctx.new_page()
                    open_conversation(page)
                    _t2 = time.perf_counter()
                    error = None
                    untestable = None
                    try:
                        present, sent = verifier(page, target)
                    except ProbeBlocked as exc:   # moderation blocked our test message: can't judge the extension
                        present, sent, error = None, None, None
                        untestable = str(exc)
                    except Exception as exc:      # one extension's UI failing must not abort the whole run
                        present, sent = None, None
                        error = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0][:220]}"

                    _t3 = time.perf_counter()
                    shot_path = None
                    if screenshot_dir is not None:
                        # Fixed 2026-09-17: without this, a long-history
                        # conversation (e.g. Hiking Group) can leave the just
                        # -sent evidence scrolled off the bottom of the
                        # viewport — the "sent" check still reads it
                        # correctly from the DOM, but the screenshot itself
                        # shows stale old messages instead of real proof.
                        # Fixed 2026-09-19: `.first` matched a non-scrolling wrapper, and
                        # poll / document / whiteboard cards grow after render, so one
                        # scroll left the newest bubble below the fold. Scroll every
                        # scrollable list element, let media settle, then scroll again
                        # with the newest bubble pinned to the bottom edge.
                        scroll_js = """() => {
                            document.querySelectorAll('[class*="cometchat-message-list"], [class*="message-list"]').forEach(el => {
                                if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
                            });
                            const b = document.querySelectorAll('.cometchat-message-bubble');
                            if (b.length) b[b.length - 1].scrollIntoView({block: 'end'});
                        }"""
                        # Stop as soon as the list height stops changing (cards/images done growing).
                        height_js = "() => Math.max(0, ...Array.from(document.querySelectorAll('[class*=\"message-list\"]')).map(e => e.scrollHeight))"
                        prev_h = -1
                        for _ in range(6):
                            page.evaluate(scroll_js)
                            page.wait_for_timeout(350)
                            h = page.evaluate(height_js)
                            if h == prev_h:
                                break
                            prev_h = h
                        shot_path = screenshot_dir / f"{name.replace(' ', '_')}_{state_label}.png"
                        page.screenshot(path=str(shot_path))

                    ctx.close()
                    _t4 = time.perf_counter()
                    print(f"  [time] {state_label}: toggle {_t1-_t0:.1f}s | open chat {_t2-_t1:.1f}s | check {_t3-_t2:.1f}s | screenshot+close {_t4-_t3:.1f}s", flush=True)

                    match = (dash_state == present) if (error is None and untestable is None) else False
                    # ON state must also have actually sent something wherever a send is
                    # attempted (sent is None when no send is attempted, e.g. the OFF state).
                    sent_ok = not (target and sent is False) and error is None
                    results[name][state_label] = {
                        "dashboard_enabled": dash_state,
                        "sample_app_present": present,
                        "sent": sent,
                        "match": match,
                        "sent_ok": sent_ok,
                        "screenshot": str(shot_path) if shot_path else None,
                    }
                    if error:
                        results[name][state_label]["error"] = error
                    if untestable:
                        results[name][state_label]["untestable"] = True
                        results[name][state_label]["reason"] = untestable
                    reason = LAST_REASON.pop(kind, None)
                    if reason:
                        results[name][state_label]["reason"] = reason
                    flag = "UNTESTABLE" if untestable else "ERROR" if error else ("OK" if (match and sent_ok) else ("NOT SENT" if match else "MISMATCH"))
                    sent_note = "" if sent is None else f", sent={sent}"
                    print(
                        f"  {state_label.upper():>3}  dashboard={dash_state!s:<5} "
                        f"sample_app={present!s:<5}{sent_note}  [{flag}]"
                    )

            dash_ctx.close()
        finally:
            restore_original_states(browser)
            if not KEEP_SERVER:
                stop_sample_app(started_server)
            browser.close()

    return results


def summarize(results: dict) -> tuple[int, int]:
    checks = 0
    passed = 0
    for name, states in results.items():
        if states.get("not_available"):          # skipped, neither a pass nor a fail
            continue
        for state_label, r in states.items():
            if r.get("untestable"):
                continue
            checks += 1
            if r["match"] and r.get("sent_ok", True):
                passed += 1
    return passed, checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated extension names to run (default: all)")
    parser.add_argument("--keep-server", action="store_true", help="leave the sample app dev server running after")
    parser.add_argument("--app-id", help="switch to a different app (overrides CC_SAMPLE_APP_ID)")
    parser.add_argument("--region", help="region for --app-id (overrides CC_SAMPLE_APP_REGION, default 'eu')")
    parser.add_argument("--auth-key", help="Auth Key for --app-id (overrides CC_SAMPLE_APP_AUTH_KEY) — "
                         "required whenever --app-id differs from the EU default")
    parser.add_argument("--target-conversation", help="conversation name to run checks in "
                         "(overrides CC_TARGET_CONVERSATION, default 'Hiking Group') — must exist in --app-id's app")
    args = parser.parse_args()

    global KEEP_SERVER, APP_ID, REGION, AUTH_KEY, TARGET_CONVERSATION
    KEEP_SERVER = args.keep_server
    if args.app_id:
        APP_ID = args.app_id
    if args.region:
        REGION = args.region
    if args.auth_key:
        AUTH_KEY = args.auth_key
    if args.target_conversation:
        TARGET_CONVERSATION = args.target_conversation

    only = [s.strip() for s in args.only.split(",")] if args.only else None

    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"

    t0 = time.time()
    results = run(only=only, screenshot_dir=screenshot_dir)
    elapsed = time.time() - t0

    passed, checks = summarize(results)
    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "passed": passed, "checks": checks, "elapsed_s": round(elapsed, 1), "original_states": ORIGINAL_STATES}, f, indent=2)

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
