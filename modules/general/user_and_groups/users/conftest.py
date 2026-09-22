"""Fixtures for the User & Groups > Users module."""
from __future__ import annotations

from typing import List, Optional

import pytest
from playwright.sync_api import Page

from conftest import APP_ID, BASE_URL
from core.testdata import E2E_PREFIX, is_e2e_owned, make_uid
from modules.general.user_and_groups.users.users_page import UsersPage
from modules.general.user_and_groups.users.user_detail_page import UserDetailPage


# ---------------------------------------------------------------------------
# Users module fixtures
#
# SAFETY: this suite runs against a live CometChat app. Every user it creates is
# prefixed with E2E_PREFIX and torn down afterwards, and the destructive tests
# (deactivate / delete / remove-friend) refuse to act on any row that does not
# carry that prefix. Nothing pre-existing in your app is ever modified.
# ---------------------------------------------------------------------------
from modules.general.user_and_groups.users.users_page import UsersPage
from modules.general.user_and_groups.users.user_detail_page import UserDetailPage



@pytest.fixture(scope="function")
def users(page: Page) -> UsersPage:
    """Users list page, opened and settled."""
    up = UsersPage(page, app_id=APP_ID, base_url=BASE_URL)
    up.open()
    if "/login" in page.url or "signin" in page.url.lower():
        pytest.exit(
            "\nRedirected to login — the saved session has expired.\n"
            "Re-run: python utils/bootstrap_auth.py\n",
            returncode=4,
        )
    return up


@pytest.fixture(scope="function")
def raw_users(page: Page) -> UsersPage:
    """Users page object WITHOUT auto-navigation (for load / negative tests)."""
    return UsersPage(page, app_id=APP_ID, base_url=BASE_URL)


@pytest.fixture(scope="function")
def user_detail(page: Page) -> UserDetailPage:
    return UserDetailPage(page, app_id=APP_ID, base_url=BASE_URL)


def _create_user(users: UsersPage, name: Optional[str] = None,
                 uid: Optional[str] = None, **extra) -> str:
    """Create one user through the Add User modal and return its UID."""
    the_uid = uid or make_uid()
    the_name = name or f"{E2E_PREFIX} {the_uid[-6:]}"
    if not users.open_add_user():
        pytest.skip("Could not open the Add User drawer — cannot seed test data")
    users.fill_user_form(name=the_name, uid=the_uid, **extra)
    users.save_modal()

    # The drawer closes whether or not the API accepted the user, and shows no
    # error when it did not (observed: POST .../v3.0/users -> 402). Without this
    # check every dependent test fails later with a misleading "user not found".
    if not _user_exists(users, the_uid):
        pytest.skip(
            f"User {the_uid} was not created — the dashboard API rejected it "
            f"(observed HTTP 402 on POST /v3.0/users for this app). "
            f"Seed-dependent Users cases cannot run against this app."
        )
    return the_uid


def _delete_user(users: UsersPage, uid: str) -> None:
    """Delete a user, but only if it carries the e2e prefix."""
    try:
        users.open()
        if users.search_box() is not None:
            users.search(uid)
        row = users.row_for_uid(uid)
        if row is None:
            return
        idx = users._row_index_for(uid)
        if idx < 0 or not is_e2e_owned(users.rows().nth(idx).inner_text()):
            return
        control = users.row_action(idx, 2)  # delete
        if control is None:
            return
        control.click()
        users.page.wait_for_timeout(900)
        users.accept_confirm()
    except Exception:
        # Teardown must never fail the run; leftovers are prefixed and obvious.
        pass


def _user_exists(users: UsersPage, uid: str) -> bool:
    try:
        users.open()
        if users.search_box() is not None:
            users.search(uid)
        return users.row_for_uid(uid) is not None
    except Exception:
        return False


@pytest.fixture(scope="function")
def user_factory(users: UsersPage):
    """Create disposable users through the UI; delete them on teardown.

    Usage:
        uid = user_factory(name="Alice")          # -> created UID
        uid = user_factory(name="Bob", tags="qa") # extra fields optional
    """
    created: List[str] = []

    def _create(name: Optional[str] = None, uid: Optional[str] = None, **extra) -> str:
        the_uid = _create_user(users, name=name, uid=uid, **extra)
        created.append(the_uid)
        return the_uid

    yield _create

    for uid in created:
        _delete_user(users, uid)


class _SharedUser:
    """Holds the UID of the read-only fixture user shared across tests."""

    def __init__(self) -> None:
        self.uid: Optional[str] = None


@pytest.fixture(scope="session")
def _shared_user(shared_context) -> _SharedUser:
    holder = _SharedUser()
    yield holder

    # Deleted once at the end of the run rather than after every test.
    if holder.uid:
        try:
            pg = shared_context.get_page()
            _delete_user(UsersPage(pg, app_id=APP_ID, base_url=BASE_URL), holder.uid)
        except Exception:
            pass


@pytest.fixture(scope="function")
def seeded_user(users: UsersPage, _shared_user: _SharedUser) -> str:
    """A user for tests that only *read* it — shared across the whole run.

    Seeding per test meant clicking through the Add User modal for most of the
    92 Users cases. This creates one user on first use and reuses it, recreating
    it only if it has gone missing. Tests that change a user's state (deactivate,
    reactivate, delete) must use `fresh_user` instead, so they never hand the
    next test a modified user.
    """
    if _shared_user.uid and _user_exists(users, _shared_user.uid):
        return _shared_user.uid

    _shared_user.uid = _create_user(users)
    return _shared_user.uid


@pytest.fixture(scope="function")
def fresh_user(user_factory) -> str:
    """A disposable user created for this test alone and deleted afterwards.

    For tests that deactivate, reactivate or otherwise modify the user.
    """
    return user_factory()
