"""USR_052 - USR_055 : detail/list edge cases.
USR_086 - USR_092 : rendering, loading, session, deep-link (added)."""
from __future__ import annotations

import re

import pytest

from conftest import make_uid

DETAIL_SCENARIO = "User Detail - Edge Cases"
LIST_SCENARIO = "Users List - Empty/Error"
RENDER_SCENARIO = "Users List - Rendering Edge Cases"
STATE_SCENARIO = "Users List - Loading & Session"

USERS_API = re.compile(r"user", re.I)


@pytest.mark.tc(id="USR_052", scenario=DETAIL_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify deleting last auth token",
                expected="Token removed, empty table shown, a new one can still be created")
def test_usr_052_delete_last_token(users, user_detail, seeded_user):
    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    if not users.open_user(seeded_user):
        user_detail.open_uid(seeded_user)

    while user_detail.token_row_count() > 1:
        if not user_detail.delete_token(0):
            break
        user_detail.page.wait_for_timeout(1_200)
        confirm = user_detail.page.locator(".ant-popconfirm, .ant-modal, [role=dialog]")
        if confirm.count() and confirm.first.is_visible():
            confirm.first.locator("button").last.click()
            user_detail.page.wait_for_timeout(1_500)

    if user_detail.token_row_count() == 0:
        assert user_detail.create_token(), "Could not create a token to then delete"

    assert user_detail.delete_token(0), "No delete control on the last token"
    confirm = user_detail.page.locator(".ant-popconfirm, .ant-modal, [role=dialog]")
    if confirm.count() and confirm.first.is_visible():
        confirm.first.locator("button").last.click()
        user_detail.page.wait_for_timeout(2_000)

    assert user_detail.token_row_count() == 0, "Last token was not removed"
    assert not user_detail.visible_error_banners(), (
        f"Deleting the last token produced an error: {user_detail.visible_error_banners()}"
    )
    assert user_detail.create_token_button() is not None, (
        "'+ Create Auth Token' disappeared once the last token was deleted — "
        "the user can no longer create one"
    )


@pytest.mark.tc(id="USR_053", scenario=DETAIL_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify adding same friend twice",
                expected="Error shown or duplicate prevented")
def test_usr_053_duplicate_friend(users, user_detail, seeded_user):
    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    if not users.open_user(seeded_user):
        user_detail.open_uid(seeded_user)
    if not user_detail.switch_tab("Friends"):
        pytest.skip("No Friends tab on the user detail page")

    if not user_detail.open_add_dialog("Friends"):
        pytest.skip("Add Friends dialog did not open")

    option = user_detail.page.locator(".ant-modal tbody tr, [role=dialog] tbody tr")
    if not option.count():
        user_detail.close_dialog()
        pytest.skip("No candidate users available to add as a friend")

    label = option.first.inner_text().strip()[:40]
    option.first.click()
    confirm = user_detail.page.get_by_role("button", name=re.compile(r"add|save|ok", re.I))
    if confirm.count():
        confirm.last.click()
    user_detail.page.wait_for_timeout(2_500)
    after_first = user_detail.list_row_count()

    if not user_detail.open_add_dialog("Friends"):
        pytest.skip("Could not reopen the Add Friends dialog")
    again = user_detail.page.locator(".ant-modal tbody tr, [role=dialog] tbody tr").filter(
        has_text=label.split("\n")[0]
    )
    if not again.count():
        user_detail.close_dialog()
        return  # already-friends users correctly excluded from the picker

    again.first.click()
    confirm = user_detail.page.get_by_role("button", name=re.compile(r"add|save|ok", re.I))
    if confirm.count():
        confirm.last.click()
    user_detail.page.wait_for_timeout(2_500)

    assert user_detail.list_row_count() == after_first, (
        "The same user was added as a friend twice — the friend list now contains a duplicate"
    )


@pytest.mark.tc(id="USR_054", scenario=LIST_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify empty users list for new app",
                expected="Empty state with an option to add the first user")
