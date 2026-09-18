#!/usr/bin/env python3
"""Verification for Knowledge Base RETRIEVAL, per source — the actual
"agent answers from an attached source" flow, as opposed to
verify_ai_agent_builder.py's read-only KB inventory check.

Tests each of the 3 shared KB sources IN ISOLATION, one at a time, rather
than attaching all 3 together — attaching everything at once can mask a
single broken source behind the other two still working. For each source:

  1. Attach ONLY that source (detach any others first) — verified via
     kb_is_attached(), not assumed from the click.
  2. Reload the Instructions tab fresh (a fresh page load starts a new,
     empty chat — confirmed live 2026-09-18 — so no answer from a
     previous source's question can leak into this one via conversation
     memory).
  3. Ask a question specific to that one source's content.
  4. Poll the chat every 0.5s while waiting (not a single post-wait read),
     to catch the real interim "Retrieving relevant information from
     available sources…" state as evidence retrieval genuinely happened.
  5. Read the final reply. A generic failure ("I could not find any
     match"/"I don't have access to that information") is flagged as a
     real product bug — this is a heuristic flag for a human to read
     against the actual reply text, not an automatic pass/fail, since a
     deliberately thin source (the "test" text source) legitimately
     answering "there isn't much here" is not the same bug as a real
     answer being missed.
  6. Detach that source before moving to the next, so only one source is
     ever attached at a time.

On a disposable test agent throughout — never the real Customer Support
Agent. Sources end fully detached and the test agent is deleted.

This attaches to shared KB source rows, which needs an explicit Bash
permission rule — the harness blocks it by default as a "Modify Shared
Resources" action. See Dashboard-Automation/.claude/settings.local.json.

Usage
-----
    python3 "modules/products/ai_agents/verify_kb_retrieval.py"
    CC_HEADLESS=0 python3 "modules/products/ai_agents/verify_kb_retrieval.py"
    CC_ADD_SOURCE=1 python3 "modules/products/ai_agents/verify_kb_retrieval.py"   # add+verify a new source (see below)
    CC_KEEP_AGENT=1 python3 "modules/products/ai_agents/verify_kb_retrieval.py"   # don't delete the test agent afterward

CC_KEEP_AGENT=1 turns the disposable test agent into a real, permanent one:
skips delete_agent() in the finally block, and — since a kept agent should
actually be usable, not left in whatever isolated single-source state the
last test step needed — attaches ALL sources (run()) or leaves the new
source attached (run_add_source_test()) instead of detaching everything on
the way out. Combine with CC_ADD_SOURCE=1 to create a new permanent agent
wired up with a brand-new Knowledge Base source in one go.

CC_EXISTING_AGENT="<real agent name>" runs the per-source loop (run() only)
against an already-existing real agent instead of creating one — opens it
via manage_agent(), never touches its own Instructions/system prompt, tests
each source in isolation the same way, and leaves all sources attached at
the end. No agent is created or deleted either way.

    CC_EXISTING_AGENT="Knowledge Assistant" python3 "modules/products/ai_agents/verify_kb_retrieval.py"
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from modules.products.ai_agents.ai_agent_builder_page import AIAgentBuilderPage  # noqa: E402
from modules.products.ai_agents.ai_agents_page import AIAgentsPage  # noqa: E402

ROOT = REPO_ROOT
REPORTS = ROOT / "reports" / "kb_retrieval_verification"
REPORTS.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("CC_BASE_URL", "https://app.cometchat.com")
APP_ID = os.environ.get("CC_APP_ID", "168258051159eab49")
STORAGE_STATE = os.environ.get("CC_STORAGE_STATE", str(ROOT / "auth" / "storage_state.json"))
HEADLESS = os.environ.get("CC_HEADLESS", "1") != "0"
KEEP_AGENT = os.environ.get("CC_KEEP_AGENT") == "1"  # opt-in: skip delete_agent(), leave a real permanent agent
AGENT_NAME_OVERRIDE = os.environ.get("CC_AGENT_NAME")  # real name for a kept agent, instead of the auto QA-test name
EXISTING_AGENT_NAME = os.environ.get("CC_EXISTING_AGENT")  # test against a real, already-existing agent instead of creating one

SYSTEM_PROMPT = (
    "You are a QA probe agent. Use the attached knowledge base to answer "
    "questions. If you genuinely cannot find relevant information, say so "
    "clearly."
)
REAL_AGENT_SYSTEM_PROMPT = (
    "You are a helpful knowledge assistant. Answer questions using the "
    "attached knowledge base. If you genuinely cannot find relevant "
    "information, say so clearly rather than guessing."
)

# One question per source, asked with only that source attached. Phrased
# naturally — NOT naming the source/file — so this tests real semantic
# retrieval (does the agent find and use the right content on its own)
# rather than just following an instruction to read a specific file.
SOURCE_QUESTIONS = {
    "https://www.cometchat.com/docs": (
        "Can you tell me what resources and deployment options are available, "
        "based on whatever is in your knowledge base?"
    ),
    "Complete_Manual-Testing.pdf": (
        "What does your knowledge base say about software testing — things "
        "like fundamentals, roles, or deliverables?"
    ),
    "test": (
        "Give me a one-line summary of everything currently in your knowledge base."
    ),
    "Push Notifications": (
        "What happens when someone gets a new message or call while they're "
        "not actively using the app?"
    ),
}

RETRIEVAL_HINT_PHRASES = [
    "retriev", "searching", "looking through", "knowledge base", "checking my knowledge",
]
NO_MATCH_PHRASES = [
    "could not find", "couldn't find", "no relevant information", "don't have access",
    "do not have access", "no match", "unable to find", "i don't have information",
    "i do not have information",
]


def ensure_only_attached(
    builder: AIAgentBuilderPage, new_page, source_names: list[str], target: str, toggle_on_shot: pathlib.Path
) -> dict:
    """Attach `target` and detach every other source; screenshot the KB page
    right after (showing `target`'s switch ON and the others OFF), and
    return the resulting attach state so isolation can be verified, not
    assumed from the click.
    """
    builder.open_knowledge_base(force=True)
    for name in source_names:
        if name == target:
            builder.attach_source(name)
        else:
            builder.detach_source(name)
    state = {name: builder.kb_is_attached(name) for name in source_names}
    new_page.screenshot(path=str(toggle_on_shot), full_page=True)
    return state


INTERIM_STATE_TEXTS = {"thinking…", "retrieving relevant information from available sources…"}


def wait_for_stable_reply(page, max_seconds: float = 45.0, interval: float = 0.5, stable_reads: int = 4) -> list[str]:
    """Poll message bubbles until the last one stops changing for
    `stable_reads` consecutive polls (2s of no change by default) AND isn't
    still one of the known interim/loading strings — instead of trusting a
    single fixed-duration sleep, which can fire mid-stream (stop button
    still showing) or before the reply bubble even starts rendering. Caught
    exactly that failure mode once already: a fixed wait captured the
    interim "Retrieving relevant information…" text as if it were the final
    answer. Returns every distinct state observed, in order.
    """
    bubbles = page.locator("[class*='cometchat-message-bubble']")
    samples: list[str] = []
    same_count = 0
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            texts = [bubbles.nth(i).inner_text().strip() for i in range(bubbles.count())]
            texts = [t for t in texts if t]
        except Exception:
            texts = []
        last = texts[-1] if texts else ""
        if texts and (not samples or samples[-1] != last):
            samples.append(last)
            same_count = 0
        elif texts:
            same_count += 1
            if same_count >= stable_reads and last.strip().lower() not in INTERIM_STATE_TEXTS:
                break
        time.sleep(interval)
    return samples


def ask_and_capture(
    builder: AIAgentBuilderPage,
    new_page,
    question: str,
    asked_shot: pathlib.Path,
    response_shot: pathlib.Path,
) -> dict:
    builder.open_instructions(force=True)  # fresh load -> empty chat, no memory bleed from a prior source's Q&A

    composer = new_page.locator("[data-placeholder='Ask anything']")
    composer.wait_for(state="visible", timeout=20_000)
    composer.click()
    new_page.keyboard.type(question)
    new_page.screenshot(path=str(asked_shot), full_page=True)  # question typed, not yet sent
    new_page.keyboard.press("Enter")

    all_samples = wait_for_stable_reply(new_page)
    new_page.screenshot(path=str(response_shot), full_page=True)

    reply_text = all_samples[-1] if all_samples else ""
    retrieval_hint_seen = any(any(p in s.lower() for p in RETRIEVAL_HINT_PHRASES) for s in all_samples)
    no_match_flag = any(p in reply_text.lower() for p in NO_MATCH_PHRASES)
    still_interim = reply_text.strip().lower() in INTERIM_STATE_TEXTS

    return {
        "question": question,
        "observed_states": all_samples,
        "reply_text": reply_text,
        "retrieval_indicator_shown": retrieval_hint_seen,
        "no_match_flag": no_match_flag,
        "ok": bool(reply_text) and not no_match_flag and not still_interim,
    }


def run(screenshot_dir: pathlib.Path) -> dict:
    results: dict = {"per_source": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        agents = AIAgentsPage(page, APP_ID, BASE_URL)

        agents.open(force=True)
        if "/login" in page.url:
            raise RuntimeError(
                f"Redirected to {page.url} — auth/storage_state.json is stale. "
                "Run `python3 utils/bootstrap_auth.py` to refresh it."
            )

        using_existing = bool(EXISTING_AGENT_NAME)
        if using_existing:
            test_name = EXISTING_AGENT_NAME
            if not agents.exists(test_name):
                raise RuntimeError(f"CC_EXISTING_AGENT='{test_name}' not found on the AI Agents list")
        else:
            test_name = AGENT_NAME_OVERRIDE or f"QA KB Retrieval Test {int(time.time())}"
            description = (
                "Answers questions using the full Knowledge Base." if AGENT_NAME_OVERRIDE
                else "Created by verify_kb_retrieval.py — safe to delete."
            )
            agents.add_agent(test_name, description=description)
            if not agents.exists(test_name):
                raise RuntimeError(f"Setup failed: '{test_name}' not on the list after add_agent()")

        new_page = agents.manage_agent(test_name)
        agent_id = new_page.url.rstrip("/").split("/ai-agents/")[1].split("/")[0]
        builder = AIAgentBuilderPage(new_page, APP_ID, BASE_URL, agent_id)

        try:
            if using_existing:
                # Don't touch an existing real agent's own instructions — it
                # already has whatever real prompt it should have.
                builder.open_instructions(force=True)
            else:
                builder.open_instructions(force=True)
                builder.set_instructions(REAL_AGENT_SYSTEM_PROMPT if AGENT_NAME_OVERRIDE else SYSTEM_PROMPT)

            builder.open_knowledge_base(force=True)
            source_names = builder.kb_source_names()

            for i, source in enumerate(source_names):
                print(f"\n--- Source {i+1}/{len(source_names)}: {source} ---")
                question = SOURCE_QUESTIONS.get(
                    source, f"What does your knowledge base say that's relevant to \"{source}\"?"
                )
                slug = source[:30].replace("/", "_").replace(":", "_")

                toggle_on_shot = screenshot_dir / f"{i:02d}_{slug}_1_toggle_on.png"
                asked_shot = screenshot_dir / f"{i:02d}_{slug}_2_asked.png"
                response_shot = screenshot_dir / f"{i:02d}_{slug}_3_response.png"

                attach_state = ensure_only_attached(builder, new_page, source_names, source, toggle_on_shot)
                isolated_ok = attach_state.get(source) is True and all(
                    (v is False) for k, v in attach_state.items() if k != source
                )
                print("Attach state (only target should be True):", attach_state, "| isolated:", isolated_ok)

                qa = ask_and_capture(builder, new_page, question, asked_shot, response_shot)
                qa["source"] = source
                qa["isolated_attach_ok"] = isolated_ok
                qa["ok"] = qa["ok"] and isolated_ok
                qa["screenshots"] = {
                    "toggle_on": str(toggle_on_shot),
                    "asked": str(asked_shot),
                    "response": str(response_shot),
                }

                print("Retrieval indicator shown:", qa["retrieval_indicator_shown"])
                print("Reply:", qa["reply_text"][:300])
                if qa["no_match_flag"]:
                    print("FLAGGED: reply looks like a no-match failure — review manually against the source's real content.")

                results["per_source"][source] = qa

            builder.open_knowledge_base(force=True)
            if KEEP_AGENT or using_existing:
                # This agent is being kept (or already existed), not deleted —
                # leave it with a working Knowledge Base (all sources attached)
                # instead of stripping it back to the isolated single-source
                # state each per-source test used.
                for name in source_names:
                    builder.attach_source(name)
                final_state = {name: builder.kb_is_attached(name) for name in source_names}
                results["all_detached_at_end"] = {"ok": all(final_state.values()), "state": final_state, "kept_attached": True}
                print("\nAgent kept — attached all sources for real use:", final_state)
            else:
                # Leave the KB exactly as found: every source detached.
                for name in source_names:
                    builder.detach_source(name)
                final_state = {name: builder.kb_is_attached(name) for name in source_names}
                results["all_detached_at_end"] = {"ok": not any(final_state.values()), "state": final_state}
                print("\nFinal detach state:", final_state)

        finally:
            new_page.close()
            agents.open(force=True)
            if using_existing:
                results["cleanup"] = {"ok": agents.exists(test_name), "existing_agent": True, "agent_name": test_name}
                print("No cleanup needed — tested against existing agent:", test_name, "| still present:", results["cleanup"]["ok"])
            elif KEEP_AGENT:
                results["cleanup"] = {"ok": agents.exists(test_name), "kept": True, "agent_name": test_name}
                print("Cleanup skipped (CC_KEEP_AGENT=1) — agent kept:", results["cleanup"]["ok"], "| name:", test_name)
            else:
                agents.delete_agent(test_name)
                results["cleanup"] = {"ok": not agents.exists(test_name), "kept": False}
                print("Cleanup (test agent deleted):", results["cleanup"]["ok"])

        ctx.close()
        browser.close()

    return results


NEW_SOURCE_TITLE = "Push Notifications"
NEW_SOURCE_BODY = "Real-time alerts for new messages, calls, and events routed through FCM or APNs."
NEW_SOURCE_QUESTION = "Provide the information about the push notification from the knowledge base"


def run_add_source_test(screenshot_dir: pathlib.Path) -> dict:
    """One-off, opt-in flow (CC_ADD_SOURCE=1): adds a brand-new, PERMANENT
    Text source to the shared Knowledge Base, then verifies an agent can
    retrieve it — same isolation discipline as run() (disposable test
    agent, only this source attached, fresh chat, real retrieval-step
    check) but the source itself is deliberately NOT deleted afterward,
    since the point is to add real lasting content, not a throwaway probe.
    """
    result: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        agents = AIAgentsPage(page, APP_ID, BASE_URL)

        agents.open(force=True)
        if "/login" in page.url:
            raise RuntimeError(
                f"Redirected to {page.url} — auth/storage_state.json is stale. "
                "Run `python3 utils/bootstrap_auth.py` to refresh it."
            )

        test_name = f"QA Add-Source Test {int(time.time())}"
        agents.add_agent(test_name, description="Created by verify_kb_retrieval.py (add-source flow) — safe to delete.")
        if not agents.exists(test_name):
            raise RuntimeError(f"Setup failed: '{test_name}' not on the list after add_agent()")

        new_page = agents.manage_agent(test_name)
        agent_id = new_page.url.rstrip("/").split("/ai-agents/")[1].split("/")[0]
        builder = AIAgentBuilderPage(new_page, APP_ID, BASE_URL, agent_id)

        try:
            builder.open_instructions(force=True)
            builder.set_instructions(REAL_AGENT_SYSTEM_PROMPT if AGENT_NAME_OVERRIDE else SYSTEM_PROMPT)

            builder.open_knowledge_base(force=True)
            builder.add_text_source(NEW_SOURCE_TITLE, NEW_SOURCE_BODY)
            result["source_added"] = {"ok": NEW_SOURCE_TITLE in builder.kb_source_names(), "title": NEW_SOURCE_TITLE, "body": NEW_SOURCE_BODY}
            print("Source added:", result["source_added"]["ok"])

            source_names = builder.kb_source_names()
            toggle_on_shot = screenshot_dir / "push_notifications_1_toggle_on.png"
            asked_shot = screenshot_dir / "push_notifications_2_asked.png"
            response_shot = screenshot_dir / "push_notifications_3_response.png"

            attach_state = ensure_only_attached(builder, new_page, source_names, NEW_SOURCE_TITLE, toggle_on_shot)
            isolated_ok = attach_state.get(NEW_SOURCE_TITLE) is True and all(
                (v is False) for k, v in attach_state.items() if k != NEW_SOURCE_TITLE
            )
            print("Attach state (only target should be True):", attach_state, "| isolated:", isolated_ok)

            qa = ask_and_capture(builder, new_page, NEW_SOURCE_QUESTION, asked_shot, response_shot)
            qa["source"] = NEW_SOURCE_TITLE
            qa["isolated_attach_ok"] = isolated_ok
            qa["ok"] = qa["ok"] and isolated_ok
            qa["screenshots"] = {"toggle_on": str(toggle_on_shot), "asked": str(asked_shot), "response": str(response_shot)}
            print("Retrieval indicator shown:", qa["retrieval_indicator_shown"])
            print("Reply:", qa["reply_text"][:300])
            result["retrieval"] = qa

            builder.open_knowledge_base(force=True)
            if KEEP_AGENT:
                # This agent is being kept, not deleted — leave the source attached
                # so it's actually usable, instead of detaching it right after proving it works.
                result["detached_from_test_agent"] = {"ok": builder.kb_is_attached(NEW_SOURCE_TITLE), "kept_attached": True}
            else:
                # Detach from this disposable agent only — the SOURCE itself stays (permanent, by design).
                builder.detach_source(NEW_SOURCE_TITLE)
                result["detached_from_test_agent"] = {"ok": not builder.kb_is_attached(NEW_SOURCE_TITLE), "kept_attached": False}

        finally:
            new_page.close()
            agents.open(force=True)
            if KEEP_AGENT:
                result["cleanup"] = {"ok": agents.exists(test_name), "kept": True, "agent_name": test_name}
                print("Cleanup skipped (CC_KEEP_AGENT=1) — agent kept:", result["cleanup"]["ok"], "| name:", test_name)
            else:
                agents.delete_agent(test_name)
                result["cleanup"] = {"ok": not agents.exists(test_name), "kept": False}
                print("Cleanup (test agent deleted):", result["cleanup"]["ok"])

        ctx.close()
        browser.close()

    return result


def main() -> None:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    if os.environ.get("CC_ADD_SOURCE") == "1":
        # Opt-in one-off: add the new "Push Notifications" source and verify
        # retrieval against it. Skips the regular 3-source regression loop so
        # this doesn't re-add the source on every future run.
        result = run_add_source_test(screenshot_dir)
        elapsed = time.time() - t0
        out_path = REPORTS / f"{run_id}-add-source.json"
        with open(out_path, "w") as f:
            json.dump({"result": result, "elapsed_s": round(elapsed, 1), "app_id": APP_ID}, f, indent=2, default=str)
        checks = ["source_added", "retrieval", "detached_from_test_agent", "cleanup"]
        passed = sum(1 for c in checks if result.get(c, {}).get("ok"))
        print(f"\n{'=' * 50}")
        print(f"Add Source (Push Notifications): {passed}/{len(checks)} checks passed in {elapsed:.0f}s")
        print(f"Results written to {out_path}")
        print(f"Screenshots written to {screenshot_dir}")
        print(f"{'=' * 50}")
        return

    results = run(screenshot_dir)
    elapsed = time.time() - t0

    out_path = REPORTS / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({"results": results, "elapsed_s": round(elapsed, 1), "app_id": APP_ID}, f, indent=2, default=str)

    per_source_passed = sum(1 for r in results.get("per_source", {}).values() if r.get("ok"))
    per_source_total = len(results.get("per_source", {}))
    other_checks = ["all_detached_at_end", "cleanup"]
    other_passed = sum(1 for c in other_checks if results.get(c, {}).get("ok"))

    print(f"\n{'=' * 50}")
    print(f"KB Retrieval (per source): {per_source_passed}/{per_source_total} sources passed, "
          f"{other_passed}/{len(other_checks)} cleanup checks passed, in {elapsed:.0f}s")
    print(f"Results written to {out_path}")
    print(f"Screenshots written to {screenshot_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
