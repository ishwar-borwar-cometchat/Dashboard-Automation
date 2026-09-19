#!/usr/bin/env python3
"""User Roles — change a role's permission on the Dashboard, check it on the Sample App.

For every permission it does the same thing, on ANY app:
    1. set the permission to DENY on the role's page and save it,
    2. in the Sample App (UI Kit + SDK), logged in as a user who has that role,
       try the action and check the API REJECTS it,
    3. set the permission back to ALLOW and check the same action now WORKS.
Both states get a screenshot of the Sample App and the raw API result.

Setup / cleanup (all names carry the e2e_ prefix; nothing pre-existing is touched):
    - creates a test role (or, with --role default, tests the Default Role and
      restores every permission it changed),
    - creates a sender and a receiver user, BOTH on that role (permissions only
      apply when both users are on the role being tested),
    - deletes the test users and role at the end, even after a crash.

The Dashboard says these permissions "are only enforced at the API level", so the
Sample App does not hide buttons — the check is that the API call the app makes is
rejected (deny) or accepted (allow).

Usage
    python3 modules/general/user_and_groups/user_roles/verify_user_roles.py \
        --app-id <id> --region <eu|us|in> --auth-key <key> [--only "User Listing,Group Creation"] [--role default]

Nothing here is specific to one app. --auth-key is used only in memory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys
import time
import uuid
from typing import Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import Page, sync_playwright  # noqa: E402

# Reuse the Sample App start/stop + app-config switching from the Extensions script.
_VE_PATH = REPO_ROOT / "modules/products/chat_and_messaging/Feature ( Extensions)/verify_extensions.py"
_spec = importlib.util.spec_from_file_location("verify_extensions", _VE_PATH)
ve = importlib.util.module_from_spec(_spec)
sys.argv, _argv = ["verify_extensions"], sys.argv
_spec.loader.exec_module(ve)
sys.argv = _argv

REPORTS = REPO_ROOT / "reports" / "user_roles_verification"
REPORTS.mkdir(parents=True, exist_ok=True)
PREFIX = "e2e"

# ---------------------------------------------------------------------------
# What to check. Each action runs INSIDE the Sample App page as the logged-in
# test user, through the same CometChat SDK the UI Kit uses. `a` = {receiver,...}.
# Adding a permission = adding one entry here; nothing else changes.
# ---------------------------------------------------------------------------
_WRAP = """async (a) => {
  try { %s }
  catch (e) { return {ok:false, code:(e&&e.code)||null, message:String((e&&e.message)||e).slice(0,200)}; }
}"""

def _act(body: str) -> str:
    return _WRAP % body

# ---------------------------------------------------------------------------
# Checks that run on the DASHBOARD (for permissions the Sample App has no screen for).
# Each takes the RolesDashboard `dash` and the args dict and returns the same kind of
# result dict the Sample App actions return ({ok, ...}).
# ---------------------------------------------------------------------------
def _wait_user_page(pg, uid: str) -> None:
    """The user detail page is loaded when the user's own ID is on screen and the spinner is gone."""
    pg.get_by_text(uid, exact=False).first.wait_for(timeout=30_000)
    try:
        pg.wait_for_function("() => !document.querySelector('.ant-spin-spinning, [class*=spinner i], [class*=loading i]')",
                             timeout=10_000)
    except Exception:
        pass
    pg.wait_for_timeout(500)


def dashboard_edit_user_name(dash, args: dict) -> dict:
    """Dashboard > Users > <sender> > Edit: change the name, save, reload, read the name back."""
    pg, uid, new_name = dash.page, args["sender"], f"E2E dashboard edit {args['stamp']}"
    pg.goto(dash._url(f"users/user/{uid}"), wait_until="domcontentloaded")
    _wait_user_page(pg, uid)
    pg.get_by_role("button", name=re.compile(r"^\s*edit\s*$", re.I)).first.click()
    inp = pg.locator("input:visible").first
    inp.wait_for(timeout=10_000)
    inp.fill(new_name)
    pg.get_by_role("button", name=re.compile(r"save|update|confirm", re.I)).first.click()
    pg.wait_for_timeout(2_500)
    toasts = [t.strip() for t in pg.locator(".ant-message-notice, .ant-notification-notice").all_inner_texts() if t.strip()]
    pg.reload(wait_until="domcontentloaded")
    _wait_user_page(pg, uid)
    shown = new_name in pg.locator("body").inner_text()
    res = {"ok": shown, "name_after_reload": new_name if shown else "(unchanged)"}
    if toasts:
        res["dashboard_message"] = " / ".join(toasts)[:160]
    return res


def dashboard_restore_user_name(dash, args: dict) -> None:
    pg, uid = dash.page, args["sender"]
    try:
        pg.goto(dash._url(f"users/user/{uid}"), wait_until="domcontentloaded")
        _wait_user_page(pg, uid)
        if f"E2E dashboard edit {args['stamp']}" not in pg.locator("body").inner_text():
            return
        pg.get_by_role("button", name=re.compile(r"^\s*edit\s*$", re.I)).first.click()
        pg.locator("input:visible").first.wait_for(timeout=10_000)
        pg.locator("input:visible").first.fill(uid)
        pg.get_by_role("button", name=re.compile(r"save|update|confirm", re.I)).first.click()
        pg.wait_for_timeout(2_000)
    except Exception:
        pass


def dashboard_add_friend(dash, user_uid: str, friend_uid: str) -> None:
    """Dashboard > Users > <user> > Friends > Add Friends > <friend> > Add Friend."""
    pg = dash.page
    pg.goto(dash._url(f"users/user/{user_uid}"), wait_until="domcontentloaded")
    _wait_user_page(pg, user_uid)
    pg.get_by_text("Friends", exact=True).first.click()
    pg.wait_for_timeout(1_500)
    pg.get_by_role("button", name=re.compile(r"add friends?", re.I)).first.click()
    dlg = pg.locator(".ant-modal:visible, .ant-drawer-content:visible").first
    dlg.wait_for(timeout=10_000)
    dlg.locator("input:visible").first.fill(friend_uid)
    pg.wait_for_timeout(1_500)
    # wait for the search to narrow to the wanted user, then click the Add Friend button in THAT user's row
    who = dlg.get_by_text(friend_uid, exact=True).first
    who.wait_for(timeout=15_000)
    pg.wait_for_timeout(500)
    who.locator("xpath=ancestor::*[.//button][1]").get_by_role("button", name=re.compile(r"add friend", re.I)).first.click(timeout=10_000)
    pg.wait_for_timeout(2_000)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)


