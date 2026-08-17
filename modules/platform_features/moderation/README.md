# Moderation

Dashboard location: **PLATFORM FEATURES > Moderation**

Not yet automated.

## To add this module

1. `<name>_page.py` — page object. Keep every app-specific selector in one
   `SELECTORS` dict at the top so a DOM scan can correct them in one place.
2. `conftest.py` — module fixtures. Import `APP_ID` / `BASE_URL` from the root
   conftest; import `make_uid` / `is_e2e_owned` from `core.testdata` if the
   module creates data.
3. `test_*.py` — one file per scenario group. Every test carries
   `@pytest.mark.tc(id=..., scenario=..., priority=..., title=..., expected=...)`
   so it maps back to the test-case sheet and into the HTML report.

Collection, result capture and the report pick it up automatically.
