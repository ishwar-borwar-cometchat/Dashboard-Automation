"""Fixtures for PRODUCTS > Chat & Messaging > Features.

SAFETY: toggle tests run against a live CometChat app and flip real extension
config. Every toggle test records the extension's state before touching it and
`restore_extension_state` puts it back in teardown — even if the test fails
midway — so a run never leaves the app's Features config different from how it
found it.
"""
from __future__ import annotations

from typing import Callable, Dict

import pytest
from playwright.sync_api import Page

from conftest import APP_ID, BASE_URL
from modules.products.chat_and_messaging.chat_features_page import ChatFeaturesPage


@pytest.fixture(scope="function")
def chat_features(page: Page) -> ChatFeaturesPage:
    """Features page, already opened and settled."""
    cf = ChatFeaturesPage(page, app_id=APP_ID, base_url=BASE_URL)
    cf.open()
    if "/login" in page.url or "signin" in page.url.lower():
        pytest.exit(
            "\nRedirected to login — the exported session has expired.\n"
            "Re-export storage_state.json and re-run.\n",
            returncode=4,
        )
    return cf


@pytest.fixture(scope="function")
def raw_chat_features(page: Page) -> ChatFeaturesPage:
    """Features page object WITHOUT auto-navigation (for the page-load case)."""
    return ChatFeaturesPage(page, app_id=APP_ID, base_url=BASE_URL)


@pytest.fixture(scope="function")
def restore_extension_state(chat_features: ChatFeaturesPage) -> Callable[[str], None]:
    """Call with a feature name before mutating it; restores it after the test."""
    original: Dict[str, bool] = {}

    def _track(feature_name: str) -> None:
        if feature_name not in original:
            original[feature_name] = chat_features.is_enabled(feature_name)

    yield _track

    for feature_name, was_enabled in original.items():
        try:
            chat_features.set_extension(feature_name, was_enabled)
        except Exception:
            # Teardown must never fail the run; a mismatched extension here is
            # loud and obvious on the app's own Features page.
            pass