PERMISSIONS = [
    {"name": "User Listing", "shows": "Sample App > Users tab, opened fresh after the permission change. Deny: the app's error screen. Allow: the user list.", "screen": "users", "section": "Users", "what": "list users",
     "js": _act("const r = await new CometChat.UsersRequestBuilder().setLimit(5).build().fetchNext(); return {ok:true, count:r.length};")},
    {"name": "User Details Access", "shows": 'Sample App > the chat with the receiver, opened from the Users tab. The app shows the same chat either way (it already has the user loaded), so the deny/allow difference is only in the API answer printed in the bar on top.', "screen": "chat", "section": "Users", "what": "open another user's details",
     "js": _act("const u = await CometChat.getUser(a.receiver); return {ok:!!u, uid:u&&u.getUid()};")},
    {"name": "Block User", "shows": "Sample App > the chat with the receiver. Allow: the app shows 'Can't send a message to blocked user. Click to unblock'. Deny: no block happened, so the chat looks normal.", "screen": "chat", "section": "Users", "what": "block a user",
     "js": _act("const v = await CometChat.blockUsers([a.receiver]); "
                "const raw = JSON.stringify(v); const e = v && v[a.receiver]; "
                "const ok = e === 'success' || e === true || (e && (e.success === true || /success/i.test(JSON.stringify(e)))); "
                "return {ok: !!ok, result: raw};"),
     # undone AFTER the screenshot so the screenshot shows the blocked state; always runs
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.receiver]); } catch (e) {} }"},
    {"name": "Blocked User Listing", "screen": "chat", "section": "Users", "what": "list the users you have blocked",
     "shows": "Sample App > the chat with the receiver, who is blocked ('Can't send a message to blocked user' bar). The Sample App has no blocked-users list screen, so the listing result itself is shown only in the bar on top (on allow: how many blocked users came back and that the receiver is among them).",
     "pre": "async (a) => { try { await CometChat.blockUsers([a.receiver]); } catch (e) {} }",
     "js": _act("const r = await new CometChat.BlockedUsersRequestBuilder().setLimit(10).build().fetchNext(); "
                "const has = r.some(u => u.getUid() === a.receiver); return {ok: has, count: r.length, contains_receiver: has};"),
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.receiver]); } catch (e) {} }"},
    {"name": "Unblock User", "screen": "chat", "section": "Users", "what": "unblock a blocked user",
     "shows": "Sample App > the chat with the receiver after the unblock attempt. Deny: the receiver is still blocked, so the app still shows 'Can't send a message to blocked user. Click to unblock'. Allow: that bar is gone and the chat is normal.",
     "pre": "async (a) => { try { await CometChat.blockUsers([a.receiver]); } catch (e) {} }",
     "js": _act("const v = await CometChat.unblockUsers([a.receiver]); const e = v && v[a.receiver]; "
                "const ok = e === 'success' || e === true || (e && (e.success === true || /success/i.test(JSON.stringify(e)))); "
                "return {ok: !!ok, result: JSON.stringify(v)};"),
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.receiver]); } catch (e) {} }"},
    {"name": "Edit User Profile", "screen": "chat", "section": "Users", "what": "change the logged-in user's own name",
     "shows": "Sample App > the chat with the receiver. The Sample App has no profile-edit screen, so the result is the API answer printed in the bar on top. Allow: the name changes. Deny: the API returns no error, but the name is NOT changed (it comes back as the old name). The name is set back afterwards.",
     "js": _act("const me = await CometChat.getLoggedinUser(); const u = new CometChat.User(me.getUid()); "
                "u.setName('E2E edited ' + a.stamp); const r = await CometChat.updateCurrentUserDetails(u); "
                "return {ok: r.getName() === 'E2E edited ' + a.stamp, name: r.getName()};"),
     "cleanup": "async (a) => { try { const me = await CometChat.getLoggedinUser(); const u = new CometChat.User(me.getUid()); u.setName(me.getUid()); await CometChat.updateCurrentUserDetails(u); } catch (e) {} }"},
    {"name": "Edit User Profile (Dashboard)", "via": "dashboard", "screen": "dashboard", "section": "Users",
     "what": "edit a user's name from the Dashboard's Users page",
     "permission": "Edit User Profile",
     "shows": "Dashboard > Users. Deny: the test user's detail page after Save and a reload; the Name field still shows the old name. Allow: after Save the Dashboard goes back to the Users list, and the test user's row shows the new name.",
     "dash_action": dashboard_edit_user_name, "dash_cleanup": dashboard_restore_user_name},
    # ---- modes (2, 5) : 'friends' only, with and without a friend link --------------------------------
    {"name": "User Listing Mode", "screen": "users", "section": "Users", "needs_b": True,
     "what": "list users when the mode is 'friends only'",
     "labels": {"deny": "MODE = friends, not friends", "allow": "MODE = friends, receiver added as a friend"},
     "shows": "Sample App > Users tab. First screenshot: mode 'friends' and the sender has no friends. Second: the receiver has been added as the sender's friend on the Dashboard (Users > user > Friends). The bar says whether the receiver was in the list the API returned.",
     "setting": ("User Listing Mode", "mode", "friends"), "restore": ("User Listing Mode", "mode", "all"),
     "target": {"deny": "receiver", "allow": "receiver"}, "friend_on_allow": True,
     "js": _act("const r = await new CometChat.UsersRequestBuilder().setLimit(30).build().fetchNext(); "
                "const has = r.some(u => u.getUid() === a.target); return {ok: has, count: r.length, contains_target: has};")},
    {"name": "User Details Mode", "screen": "chat", "section": "Users", "needs_b": True,
     "what": "open a user's details when the mode is 'friends only'",
     "labels": {"deny": "MODE = friends, not friends", "allow": "MODE = friends, user added as a friend"},
     "shows": "Sample App > the chat with the third test user. First screenshot: mode 'friends' and they are not friends. Second: the third user was added as the sender's friend on the Dashboard. The bar is the API's answer to 'get this user's details'.",
     "setting": ("User Details Mode", "mode", "friends"), "restore": ("User Details Mode", "mode", "all"),
     "target": {"deny": "third", "allow": "third"}, "friend_on_allow": True,
     "js": _act("const u = await CometChat.getUser(a.target); return {ok: !!u, uid: u && u.getUid()};")},
    # ---- role filters (3, 6, 8, 10, 12): filter = [Role B]; the sender is on role A -----------------------
    {"name": "User Details Role Filter", "screen": "chat", "section": "Users", "needs_b": True,
     "what": "open a user's details when the filter names a second role (B)",
     "labels": {"deny": "FILTER = role B, user on role A", "allow": "FILTER = role B, user on role B"},
     "shows": "Sample App > the chat with the user being looked up. The filter names role B; the sender is on role A. The bar is the API's answer to 'get this user's details'.",
     "setting": ("User Details Role Filter", "filter"), "restore": ("User Details Role Filter", "filter", []),
     "target": {"deny": "receiver", "allow": "third"},
     "js": _act("const u = await CometChat.getUser(a.target); return {ok: !!u, uid: u && u.getUid()};")},
    {"name": "Block User Role Filter", "screen": "chat", "section": "Users", "needs_b": True, "permission_row": "Block user Role Filter",
     "what": "block a user when the filter names a second role (B)",
     "labels": {"deny": "FILTER = role B, blocking a user on role A", "allow": "FILTER = role B, blocking a user on role B"},
     "shows": "Sample App > the chat with the user being blocked. If the block worked the app shows 'Can't send a message to blocked user'. The bar is the API's answer.",
     "setting": ("Block user Role Filter", "filter"), "restore": ("Block user Role Filter", "filter", []),
     "target": {"deny": "receiver", "allow": "third"},
     "js": _act("const v = await CometChat.blockUsers([a.target]); const e = v && v[a.target]; "
                "const ok = e === 'success' || e === true || (e && (e.success === true || /success/i.test(JSON.stringify(e)))); "
                "return {ok: !!ok, result: JSON.stringify(v)};"),
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.target]); } catch (e) {} }"},
    {"name": "Blocked User Listing Role Filter", "screen": "chat", "section": "Users", "needs_b": True, "permission_row": "Blocked User Listing Role Filter",
     "what": "list blocked users when the filter names a second role (B)",
     "labels": {"deny": "FILTER = role B, is the blocked role-A user listed?", "allow": "FILTER = role B, is the blocked role-B user listed?"},
     "shows": "Sample App > the chat with the blocked user (the app shows 'Can't send a message to blocked user'). Both users are blocked first; the bar says whether the one being checked came back in the blocked-users list.",
     "setting": ("Blocked User Listing Role Filter", "filter"), "restore": ("Blocked User Listing Role Filter", "filter", []),
     "target": {"deny": "receiver", "allow": "third"},
     "pre": "async (a) => { try { await CometChat.blockUsers([a.receiver, a.third]); } catch (e) {} }",
     "js": _act("const r = await new CometChat.BlockedUsersRequestBuilder().setLimit(30).build().fetchNext(); "
                "const has = r.some(u => u.getUid() === a.target); return {ok: has, count: r.length, contains_target: has};"),
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.receiver, a.third]); } catch (e) {} }"},
    {"name": "Unblock User Role Filter", "screen": "chat", "section": "Users", "needs_b": True, "permission_row": "Unblock User Role Filter",
     "what": "unblock a user when the filter names a second role (B)",
     "labels": {"deny": "FILTER = role B, unblocking a user on role A", "allow": "FILTER = role B, unblocking a user on role B"},
     "shows": "Sample App > the chat with the user being unblocked. Both users are blocked first. If the unblock worked the 'Can't send a message to blocked user' bar is gone. The bar on top is the API's answer.",
     "setting": ("Unblock User Role Filter", "filter"), "restore": ("Unblock User Role Filter", "filter", []),
     "target": {"deny": "receiver", "allow": "third"},
     "pre": "async (a) => { try { await CometChat.blockUsers([a.receiver, a.third]); } catch (e) {} }",
     "js": _act("const v = await CometChat.unblockUsers([a.target]); const e = v && v[a.target]; "
                "const ok = e === 'success' || e === true || (e && (e.success === true || /success/i.test(JSON.stringify(e)))); "
                "return {ok: !!ok, result: JSON.stringify(v)};"),
     "cleanup": "async (a) => { try { await CometChat.unblockUsers([a.receiver, a.third]); } catch (e) {} }"},
    # NOTE: kept LAST in this group — its filter is the one that sometimes fails to clear, and it hides users from the list
    {"name": "User Listing Role Filter", "screen": "users", "section": "Users", "needs_b": True,
     "what": "list users when the filter names a second role (B)",
     "labels": {"deny": "FILTER = role B, looking for a user on role A", "allow": "FILTER = role B, looking for a user on role B"},
     "shows": "Sample App > Users tab. The filter names role B; the sender is on role A. First screenshot: is a role-A user in the list? Second: is a role-B user in the list? With the filter set, the list should hold only role-B users. The bar says what the API returned.",
     "setting": ("User Listing Role Filter", "filter"), "restore": ("User Listing Role Filter", "filter", []),
     "target": {"deny": "receiver", "allow": "third"},
     "js": _act("const r = await new CometChat.UsersRequestBuilder().setLimit(30).build().fetchNext(); "
                "const has = r.some(u => u.getUid() === a.target); return {ok: has, count: r.length, contains_target: has};")},
    {"name": "Message Sending", "screen": "chat", "section": "Messages", "what": "send a text message",
     "js": _act("const m = new CometChat.TextMessage(a.receiver, 'Role check ' + a.stamp, CometChat.RECEIVER_TYPE.USER); "
                "const s = await CometChat.sendMessage(m); return {ok:!!s.getId(), id:s.getId()};")},
    {"name": "Message Listing", "screen": "chat", "section": "Messages", "what": "read a conversation's messages",
     "js": _act("const r = await new CometChat.MessagesRequestBuilder().setUID(a.receiver).setLimit(5).build().fetchPrevious(); return {ok:true, count:r.length};")},
    {"name": "Reaction Management", "screen": "chat", "section": "Message Reactions", "what": "add a reaction to a message",
     "js": _act("const m = new CometChat.TextMessage(a.receiver, 'React target ' + a.stamp, CometChat.RECEIVER_TYPE.USER); "
                "const s = await CometChat.sendMessage(m); await CometChat.addReaction(s.getId(), '\U0001F44D'); "
                "try { await CometChat.removeReaction(s.getId(), '\U0001F44D'); } catch (x) {} return {ok:true, id:s.getId()};")},
    {"name": "List Conversation", "screen": "chats", "section": "Conversations", "what": "list conversations",
     "js": _act("const r = await new CometChat.ConversationsRequestBuilder().setLimit(5).build().fetchNext(); return {ok:true, count:r.length};")},
    {"name": "Group Listing", "screen": "groups", "section": "Groups", "what": "list groups",
     "js": _act("const r = await new CometChat.GroupsRequestBuilder().setLimit(5).build().fetchNext(); return {ok:true, count:r.length};")},
    {"name": "Group Creation", "screen": "groups", "section": "Groups", "what": "create a group",
     "js": _act("const g = new CometChat.Group(a.guid, 'E2E role check', CometChat.GROUP_TYPE.PUBLIC); "
                "const r = await CometChat.createGroup(g); return {ok:true, guid:r.getGuid()};"),
     "cleanup": "async (a) => { try { await CometChat.deleteGroup(a.guid); } catch (e) {} }"},
]


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Dashboard side
# ---------------------------------------------------------------------------
class RolesDashboard:
    def __init__(self, page: Page, app_id: str, base_url: str):
        self.page, self.app_id, self.base = page, app_id, base_url

    def _url(self, path: str) -> str:
        return f"{self.base}/app/{self.app_id}/{path}"

    def open_list(self) -> None:
        self.page.goto(self._url("roles"), wait_until="domcontentloaded")
        self.page.locator("tr.ant-table-row").first.wait_for(timeout=30_000)

    def has_role(self, role_id: str) -> bool:
        return self.page.locator(f'tr.ant-table-row[data-row-key="{role_id}"]').count() > 0

    def create_role(self, role_id: str, name: str) -> None:
        self.open_list()
        self.page.locator("header").get_by_role("button", name="Add Role").click()
        self.page.locator("#role").fill(role_id)
        self.page.locator("#name").fill(name)
        self.page.locator("#description").fill("Created by the automated User Roles check — safe to delete")
        self.page.get_by_role("button", name="Save").click()
        self.page.locator(f'tr.ant-table-row[data-row-key="{role_id}"]').wait_for(timeout=20_000)

    def delete_role(self, role_id: str) -> None:
        self.open_list()
        row = self.page.locator(f'tr.ant-table-row[data-row-key="{role_id}"]')
        if row.count() == 0:
            return
        row.locator("button[aria-label^='Delete']").first.click()
        dlg = self.page.locator(".ant-modal, .ant-popconfirm, [role=dialog]").first
        dlg.wait_for(timeout=8_000)
        btn = dlg.get_by_role("button", name=re.compile(r"^(delete|ok|yes|confirm)$", re.I))
        (btn.first if btn.count() else dlg.locator("button").last).click()
        self.page.wait_for_timeout(1500)

    # -- permissions -----------------------------------------------------
    def open_permissions_edit(self, role_id: str) -> None:
        self.page.goto(self._url(f"roles/{role_id}/edit"), wait_until="domcontentloaded")
        self.page.get_by_text("User Listing", exact=True).first.wait_for(timeout=30_000)

    def _row(self, perm: str):
        label = self.page.get_by_text(perm, exact=True).first
        return label.locator("xpath=ancestor::*[.//*[contains(@class,'ant-select')]][1]")

    def read_permission(self, perm: str) -> Optional[str]:
        """Current allow/deny of a permission — works in view and edit mode."""
        return self.page.evaluate(
            """(perm) => {
                const label = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === perm);
                let n = label;
                for (let i = 0; i < 8 && n; i++) {
                    n = n.parentElement; if (!n) break;
                    const leaf = [...n.querySelectorAll('*')].find(e => e.children.length === 0 && /^(allow|deny)$/.test(e.textContent.trim()));
                    if (leaf) return leaf.textContent.trim();
                }
                return null;
            }""", perm)

    def set_permission(self, role_id: str, perm: str, value: str, attempts: int = 3) -> None:
        """Set one permission and save it. The Dashboard page occasionally drops a click, so a
        failed attempt is retried from a fresh page load before it is reported as an error."""
        last = None
        for _ in range(attempts):
            try:
                self._set_permission_once(role_id, perm, value)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last

    def _set_permission_once(self, role_id: str, perm: str, value: str) -> None:
        """One attempt: choose the value, Save Changes, confirm the dialog, wait for the server."""
        self.open_permissions_edit(role_id)
        self.page.get_by_role("button", name="Edit").nth(1).click()
        self.page.get_by_role("button", name="Save Changes").wait_for(timeout=10_000)
        row = self._row(perm)
        row.scroll_into_view_if_needed()
        opts = self.page.locator(".ant-select-item-option:visible")
        for _attempt in range(3):
            row.locator(".ant-select").first.click()
            opts.first.wait_for(timeout=5_000)
            self.page.wait_for_timeout(400)   # the list is animating open; a click before this is swallowed
            opts.filter(has_text=re.compile(rf"^{value}$")).first.click()
            self.page.wait_for_timeout(300)
            if self.read_permission(perm) == value:
                break
        else:
            raise RuntimeError(f"could not select '{value}' for {perm}")
        self.page.get_by_role("button", name="Save Changes").click()
        dlg = self.page.locator(".ant-modal:visible").first
        dlg.wait_for(timeout=8_000)
        with self.page.expect_response(
            lambda r: r.request.method == "PUT" and f"/roles/{role_id}/permissions" in r.url, timeout=20_000
        ) as resp:
            dlg.get_by_role("button", name="Save", exact=True).click()
        if resp.value.status >= 300:
            raise RuntimeError(f"saving {perm}={value} failed: HTTP {resp.value.status}")
        self.page.get_by_role("button", name="Save Changes").wait_for(state="detached", timeout=15_000)

    def row_screenshot(self, perm: str) -> Optional[bytes]:
        """A real screenshot of the permission's row (name, description, value) on the role page.
        Waits for the "Permissions updated" toast to go away first (it sits on top of the value),
        and leaves the floating Support button out of the crop."""
        try:
            # The "Permissions updated successfully" toast stays on screen and covers the value:
            # hide the toast's own container (the nearest fixed/absolute ancestor of its text).
            self.page.evaluate("""() => {
                for (const e of document.querySelectorAll('*')) {
                    if (e.children.length === 0 && /permissions? updated|updated successfully/i.test(e.textContent || '')) {
                        let n = e;
                        for (let i = 0; i < 8 && n.parentElement; i++) {
                            n = n.parentElement;
                            const pos = getComputedStyle(n).position;
                            if (pos === 'fixed' || pos === 'absolute') { n.style.display = 'none'; break; }
                        }
                    }
                }
                document.querySelectorAll('.ant-message, .ant-notification').forEach(n => n.style.display = 'none');
            }""")
            self.page.wait_for_timeout(250)
            label = self.page.get_by_text(perm, exact=True).first
            label.scroll_into_view_if_needed()
            self.page.wait_for_timeout(400)
            b = label.bounding_box()
            if not b:
                return None
            return self.page.screenshot(clip={"x": 250, "y": max(0, b["y"] - 42), "width": 1130, "height": b["height"] + 92})
        except Exception:
            return None

    # -- modes and role filters (settings that are not plain allow/deny) --------
    def row_text(self, perm: str) -> str:
        """Text of a setting's row, in view or edit mode."""
        return self.page.evaluate(
            """(perm) => {
                const l = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === perm);
                if (!l) return '';
                const r = l.closest('tr, [role=row]') || l.parentElement.parentElement;
                return r.innerText.replace(/\\s+/g, ' ');
            }""", perm)

    def _change_and_save(self, role_id: str, change) -> None:
        """Open the permissions in edit mode, run change(page), Save Changes, confirm, wait for the server."""
        self.open_permissions_edit(role_id)
        self.page.get_by_role("button", name="Edit").nth(1).click()
        self.page.get_by_role("button", name="Save Changes").wait_for(timeout=10_000)
        if change() is False:                     # already in the wanted state: nothing to save
            self.page.get_by_role("button", name="Cancel").first.click()
            self.page.wait_for_timeout(300)
            return
        self.page.get_by_role("button", name="Save Changes").click()
        dlg = self.page.locator(".ant-modal:visible").first
        dlg.wait_for(timeout=8_000)
        with self.page.expect_response(
            lambda r: r.request.method == "PUT" and f"/roles/{role_id}/permissions" in r.url, timeout=10_000
        ) as resp:
            dlg.get_by_role("button", name="Save", exact=True).click()
        if resp.value.status >= 300:
            raise RuntimeError(f"saving failed: HTTP {resp.value.status}")
        self.page.get_by_role("button", name="Save Changes").wait_for(state="detached", timeout=15_000)

    def _selected(self, perm: str) -> list:
        """What the row's dropdown currently shows selected (one item for a mode, one per role for a filter)."""
        return [t.strip() for t in self._row(perm).locator(".ant-select-selection-item").all_inner_texts() if t.strip()]

    def _pick(self, perm: str, option_text: str) -> bool:
        """Choose an option in a row's dropdown and check it really took. Returns True if it changed anything."""
        if option_text in self._selected(perm):
            return False
        for _ in range(3):
            row = self._row(perm)
            row.scroll_into_view_if_needed()
            opts = self.page.locator(".ant-select-item-option:visible")
            row.locator(".ant-select").first.click()
            opts.first.wait_for(timeout=5_000)
            self.page.wait_for_timeout(400)          # the list is animating open; a click before this is swallowed
            opts.filter(has_text=re.compile(rf"^{re.escape(option_text)}$")).first.click()
            self.page.wait_for_timeout(300)
            if option_text in self._selected(perm):
                return True
        raise RuntimeError(f"the dropdown for '{perm}' did not take '{option_text}'")

    def set_mode(self, role_id: str, perm: str, value: str, attempts: int = 3) -> None:
        """A mode dropdown (e.g. 'all' / 'friends')."""
        last = None
        for _ in range(attempts):
            try:
                self._change_and_save(role_id, lambda: self._pick(perm, value))
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last

    def set_role_filter(self, role_id: str, perm: str, role_names: list, attempts: int = 3) -> None:
        """A multi-select of roles. [] clears it. Skips the save if it is already in that state."""
        def change():
            row = self._row(perm)
            row.scroll_into_view_if_needed()
            before = sorted(self._selected(perm))
            for _ in range(6):                     # remove the current tags one by one
                tag_x = row.locator(".ant-select-selection-item-remove")
                if not tag_x.count():
                    break
                tag_x.first.click(force=True)
                self.page.wait_for_timeout(300)
            if row.locator(".ant-select-selection-item-remove").count():   # still there: clear with the keyboard
                row.locator(".ant-select").first.click()
                for _ in range(6):
                    self.page.keyboard.press("Backspace")
                self.page.get_by_text("Permissions", exact=True).first.click()
                self.page.wait_for_timeout(300)
            for name in role_names:
                self._pick(perm, name)
            # close the dropdown by clicking a neutral spot (Escape can throw the selection away)
            self.page.get_by_text("Permissions", exact=True).first.click()
            self.page.wait_for_timeout(300)
            after = sorted(self._selected(perm))
            if after != sorted(role_names):
                raise RuntimeError(f"role filter shows {after}, wanted {sorted(role_names)}")
            return before != after
        last = None
        for _ in range(attempts):
            try:
                self._change_and_save(role_id, change)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last

    def confirm_value(self, role_id: str, perm: str, want: str) -> Optional[str]:
        """Value the Dashboard shows after a save. The page can briefly re-render with the old value
        right after the PUT, so re-read for a moment, and only then fall back to a fresh page load."""
        for _ in range(4):
            v = self.read_permission(perm)
            if v == want:
                return v
            self.page.wait_for_timeout(600)
        return self.saved_value(role_id, perm)

    def saved_value(self, role_id: str, perm: str) -> Optional[str]:
        self.open_permissions_edit(role_id)
        return self.read_permission(perm)


