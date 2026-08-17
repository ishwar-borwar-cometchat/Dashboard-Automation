# CometChat Dashboard — E2E Automation

Playwright + pytest suite for the CometChat Dashboard. The repository mirrors the
dashboard's own sidebar, so a module in the product maps to exactly one folder here.

| Module | Cases | IDs | Status |
|---|---|---|---|
| General > Overview | 55 | `OV_001`–`OV_055` | Automated |
| General > User & Groups > Users | 92 | `USR_001`–`USR_092` | Automated |
| General > User & Groups > Groups | — | — | Not started |
| General > User & Groups > User Roles | — | — | Not started |
| Products > Chat & Messaging | — | — | Not started |
| Products > Voice & Video Calls | — | — | Not started |
| Products > AI Agents | — | — | Not started |
| Products > BYO Agents | — | — | Not started |
| Products > Campaigns | — | — | Not started |
| Platform Features > Moderation | — | — | Not started |
| Platform Features > Notifications | — | — | Not started |
| Platform Features > Analytics & Insights | — | — | Not started |
| Account > Application / Profile / Resources | — | — | Not started |
| **Total automated** | **147** | | |

## Layout

```
Dashboard-Automation/
├── conftest.py           browser/context/page fixtures + result capture
├── pytest.ini
├── run_tests.sh
├── core/
│   ├── base_page.py      navigation and locator helpers shared by every page object
│   └── testdata.py       make_uid() / is_e2e_owned() — the test-data safety guards
├── modules/              ← mirrors the dashboard sidebar
│   ├── general/
│   │   ├── overview/            overview_page.py + 9 test files
│   │   └── user_and_groups/
│   │       ├── users/           users_page.py, user_detail_page.py + 11 test files
│   │       ├── groups/          (placeholder)
│   │       └── user_roles/      (placeholder)
│   ├── products/
│   │   ├── chat_and_messaging/  voice_and_video_calls/  ai_agents/
│   │   └── byo_agents/          campaigns/
│   ├── platform_features/
│   │   └── moderation/  notifications/  analytics_and_insights/
│   └── account/
│       └── application/  profile/  resources/
├── utils/
│   ├── bootstrap_auth.py     one-time interactive login capture
│   ├── report.py             pass/fail/skip HTML report generator
│   └── scan_users_page.js    DevTools snippet to verify Users selectors
├── auth/storage_state.json   (you create this — gitignored)
├── artifacts/                failure screenshots
└── reports/                  results.json + report.html
```

Each module folder holds its own page objects, `conftest.py` and tests. Adding a
module means creating one folder — collection, result capture and the HTML report
pick it up with no central wiring. Every unautomated module already has a folder
with a README describing what to put in it.

Every test carries `@pytest.mark.tc(...)` holding its spreadsheet ID, scenario,
priority and expected result, so the HTML report maps 1:1 back to the test-case
sheets.

## Install

```bash
pip install playwright pytest pytest-playwright
playwright install chromium
```

## Authentication

The dashboard authenticates with a **Bearer JWT in localStorage** (sent to
`apimgmt.cc-cluster-*.io`), not session cookies — so the suite captures a whole
browser session.

```bash
python utils/bootstrap_auth.py
```

Chrome opens, you log in by hand, press Enter, and the session is saved to
`auth/storage_state.json` (valid ~7 days). No credentials are typed by the script
or stored anywhere else. For CI, set `CC_AUTH_TOKEN` and `CC_TOKEN_KEY` instead.

> Never commit `auth/storage_state.json` or a `CC_AUTH_TOKEN` value.

## Run

```bash
./run_tests.sh                                          # everything
./run_tests.sh modules/general/overview                 # one module
./run_tests.sh modules/general/user_and_groups/users
./run_tests.sh -k "OV_052 or USR_081"                   # the security checks
CC_HEADLESS=0 ./run_tests.sh                            # watch it run
```

| Variable | Default | Purpose |
|---|---|---|
| `CC_BASE_URL` | `https://app.cometchat.com` | Dashboard origin |
| `CC_APP_ID` | `1671876b17a071c54` | App under test |
| `CC_STORAGE_STATE` | `auth/storage_state.json` | Playwright auth state |
| `CC_HEADLESS` | `1` | Set `0` to run headed |
| `CC_SLOWMO` | `0` | ms delay between actions when debugging |
| `CC_E2E_PREFIX` | `e2e` | Prefix for test-created data |
| `CC_AUTH_TOKEN` / `CC_TOKEN_KEY` | — | Bearer JWT path for CI |

`reports/report.html` is standalone: summary tiles, a blocking-failures callout for
Critical/High regressions, status filters, failure traces and screenshot links.

## Test data safety

The Users tests create, deactivate and delete real users. Two guards:

* Everything the suite creates is prefixed (`e2e_...`) and deleted in teardown.
* Destructive tests call `is_e2e_owned()` before acting and **hard-fail** rather
  than touching a row without that prefix.

Use a non-production app for the first run regardless. If a run is interrupted,
leftovers are all prefixed — search `e2e_` and delete.

## Findings so far

### Overview — live run, 17 Aug 2026: 48 pass, 1 fail, 6 skip

**OV_052 — Auth Key exposed in the DOM (High/Critical).** The Auth Key row renders
`.style_credentialItemLeft` with 40 mask characters, and a sibling
`.style_credentialItemRight` holding a `display:none` div containing the **real
40-character key**. It is in the DOM from first paint, before the user clicks
reveal, and is byte-identical to what the copy button writes to the clipboard.
Masking is presentation-only. Fix: hold the key in component state, render it only
while revealed, and read from state in the copy handler.

Observations that passed but are worth raising:

| Where | Observation |
|---|---|
| OV_022 | Usage indicators are 20-segment bars (5%/segment), so MAU 2/100, Voice 2/2500 and Video 4/2500 all show **zero** filled segments — visually identical to no usage. PCC 2/25 (8%) correctly fills 1. |
| OV_040 | Slack Support is the only Quick Link opening a modal rather than `window.open`. |
| OV_042 | Product Updates points at `https://Updates.cometchat.com/` — capitalised host. |
| OV_045 | Sidebar active state is a CSS-module class only; no `aria-current` or `aria-selected`, so screen readers cannot announce the current page. |

### Users — not yet run

**Selectors are inferred, not verified.** The Users page could not be scanned, so
the Ant Design selectors (`.ant-table`, `.ant-modal`, `.ant-pagination`,
`.ant-tabs`) are high confidence from the Overview scan, but five app-specific ones
are tagged `# INFERRED` in the `SELECTORS` dict at the top of `users_page.py`:
search input, filter button, Add User button, row-actions cell, toolbar.

Run `utils/scan_users_page.js` in DevTools on the Users page and reconcile that one
block. Nothing outside it should need changing.

**USR_081 is the one to watch.** It applies the same check that caught OV_052, and
the Auth Tokens table on the user detail page is likely the same component pattern.

## Adding a module

1. Create `modules/<group>/<module>/` (most already exist as placeholders).
2. Add `<name>_page.py` with all app-specific selectors in one `SELECTORS` dict.
3. Add `conftest.py` for module fixtures.
4. Add `test_*.py` files with `@pytest.mark.tc(...)` markers.

Nothing central needs editing.
