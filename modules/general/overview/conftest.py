"""Fixtures for the Overview module."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from conftest import APP_ID, BASE_URL
from modules.general.overview.overview_page import OverviewPage


@pytest.fixture(scope="function")
def overview(page: Page) -> OverviewPage:
    """Overview page, already opened and settled."""
    ov = OverviewPage(page, app_id=APP_ID, base_url=BASE_URL)
    ov.open()
    if "/login" in page.url or "signin" in page.url.lower():
        pytest.exit(
            "\nRedirected to login — the exported session has expired.\n"
            "Re-export storage_state.json and re-run.\n",
            returncode=4,
        )
    ov.install_capture()
    return ov


@pytest.fixture(scope="function")
def raw_overview(page: Page) -> OverviewPage:
    """Overview page object WITHOUT auto-navigation (for load/negative tests)."""
    return OverviewPage(page, app_id=APP_ID, base_url=BASE_URL)