def test_usr_054_empty_list(users):
    if users.row_count() > 0:
        pytest.skip(
            "This app already has users, so the empty state cannot be observed. "
            "Point CC_APP_ID at a freshly created app to run this case."
        )

    text = users.empty_state_text() or users.main_text()
    assert re.search(r"no .*(user|data)|empty|get started", text, re.I), (
        f"Users list is empty but shows no empty-state message. Reads: {text[:200]!r}"
    )
    assert users.add_user_button() is not None, (
        "Empty state offers no way to add the first user"
    )


@pytest.mark.tc(id="USR_055", scenario=LIST_SCENARIO, sentiment="Negative", priority="High",
                title="Verify error state when API fails",
                expected="Error state displayed, page does not crash")
def test_usr_055_api_failure(raw_users, app_config):
    page = raw_users.page

    seen = []
    page.on("request", lambda r: seen.append(r.url)
            if r.resource_type in ("xhr", "fetch") else None)
    raw_users.open()
    endpoints = [u for u in seen if USERS_API.search(u)]
    if not endpoints:
        pytest.skip("Could not identify a users XHR endpoint to fault-inject")

    page.route(
        lambda url: bool(USERS_API.search(url)),
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"error":{"message":"Injected failure for USR_055"}}',
        ),
    )
    raw_users.open()

    body = page.locator("body").inner_text()
    assert len(body.strip()) > 50, "The entire page went blank when the users API returned 500"

    surfaced = raw_users.visible_error_banners() or re.search(
        r"error|failed|unable|try again|something went wrong|retry", body, re.I
    )
    assert surfaced, (
        "Users API returned 500 but the page surfaces no error at all — the failure is silent"
    )


# ---------------------------------------------------------------------------
# Added during review
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_086", scenario=RENDER_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify broken avatar URL falls back gracefully",
                expected="Placeholder/initials avatar, no broken-image icon")
def test_usr_086_broken_avatar(users, user_factory):
    uid = user_factory(
        name="E2E Broken Avatar",
        avatar="https://invalid.invalid/does-not-exist.png",
    )
    users.open()
    if users.search_box() is not None:
        users.search(uid)
    idx = users._row_index_for(uid)
    assert idx >= 0, "Seeded user with a broken avatar was not created"

    assert users.row_has_avatar(idx), "Row renders no avatar element at all"

    broken = users.rows().nth(idx).evaluate(
        """el => [...el.querySelectorAll('img')]
                 .filter(i => i.complete && i.naturalWidth === 0).length"""
    )
    assert broken == 0, (
        f"{broken} image(s) failed to load with no fallback — a broken-image icon is shown"
    )


@pytest.mark.tc(id="USR_087", scenario=RENDER_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify very long display name does not break table layout",
                expected="Name truncates with ellipsis, columns stay aligned")
def test_usr_087_long_name(users, user_factory):
    uid = user_factory(name="E2E " + ("VeryLongName" * 20))
    users.open()
    if users.search_box() is not None:
        users.search(uid)
    idx = users._row_index_for(uid)
    assert idx >= 0, "Seeded user with a long name was not created"

    overflow = users.rows().nth(idx).evaluate(
        """el => {
             const table = el.closest('table') || el.parentElement;
             const rw = el.getBoundingClientRect().width;
             const tw = table.getBoundingClientRect().width;
             return Math.round(rw - tw);
           }"""
    )
    assert overflow <= 2, (
        f"A long display name pushed the row {overflow}px wider than the table — layout breaks"
    )


@pytest.mark.tc(id="USR_088", scenario=RENDER_SCENARIO, sentiment="Negative", priority="Low",
                title="Verify large Metadata JSON renders without breaking the detail page",
                expected="Metadata renders readably, no overflow or freeze")