# ---------------------------------------------------------------------------
# Sample App side
# ---------------------------------------------------------------------------
def login_as(page: Page, uid: str) -> None:
    page.goto(ve.SAMPLE_APP_URL, wait_until="domcontentloaded", timeout=60_000)
    box = page.get_by_placeholder("Enter your UID")
    box.wait_for(timeout=30_000)
    box.fill(uid)
    page.get_by_role("button", name=re.compile(r"login", re.I)).last.click()
    page.wait_for_selector(".cometchat-conversations, .cometchat-tab-component, [class*=cometchat-]:not([class*=login])",
                           timeout=30_000)
    page.wait_for_function("() => !document.querySelector('.cometchat-login__user-list') && !document.querySelector('input[placeholder=\"Enter your UID\"]')",
                           timeout=30_000)


def create_test_user(page: Page, uid: str, role_id: Optional[str], auth_key: str) -> dict:
    return page.evaluate(
        """async ([uid, role, key]) => {
             try { const u = new CometChat.User(uid); u.setName(uid); if (role) u.setRole(role);
                   const r = await CometChat.createUser(u, key); return {ok:true, role:r.getRole && r.getRole()}; }
             catch (e) { return {ok:false, message:String((e&&e.message)||e)}; } }""",
        [uid, role_id, auth_key])


