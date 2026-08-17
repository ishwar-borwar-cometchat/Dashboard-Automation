# CometChat Dashboard — E2E Automation Suite

Playwright + pytest suite for the CometChat Dashboard.

| Module | Cases | IDs |
|---|---|---|
| Overview | 55 | `OV_001`–`OV_055` |
| User & Groups > Users | 92 | `USR_001`–`USR_092` |
| **Total** | **147** | |

```
cometchat-e2e/
├── conftest.py                 fixtures + result collection -> reports/results.json
├── pytest.ini
├── run_tests.sh                run suite + build HTML report
├── pages/
│   ├── base_page.py            shared navigation/locator helpers
│   ├── overview_page.py        Overview page object (selectors verified live)
│   ├── users_page.py           Users list page object (SELECTORS dict at top)
│   └── user_detail_page.py     User detail: General / Friends / Groups
├── tests/
│   ├── test_01_page_load.py        OV_001 – OV_005
│   ├── test_02_get_started.py      OV_006 – OV_010
│   ├── test_03_credentials.py      OV_011 – OV_017, OV_051 – OV_052
│   ├── test_04_usage.py            OV_018 – OV_023
│   ├── test_05_operational_data.py OV_024 – OV_027
│   ├── test_06_charts.py           OV_028 – OV_034
│   ├── test_07_quick_links.py      OV_035 – OV_044
│   ├── test_08_sidebar.py          OV_045 – OV_048
│   ├── test_09_negative.py         OV_049, OV_050, OV_053 – OV_055
│   ├── test_10_users_list.py       USR_001 – USR_007
│   ├── test_11_users_search.py     USR_056 – USR_060
│   ├── test_12_users_filters.py    USR_008 – USR_012, USR_066 – USR_068
│   ├── test_13_users_pagination.py USR_061 – USR_065
│   ├── test_14_add_user.py         USR_013 – USR_024, USR_069 – USR_070
│   ├── test_15_add_user_validation.py USR_046 – USR_051, USR_071 – USR_074
│   ├── test_16_detail_general.py   USR_025 – USR_032, USR_075 – USR_076, USR_081 – USR_082
│   ├── test_17_detail_friends.py   USR_033 – USR_037, USR_083 – USR_085
│   ├── test_18_detail_groups.py    USR_038 – USR_042
│   ├── test_19_user_actions.py     USR_043 – USR_045, USR_077 – USR_080
│   └── test_20_users_edge.py       USR_052 – USR_055, USR_086 – USR_092
├── utils/
│   ├── report.py               pass/fail/skip HTML report generator
│   ├── scan_users_page.js      DevTools snippet to verify Users selectors
│   ├── make_storage_state.py   build Playwright auth state from a browser export
│   └── devtools_snippet.js     console snippet to dump localStorage/sessionStorage
├── auth/storage_state.json     (you create this — gitignored)
├── artifacts/                  failure screenshots
└── reports/                    results.json + overview_report.html
```

Every test carries a `@pytest.mark.tc(...)` marker holding its spreadsheet ID, scenario,
priority and expected result. The report is built from those markers, so the HTML output
maps 1:1 back to `Overview_Test_Cases.xlsx`.

## Install

```bash
pip install playwright pytest pytest-playwright
playwright install chromium
```

## Authentication

The dashboard authenticates with a **Bearer JWT held in localStorage** (sent to
`apimgmt.cc-cluster-*.io`), not with session cookies — so the suite captures a whole
browser session rather than a cookie header.

### Recommended: interactive capture (once per ~7 days)

```bash
python utils/bootstrap_auth.py
```

Chrome opens, you log in by hand, press Enter, and the full session (cookies +
localStorage) is saved to `auth/storage_state.json`. The script prints which
localStorage key holds the JWT. No credentials are typed by the script or stored
anywhere else.

### Alternative: headless / CI

```bash
export CC_AUTH_TOKEN='eyJ0eXAiOiJKV1Qi...'   # the dashboard Bearer token
export CC_TOKEN_KEY='token'                  # key printed by bootstrap_auth.py
./run_tests.sh
```

The token is seeded into localStorage before app JS runs and attached as an
`authorization` header on outbound requests.

> Never commit `auth/storage_state.json` or a `CC_AUTH_TOKEN` value — both grant
> full access to the dashboard account until they expire.

### Legacy cookie import

`utils/make_storage_state.py` + `utils/devtools_snippet.js` build a state file from a
`Copy as cURL` export. Kept for environments that authenticate by cookie; not needed
for the current dashboard.

## Run

```bash
./run_tests.sh                       # full Overview suite + HTML report
./run_tests.sh tests/test_03_credentials.py
./run_tests.sh -k "OV_018 or OV_019"
CC_HEADLESS=0 ./run_tests.sh         # watch it run
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CC_BASE_URL` | `https://app.cometchat.com` | Dashboard origin |
| `CC_APP_ID` | `1671876b17a071c54` | App under test |
| `CC_STORAGE_STATE` | `auth/storage_state.json` | Playwright auth state |
| `CC_HEADLESS` | `1` | Set `0` to run headed |
| `CC_SLOWMO` | `0` | ms delay between actions when debugging |
| `CC_AUTH_TOKEN` | — | Bearer JWT, instead of a storage-state file |
| `CC_TOKEN_KEY` | `token` | localStorage key the dashboard reads the JWT from |

## Report

`reports/overview_report.html` — standalone, no assets required. Summary tiles, a
blocking-failures callout for Critical/High regressions, status filters, per-case
failure traces and links to failure screenshots in `artifacts/`.

