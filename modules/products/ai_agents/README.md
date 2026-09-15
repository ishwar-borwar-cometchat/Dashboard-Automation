# AI Agents

Dashboard location: **PRODUCTS > AI Agents**

Tested against the CometChat Sample App (`168258051159eab49`), the same app
used for the Chat & Messaging extensions/moderation work — not the root
`conftest.py`'s default app (`1671876b17a071c54`), which drives the general
Dashboard-UI regression suite. Pass `--app-id`/env override if that ever
needs to change.

## What's here

- `ai_agents_page.py` — page object for the `/ai-agents` list page:
  `open()`, `agent_names()`, `exists(name)`, `add_agent(name, icon_url=None,
  description=None)`, `manage_agent(name)` (opens the agent's builder IDE in
  a new tab and returns that `Page`).

## Two separate surfaces

1. **The list page** (`/ai-agents`) — one card per agent, a Status switch,
   delete/edit icons, "Manage Agent". `AIAgentsPage` covers this.
2. **The Agent Builder IDE** (`/ai-agents/<agent-id>/instructions`, opened
   by "Manage Agent" in a new tab) — a full separate app with its own
   sidebar: Instructions (model + system prompt + a live chat preview to
   test the agent), Knowledge Base (indexed sources), Tools (Custom API
   Tool, Card Messages, Zendesk, Google Suite — each toggleable, some
   OAuth-gated), Card Builder (external), Variables (built-in Auth
   Variables like sender/receiver uid — several marked "Sensitive" — plus
   Custom Variables), MCP (endpoints), Deploy (website-embed wizard:
   WordPress/HTML/Shopify/Webflow/Wix/Squarespace or a Code path, plus a
   user-sync step), and Logs (Live/History — real conversation traces;
   agent-generated messages carry their own Moderation Status, e.g.
   "Approved" — agent output runs through the same moderation pipeline as
   human messages). Not yet covered by a page object — build
   `ai_agent_builder_page.py` when that's next.

**Known live data on this app (as of 2026-09-15):** two pre-existing agents,
*Customer Support Agent* (real Knowledge Base sources including a
`Complete_Manual-Testing.pdf`, Google Suite OAuth tool enabled, real usage
history including a send-email tool-use flow) and *Weather*, plus
*QA Automation Test Agent* added by this module's `add_agent()`.

## Adding more here

- `conftest.py` — module fixtures, once there's more than one script/test
  file. Import `APP_ID` / `BASE_URL` from the root conftest; import
  `make_uid` / `is_e2e_owned` from `core.testdata` if the module creates
  data that needs cleanup tracking.
- `test_*.py` — one file per scenario group. Every test carries
  `@pytest.mark.tc(id=..., scenario=..., priority=..., title=..., expected=...)`
  so it maps back to the test-case sheet and into the HTML report.

Collection, result capture and the report pick it up automatically.