def run_action(page: Page, spec: dict, args: dict) -> dict:
    t0 = time.perf_counter()
    res = page.evaluate(spec["js"], args)
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    return res


def show_screen(page: Page, screen: str, receiver: str) -> None:
    """Open the Sample App screen that the permission is about, freshly loaded, so the
    screenshot shows the real UI state (a list, a chat) and not whatever tab happened to be open.
      users / groups / chats -> that bottom tab (re-opened so the list is fetched again)
      chat                   -> the conversation with the receiver (found through the Users tab)"""
    def tab(name: str) -> None:
        page.get_by_text(name, exact=True).last.click()
        page.wait_for_timeout(300)

    tab("Chats")                       # leave the tab so returning to it re-fetches
    if screen == "chats":
        page.wait_for_timeout(1500)
        return
    if screen in ("users", "groups"):
        tab("Users" if screen == "users" else "Groups")
        try:
            # settled = no loading placeholders left, and either rows or an empty/error view showing
            page.wait_for_function(
                """() => !document.querySelector('[class*="shimmer"], [class*="skeleton"]')
                         && document.querySelector('.cometchat-users__list-item, .cometchat-groups__list-item, '
                                                  + '[class*="empty-state"], [class*="error-state"], [class*="empty"], [class*="error"]')""",
                timeout=10_000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        return
    # a conversation with the receiver
    tab("Users")
    box = page.locator("input[placeholder*='Search' i]").first
    try:
        box.fill(receiver)
        page.wait_for_timeout(1200)
        page.locator(".cometchat-users__list-item", has_text=receiver).first.click(timeout=6_000)
        page.locator('[contenteditable="true"]').first.wait_for(timeout=8_000)
    except Exception:
        pass                            # the screenshot still shows exactly what the app showed
    try:                                # the message list shows grey placeholders while it loads: wait them out
        page.wait_for_function("() => !document.querySelector('[class*=\"shimmer\"], [class*=\"skeleton\"]')", timeout=10_000)
    except Exception:
        pass
    page.wait_for_timeout(700)


def result_line(res: dict) -> str:
    """One honest line describing what the API really answered."""
    extras = {k: v for k, v in res.items() if k not in ("ok", "ms", "code", "message")}
    extra_txt = ", ".join(f"{k}={v}" for k, v in extras.items())
    if "name_after_reload" in res:   # a Dashboard-side edit: it is the Dashboard's result, not an API answer
        return ("Dashboard result: ALLOWED — the name changed" if res.get("ok")
                else "Dashboard result: NOT APPLIED — the Dashboard showed no error, but the name did not change") + f" ({extra_txt})"
    for key in ("contains_target", "contains_receiver"):
        if key in res:               # a list check: the call worked; the question is whether the user was in the list
            n = res.get("count")
            who = "the user" if key == "contains_target" else "the receiver"
            return (f"API result: {who} IS in the returned list" if res.get(key)
                    else f"API result: {who} is NOT in the returned list") + (f" ({n} user(s) returned)" if n is not None else "")
    if res.get("ok"):
        return "API result: ALLOWED" + (f" ({extra_txt})" if extra_txt else "")
    if res.get("code") or res.get("message"):
        return f"API result: BLOCKED — {res.get('code') or ''}: {res.get('message') or ''}"
    # no error came back, but the action did not do what allow does
    return "API result: NOT APPLIED — no error was returned, but the action did not take effect" + (f" ({extra_txt})" if extra_txt else "")


def evidence_shot(page: Page, path: pathlib.Path, title: str, res: dict, expect_ok: bool,
                  context: Optional[list] = None, row_png: Optional[bytes] = None, row_caption: str = "") -> None:
    """One picture that links the permission to the action:
         1. a context strip: the role, the permission and its value, who is logged in, who is acted on;
         2. a real screenshot of that permission's row on the Dashboard's role page;
         3. the Sample App (or Dashboard) screen with the real result bar above it.
       The bar and strip are added by compositing, never drawn over the app."""
    import base64
    app_png = page.screenshot()                       # the app exactly as it looks, nothing added
    good = bool(res.get("ok")) == expect_ok
    b64 = lambda b: base64.b64encode(b).decode()
    ctx_html = "".join(f"<div>{_h(l)}</div>" for l in (context or []))
    parts = ["<body style='margin:0;background:#fff;font-family:system-ui'>"]
    if ctx_html:
        parts.append(f"<div style='background:#1f2a44;color:#fff;font:600 14px/1.5 system-ui;padding:10px 16px;width:1440px;box-sizing:border-box'>{ctx_html}</div>")
    if row_png:
        parts.append(f"<div style='background:#eef1f7;color:#1f2a44;font:700 13px system-ui;padding:6px 16px;width:1440px;box-sizing:border-box'>"
                     f"1 &middot; Dashboard &mdash; {_h(row_caption)}</div>"
                     f"<div style='padding:8px 16px;width:1440px;box-sizing:border-box;background:#fafafa'><img style='display:block;width:1130px;border:1px solid #cfd4de' src='data:image/png;base64,{b64(row_png)}'></div>")
    parts.append(f"<div style='background:#eef1f7;color:#1f2a44;font:700 13px system-ui;padding:6px 16px;width:1440px;box-sizing:border-box'>"
                 f"{'2' if row_png else '1'} &middot; The action and its result</div>")
    parts.append(f"<div style=\"background:{'#0f7b3f' if good else '#b3261e'};color:#fff;font:600 14px/1.4 system-ui;"
                 f"padding:10px 16px;width:1440px;box-sizing:border-box\">{_h(title)} &nbsp;|&nbsp; {_h(result_line(res))}</div>")
    parts.append(f"<img style='display:block;width:1440px' src='data:image/png;base64,{b64(app_png)}'></body>")
    comp = page.context.new_page()
    try:
        comp.set_viewport_size({"width": 1440, "height": 120})
        comp.set_content("".join(parts))
        comp.wait_for_timeout(200)
        comp.screenshot(path=str(path), full_page=True)
    finally:
        comp.close()


def _h(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------
def run(only: Optional[list], role_mode: str, shot_dir: pathlib.Path) -> dict:
    specs = [p for p in PERMISSIONS if not only or p["name"] in only]
    if not specs:
        raise SystemExit(f"No permission matched --only {only!r}")
    shot_dir.mkdir(parents=True, exist_ok=True)

    tag = uuid.uuid4().hex[:5]
    use_default = role_mode == "default"
    role_id = "default" if use_default else f"{PREFIX}_role_{tag}"
    sender, receiver = f"{PREFIX}_sender_{tag}", f"{PREFIX}_receiver_{tag}"
    results: dict = {}
    original: dict = {}
    created_role = created_users = created_role_b = created_third = False
    server = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=ve.HEADLESS)
        try:
            server = ve.start_sample_app()
            dctx = browser.new_context(storage_state=ve.STORAGE_STATE, viewport={"width": 1440, "height": 1000})
            dash = RolesDashboard(dctx.new_page(), ve.APP_ID, ve.BASE_URL)

            # --- setup -----------------------------------------------------
            t0 = time.perf_counter()
            if use_default:
                dash.open_list()
                if not dash.has_role("default"):
                    raise SystemExit("Default Role not found on this app.")
                log("[setup] testing the Default Role — every permission it changes is restored afterwards")
            else:
                dash.create_role(role_id, f"E2E Role {tag}")
                created_role = True
                log(f"[setup] created role {role_id}")

            needs_b = any(sp.get("needs_b") for sp in specs)
            role_b_id, role_b_name, third = f"{PREFIX}_roleb_{tag}", f"E2E Role B {tag}", f"{PREFIX}_third_{tag}"
            if needs_b:
                dash.create_role(role_b_id, role_b_name)
                created_role_b = True
                log(f"[setup] created second role {role_b_id} ('{role_b_name}')")

            actx = browser.new_context(viewport={"width": 1440, "height": 900})
            app = actx.new_page()
            app.goto(ve.SAMPLE_APP_URL, wait_until="domcontentloaded", timeout=60_000)
            app.get_by_placeholder("Enter your UID").wait_for(timeout=30_000)
            for uid in (sender, receiver):
                r = create_test_user(app, uid, None if use_default else role_id, ve.AUTH_KEY)
                if not r.get("ok"):
                    raise SystemExit(f"Could not create test user {uid}: {r.get('message')}")
            created_users = True
            if needs_b:
                r = create_test_user(app, third, role_b_id, ve.AUTH_KEY)
                if not r.get("ok"):
                    raise SystemExit(f"Could not create test user {third}: {r.get('message')}")
                created_third = True
                log(f"[setup] third user {third} is on role B ('{role_b_name}')")
            login_as(app, sender)
            who = app.evaluate("async () => { const u = await CometChat.getLoggedinUser(); return {uid:u.getUid(), role:u.getRole()}; }")
            expected_role = "default" if use_default else role_id
            if str(who.get("role") or "default") != expected_role:
                raise SystemExit(f"Role mismatch: logged in as {who['uid']} with role {who.get('role')!r}, "
                                 f"but the role under test is {expected_role!r}. Stopping — nothing was tested.")
            log(f"[setup] sender {sender} and receiver {receiver} both on role '{expected_role}' "
                f"(logged in as {who['uid']}) — {time.perf_counter() - t0:.1f}s")

            # --- one section per permission -------------------------------
            for spec in specs:
                name = spec["name"]
                slug = re.sub(r"\W+", "_", name)
                results[name] = {"section": spec["section"], "what": spec["what"], "shows": spec.get("shows", "")}
                log(f"\n=== {name} ===  ({spec['section']}: {spec['what']})")
                args = {"sender": sender, "receiver": receiver, "stamp": tag, "guid": f"{PREFIX}_grp_{tag}_{slug[:8]}"}
                perm = spec.get("permission", name)      # the row on the role page (differs for Dashboard-side checks)
                via_dash = spec.get("via") == "dashboard"
                setting = spec.get("setting")             # a mode or role filter instead of plain allow/deny
                labels = spec.get("labels") or {}
                if labels:
                    results[name]["labels"] = labels
                args.update({"third": third, "role_b_name": role_b_name})
                try:
                    if not setting:
                        original[name] = dash.saved_value(role_id, perm)
                    for state, expect_ok in (("deny", False), ("allow", True)):
                        t1 = time.perf_counter()
                        target_key = (spec.get("target") or {}).get(state, "receiver")
                        args["target"] = args[target_key]
                        if setting:
                            row_label, kind = setting[0], setting[1]
                            if state == "deny":                       # apply the setting once, on the first state
                                if kind == "mode":
                                    dash.set_mode(role_id, row_label, setting[2])
                                else:
                                    dash.set_role_filter(role_id, row_label, [role_b_name])
                            elif spec.get("friend_on_allow"):         # second state: make the target a friend on the Dashboard
                                dashboard_add_friend(dash, sender, args["target"])
                            dash.open_permissions_edit(role_id)
                            saved = dash.row_text(row_label)
                            want = setting[2] if kind == "mode" else role_b_name
                            saved_ok = want.lower() in saved.lower()
                            saved = want if saved_ok else f"(not shown: {saved[:60]})"
                        else:
                            dash.set_permission(role_id, perm, state)
                            saved = dash.confirm_value(role_id, perm, state)
                            saved_ok = saved == state
                        row_png = dash.row_screenshot(setting[0] if setting else perm)      # the saved setting, as the Dashboard shows it
                        row_label = setting[0] if setting else perm
                        tgt_uid = args["target"]
                        role_of = {sender: role_id, receiver: role_id, third: role_b_id if needs_b else "-"}
                        ctx_lines = [
                            f"Role under test: {role_id}   |   Permission: {row_label}   =   {saved}",
                            f"Logged in to the Sample App as: {sender} (role {role_id})   |   "
                            f"Acting on: {tgt_uid} (role {role_of.get(tgt_uid, '-')})" if not via_dash else
                            f"Edited on the Dashboard: user {sender} (role {role_id})",
                        ]
                        if needs_b:
                            ctx_lines.append(f"Role B (the second role): {role_b_id} ('{role_b_name}')   |   third user {third} is on role B")
                        t2 = time.perf_counter()
                        if via_dash:
                            res = spec["dash_action"](dash, args)          # the check itself runs on the Dashboard
                            shot_page = dash.page
                        else:
                            if spec.get("pre"):
                                app.evaluate(spec["pre"], args)
                            res = run_action(app, spec, args)
                            try:
                                show_screen(app, spec["screen"], args["target"])
                            except Exception as exc:  # never lose the verdict because a screen didn't open
                                log(f"  [note] could not open the {spec['screen']} screen: {str(exc).splitlines()[0][:80]}")
                            shot_page = app
                        shot = shot_dir / f"{slug}_{state}.png"
                        evidence_shot(shot_page, shot, (f"{name}: {labels[state]}" if state in labels else f"{name} = {state}"), res, expect_ok,
                                      context=ctx_lines, row_png=row_png,
                                      row_caption=f"the role's '{row_label}' setting, read back from the Dashboard after saving")
                        if via_dash and spec.get("dash_cleanup"):
                            spec["dash_cleanup"](dash, args)
                        elif spec.get("cleanup"):
                            app.evaluate(spec["cleanup"], args)
                        t3 = time.perf_counter()
                        match = saved_ok and (bool(res.get("ok")) == expect_ok)
                        results[name][state] = {"dashboard_value": saved, "api_ok": bool(res.get("ok")),
                                                "expected_ok": expect_ok, "match": match, "result": res,
                                                "screenshot": str(shot), "target": args["target"]}
                        log(f"  [time] {state}: change+save {t2 - t1:.1f}s | {'Dashboard' if via_dash else 'Sample App'} action+screenshot {t3 - t2:.1f}s")
                        log(f"  {state.upper():5} dashboard={saved} api={'ALLOWED' if res.get('ok') else 'BLOCKED'}"
                            f"{'' if match else '  expected ' + ('ALLOWED' if expect_ok else 'BLOCKED')}  [{'OK' if match else 'MISMATCH'}]")
                except Exception as exc:  # one permission failing must not abort the run
                    results[name]["error"] = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0][:200]}"
                    try:   # what the Dashboard showed when it failed — makes the error diagnosable
                        eshot = shot_dir / f"{slug}_dashboard_error.png"
                        dash.page.screenshot(path=str(eshot))
                        results[name]["error_screenshot"] = str(eshot)
                    except Exception:
                        pass
                    log(f"  [ERROR] {results[name]['error']}")
                finally:
                    if spec.get("restore"):                    # a mode / filter must never leak into the next check
                        try:
                            rl = spec["restore"]
                            if rl[1] == "mode":
                                dash.set_mode(role_id, rl[0], rl[2])
                            else:
                                dash.set_role_filter(role_id, rl[0], rl[2])
                            log(f"  [restore] {rl[0]} set back to {rl[2] if rl[1] == 'mode' else 'no roles selected'}")
                        except Exception as exc:
                            log(f"  [restore FAILED] {spec['name']}: {exc}")
                    # never leave a permission changed on a role that isn't ours
                    try:
                        if use_default and original.get(name) in ("allow", "deny"):
                            if dash.saved_value(role_id, perm) != original[name]:
                                dash.set_permission(role_id, perm, original[name])
                                log(f"  [restore] {name} set back to {original[name]}")
                    except Exception as exc:
                        log(f"  [restore FAILED] {name}: {exc}")
        finally:
            # --- cleanup ---------------------------------------------------
            try:
                if created_users:
                    from modules.general.user_and_groups.users.users_page import UsersPage
                    dctx2 = browser.new_context(storage_state=ve.STORAGE_STATE, viewport={"width": 1440, "height": 1000})
                    up = UsersPage(dctx2.new_page(), app_id=ve.APP_ID, base_url=ve.BASE_URL)
                    for uid in (sender, receiver) + ((third,) if created_third else ()):
                        if not uid.startswith(PREFIX + "_"):
                            continue  # destructive-action guard: only ever delete our own users
                        up.open(force=True)
                        if up.search_box() is not None:
                            up.search(uid)
                        idx = up._row_index_for(uid)
                        ctl = up.row_action(idx, 2) if idx is not None and idx >= 0 else None
                        if ctl is not None:
                            ctl.click()
                            up.page.wait_for_timeout(900)
                            up.accept_confirm()
                            log(f"[cleanup] deleted user {uid}")
                        else:
                            log(f"[cleanup] could not find user {uid} to delete — remove it manually")
                if created_role:
                    dash.delete_role(role_id)
                    log(f"[cleanup] deleted role {role_id}")
                if created_role_b:
                    dash.delete_role(role_b_id)
                    log(f"[cleanup] deleted role {role_b_id}")
            except Exception as exc:
                log(f"[cleanup FAILED] {exc} — remove any '{PREFIX}_' role/users left on the app manually")
            if not ve.KEEP_SERVER:
                ve.stop_sample_app(server)
            browser.close()
    return {"role": role_id, "results": results, "original": original}