## Live run — 17 Aug 2026

All 55 cases were executed against the live dashboard (app `1671876b17a071c54`).
Result: **48 pass, 1 fail, 6 skip**. See `reports/overview_report.html`.

### The one failure

**OV_052 — Auth Key exposed in the DOM (High/Critical).** The Auth Key row renders
two siblings: `.style_credentialItemLeft` holds the 40 mask characters the user sees,
and `.style_credentialItemRight` holds a `display:none` div containing the **real
40-character key**. It is in the DOM from first paint, before the user ever clicks
reveal, and is byte-identical to what the copy button writes to the clipboard.
Masking is presentation-only — any extension, injected script, or DOM snapshot can
read the production key. Fix: hold the key in component state, render it only while
revealed, and have the copy handler read from state.

### Observations worth raising (all passed, none blocking)

| Where | Observation |
|---|---|
| OV_022 | Usage indicators are 20-segment bars (5% per segment), so MAU 2/100, Voice 2/2500 and Video 4/2500 all render **zero** filled segments — visually identical to no usage. PCC 2/25 (8%) correctly fills 1. |
| OV_040 | Slack Support is the only Quick Link that opens an in-app modal instead of calling `window.open`. Confirm that request-a-channel is the intended behaviour. |
| OV_042 | Product Updates points at `https://Updates.cometchat.com/` — capitalised host, inconsistent with every other link. |
| OV_045 | Sidebar active state is a CSS-module class only; no `aria-current`, `aria-selected`, or `ant-menu-item-selected`, so screen readers cannot announce the current page. |
| Credentials | Every credential value is rendered twice (visible + hidden node). Selectors must target `.style_credentialItemLeft` or they pick up doubled text. |

### DOM facts the selectors rely on

* Ant Design 5 + CSS modules; charts are **ApexCharts**.
* Product cards and Quick Links are `div[role=button]` with `window.open` handlers —
  **not anchors**, so there is no `href` to assert. The suite intercepts `window.open`
  (`OverviewPage.click_quick_link`) instead of navigating.
* Card icons use CSS `mask-image`, not `<svg>`/`<img>`.
* Sidebar labels collide with product-card labels — always scope card lookups to
  `[class*=navigationCardLink]`.

## Cases that skip (and why)

| ID | Status | Reason |
|---|---|---|
| `OV_023` | skip | Needs chat traffic seeded via SDK/REST plus billing aggregation lag. |
| `OV_034` | skip | Inconclusive in the live run only — ApexCharts ignores synthetic pointer events. The Playwright suite drives it properly with `page.mouse.move()`; run locally for a verdict. |
| `OV_049` | skip | Target app already has usage; needs a freshly created zero-usage app. |
| `OV_053` | skip | Needs CDP network throttling — automated here, was unavailable in the live run. |
| `OV_054` | skip | Needs route interception to fault the usage API — automated here, unavailable in the live run. |
| `OV_055` | skip | Clears cookies/localStorage. Automated here against a disposable context; deliberately NOT run against a real logged-in browser. |

`OV_033` and `OV_050` also self-skip if the target app happens to have data in every
chart; on this app Recording Minutes was empty, so both executed and passed.

## Adding the next module

1. Add `pages/<module>_page.py`.
2. Add `tests/test_NN_<module>.py` with `@pytest.mark.tc(...)` markers.
3. Nothing else — collection, result capture and the HTML report pick it up automatically.


---

## Users module — read before the first run

### Test data safety

The Users tests create, deactivate and delete real users in your CometChat app.
Two guards keep that safe:

* **Every user the suite creates is prefixed** (`e2e_...`, override with `CC_E2E_PREFIX`)
  and deleted in fixture teardown.
* **Destructive tests refuse to touch anything else.** `test_19_user_actions.py`
  calls `is_e2e_owned()` before every deactivate/delete and hard-fails rather than
  acting on a row without the prefix.

Run against a non-production app the first time regardless. If a run is interrupted
mid-way, leftovers are all prefixed — search `e2e_` and delete.

### Selector status — action needed

Overview's selectors were verified against the live DOM. **The Users page could not
be scanned** (browser bridge unavailable), so the app-specific selectors are
*inferred* from what Overview established about this dashboard: Ant Design 5
(`.ant-table`, `.ant-modal`, `.ant-pagination`, `.ant-tabs`) plus CSS-module class
names, with controls often rendered as `div[role=button]` rather than `<button>`.

The Ant Design selectors are high confidence. The inferred ones are grouped in
`SELECTORS` at the top of `pages/users_page.py`, each tagged `# INFERRED`:

```python
"search_input":    "input[placeholder*='Search' i]",   # INFERRED
"filter_button":   "button:has-text('Filter')",        # INFERRED
"add_user_button": "button:has-text('Add User')",      # INFERRED
"row_actions":     "td:last-child",                    # INFERRED
"toolbar":         "[class*=toolbar i], ...",          # INFERRED
```

To correct them: open the Users page, paste `utils/scan_users_page.js` into the
DevTools console, and reconcile that block with the output. Nothing outside it
should need changing — that is the whole point of keeping them in one dict.

### What to expect on the first run

Expect failures in the inferred areas — that is the cost of building without a
scan, and the messages name the selector that missed rather than just asserting
False. The Ant Design-backed tests (table, tabs, modal, pagination, form errors)
should hold.

One test is expected to fail for a *real* reason: **USR_081**. It applies the same
check that caught `OV_052` on Overview, where the Auth Key was rendered into a
`display:none` node while showing as masked. The Auth Tokens table is likely the
same component pattern.
