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


@pytest.fixture(scope="function")
def user_factory(users: UsersPage):
    """Create disposable users through the UI; delete them on teardown.

    Usage:
        uid = user_factory(name="Alice")          # -> created UID
        uid = user_factory(name="Bob", tags="qa") # extra fields optional
    """
    created: List[str] = []

    def _create(name: Optional[str] = None, uid: Optional[str] = None, **extra) -> str:
        the_uid = uid or make_uid()
        the_name = name or f"{E2E_PREFIX} {the_uid[-6:]}"
        if not users.open_add_user():
            pytest.skip("Could not open the Add User modal — cannot seed test data")
        users.fill_user_form(name=the_name, uid=the_uid, **extra)
        users.save_modal()
        created.append(the_uid)
        return the_uid

    yield _create

    # ---- teardown: remove only what we created -----------------------------
    for uid in created:
        try:
            users.open()
            if users.search_box() is not None:
                users.search(uid)
            row = users.row_for_uid(uid)
            if row is None:
                continue
            idx = users._row_index_for(uid)
            if idx < 0 or not is_e2e_owned(users.rows().nth(idx).inner_text()):
                continue
            control = users.row_action(idx, 2)  # delete
            if control is None:
                continue
            control.click()
            users.page.wait_for_timeout(900)
            users.accept_confirm()
        except Exception:
            # Teardown must never fail the run; leftovers are prefixed and obvious.
            pass


@pytest.fixture(scope="function")
def seeded_user(user_factory) -> str:
    """A single disposable user, created fresh for the test."""
    return user_factory()