def test_usr_088_large_metadata(users, user_detail, user_factory):
    blob = '{"items":[' + ",".join(f'{{"i":{i},"v":"value-{i}"}}' for i in range(120)) + "]}"
    uid = user_factory(name="E2E Big Metadata", metadata=blob)

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    if not users.open_user(uid):
        user_detail.open_uid(uid)

    assert user_detail.main_text(), "Detail page rendered nothing for a large metadata blob"
    assert not user_detail.visible_error_banners(), (
        f"Large metadata produced an error: {user_detail.visible_error_banners()}"
    )
    overflow = user_detail.page.evaluate(
        "() => Math.round(document.documentElement.scrollWidth - document.documentElement.clientWidth)"
    )
    assert overflow <= 4, f"Large metadata caused {overflow}px of horizontal page overflow"


@pytest.mark.tc(id="USR_089", scenario=STATE_SCENARIO, sentiment="Negative", priority="Medium",
                title="Verify loading state while the users table fetches",
                expected="Skeleton or spinner shown while data loads")
def test_usr_089_loading_state(raw_users, app_config):
    page = raw_users.page
    client = page.context.new_cdp_session(page)
    client.send("Network.enable")
    client.send(
        "Network.emulateNetworkConditions",
        {"offline": False, "latency": 400,
         "downloadThroughput": 50 * 1024 // 8, "uploadThroughput": 50 * 1024 // 8},
    )

    seen = False
    try:
        page.goto(
            f"{app_config['base_url']}/app/{app_config['app_id']}/users",
            wait_until="commit", timeout=90_000,
        )
        for _ in range(60):
            if raw_users.is_loading():
                seen = True
                break
            page.wait_for_timeout(250)
    finally:
        try:
            client.send(
                "Network.emulateNetworkConditions",
                {"offline": False, "latency": 0,
                 "downloadThroughput": -1, "uploadThroughput": -1},
            )
        except Exception:
            pass

    assert seen, (
        "No skeleton or spinner appeared while the users table loaded over a throttled "
        "(~50 kbps / 400 ms) connection — the table pops in with no loading feedback"
    )


@pytest.mark.tc(id="USR_090", scenario=STATE_SCENARIO, sentiment="Negative", priority="High",
                title="Verify expired session on the Users page redirects to login",
                expected="Redirects to login, not a stale or empty user list")
def test_usr_090_expired_session(raw_users, app_config):
    page = raw_users.page
    raw_users.open()

    page.context.clear_cookies()
    try:
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass

    page.goto(
        f"{app_config['base_url']}/app/{app_config['app_id']}/users",
        wait_until="domcontentloaded", timeout=60_000,
    )
    page.wait_for_timeout(5_000)

    url, body = page.url, page.locator("body").inner_text()
    assert re.search(r"login|signin|sign-in|auth", url, re.I) or re.search(
        r"log ?in|sign ?in|password|continue with", body, re.I
    ), f"Expired session did not redirect to login. Landed on {url} showing: {body[:200]!r}"


@pytest.mark.tc(id="USR_091", scenario=STATE_SCENARIO, sentiment="Positive", priority="Medium",
                title="Verify deep-linking directly to a user detail URL",
                expected="Correct user's detail page loads directly")
def test_usr_091_deep_link(user_detail, seeded_user):
    user_detail.open_uid(seeded_user)

    text = user_detail.main_text()
    assert seeded_user in text or seeded_user in user_detail.page.url, (
        f"Deep link to {seeded_user} did not load that user's detail page. "
        f"URL: {user_detail.page.url}"
    )
    assert not re.search(r"not found|404", text, re.I), (
        "Deep link to a valid user rendered a not-found state"
    )


@pytest.mark.tc(id="USR_092", scenario=STATE_SCENARIO, sentiment="Negative", priority="Medium / High",
                title="Verify detail page for a non-existent UID",
                expected="Clear not-found state, not a blank page or unhandled error")
def test_usr_092_missing_user(user_detail):
    bogus = make_uid("does_not_exist")
    user_detail.open_uid(bogus)

    text = user_detail.main_text()
    assert text.strip(), f"Detail page for a non-existent UID ({bogus}) rendered a blank page"
    assert re.search(r"not found|does not exist|no .*user|404|invalid", text, re.I), (
        f"No clear not-found state for a non-existent UID. Page reads: {text[:200]!r}"
    )
