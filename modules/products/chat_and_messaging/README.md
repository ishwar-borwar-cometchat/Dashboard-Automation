# Chat & Messaging

Dashboard location: **PRODUCTS > Chat & Messaging > Features**

Automated — 27 cases, CHF_001-CHF_027.

Page objects and CORE/page-load tests live in this folder; the Extensions
round-trip and Smart Chat Features gate tests live in `Feature ( Extensions)/`
(both still share this folder's `conftest.py` fixtures and page object). Run
just this module:

```bash
./run_tests.sh modules/products/chat_and_messaging
```

## Scope

Covers the Features page only (`chat-features`): the CORE feature list and the
24 toggleable Extensions. Get Started/Integrate, Logs, Conversation Explorer,
Settings and Card Builder (other items under this sidebar section) are not yet
automated.

## Findings

* **CHF_027 — "Conversation and Advanced Search" is inconsistently interactive.**
  Grouped under CORE with the other 12 always-on features, but unlike them its
  switch carries no `disabled` attribute — it is a live, clickable toggle. Not
  exercised live by this suite (out of scope to flip a feature described as
  core search behaviour); flagged as a UI inconsistency worth a product look.
* **CHF_024-026 — Smart Chat Features require AI Settings first.** On an app
  with no AI Settings configured, enabling Conversation Starter, Smart Replies
  or Conversation Summary does not toggle the switch. A modal explains AI
  Settings must be configured first. Handled as its own gate-behavior cases
  rather than the enable/disable round trip every other extension gets.

## Test data safety

CHF_003-023 flip a real extension on live, off live, and record the extension's
starting state before touching it — `restore_extension_state` (this module's
conftest) puts it back in teardown even if a test fails midway. A run never
leaves the app's Features config different from how it found it.