def summarize(results: dict) -> tuple[int, int]:
    passed = checks = 0
    for r in results.values():
        for state in ("deny", "allow"):
            if state in r:
                checks += 1
                passed += 1 if r[state]["match"] else 0
        if "error" in r:
            checks += 2
    return passed, checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-id", required=True)
    ap.add_argument("--region", default="eu")
    ap.add_argument("--auth-key", required=True)
    ap.add_argument("--only", help="comma-separated permission names (default: all defined)")
    ap.add_argument("--role", default="test", choices=["test", "default"],
                    help="'test' = create a disposable role (default); 'default' = test the Default Role and restore it")
    ap.add_argument("--keep-server", action="store_true")
    a = ap.parse_args()

    ve.APP_ID, ve.REGION, ve.AUTH_KEY, ve.KEEP_SERVER = a.app_id, a.region, a.auth_key, a.keep_server
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    run_id = time.strftime("%Y%m%d-%H%M%S")
    shot_dir = REPORTS / f"{run_id}-screenshots"
    t0 = time.time()
    out = run(only, a.role, shot_dir)
    elapsed = time.time() - t0
    passed, checks = summarize(out["results"])
    path = REPORTS / f"{run_id}.json"
    path.write_text(json.dumps({**out, "app_id": a.app_id, "region": a.region, "passed": passed, "checks": checks,
                                "elapsed_s": round(elapsed, 1)}, indent=2))
    print(f"\n{'=' * 50}\n{passed}/{checks} checks passed in {elapsed:.0f}s\nResults written to {path}\n"
          f"Screenshots written to {shot_dir}\n{'=' * 50}")
    if passed != checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
