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
    python3 "Automation Script/AI Agents/verify_kb_retrieval.py"
    CC_HEADLESS=0 python3 "Automation Script/AI Agents/verify_kb_retrieval.py"
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
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

SYSTEM_PROMPT = (
    "You are a QA probe agent. Use the attached knowledge base to answer "
    "questions. If you genuinely cannot find relevant information, say so "
    "clearly."
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
        "Is there anything else in your knowledge base — any short note or "
        "miscellaneous information — that isn't about documentation or "
        "testing?"
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


def poll_bubbles(page, seconds: float, interval: float = 0.5) -> list[str]:
    """Sample message-bubble text repeatedly to catch a transient interim
    state (e.g. a retrieval loader line) that a single post-wait read would miss.
    """
    samples: list[str] = []
    bubbles = page.locator("[class*='cometchat-message-bubble']")
    end = time.time() + seconds
    while time.time() < end:
        try:
            texts = [bubbles.nth(i).inner_text().strip() for i in range(bubbles.count())]
            texts = [t for t in texts if t]
            if texts and (not samples or texts[-1] != samples[-1]):
                samples.append(texts[-1])
        except Exception:
            pass
        time.sleep(interval)
    return samples


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

    interim_samples = poll_bubbles(new_page, seconds=12.0, interval=0.5)
    new_page.wait_for_timeout(4_000)  # let a slower reply finish settling
    final_samples = poll_bubbles(new_page, seconds=3.0, interval=0.5)
    all_samples = interim_samples + [s for s in final_samples if s not in interim_samples]
    new_page.screenshot(path=str(response_shot), full_page=True)

    reply_text = all_samples[-1] if all_samples else ""
    retrieval_hint_seen = any(any(p in s.lower() for p in RETRIEVAL_HINT_PHRASES) for s in all_samples)
    no_match_flag = any(p in reply_text.lower() for p in NO_MATCH_PHRASES)

    return {
        "question": question,
        "observed_states": all_samples,
        "reply_text": reply_text,
        "retrieval_indicator_shown": retrieval_hint_seen,
        "no_match_flag": no_match_flag,
        "ok": bool(reply_text) and not no_match_flag,
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

        test_name = f"QA KB Retrieval Test {int(time.time())}"
        agents.add_agent(test_name, description="Created by verify_kb_retrieval.py — safe to delete.")
        if not agents.exists(test_name):
            raise RuntimeError(f"Setup failed: '{test_name}' not on the list after add_agent()")

        new_page = agents.manage_agent(test_name)
        agent_id = new_page.url.rstrip("/").split("/ai-agents/")[1].split("/")[0]
        builder = AIAgentBuilderPage(new_page, APP_ID, BASE_URL, agent_id)

        try:
            builder.open_instructions(force=True)
            builder.set_instructions(SYSTEM_PROMPT)

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

            # Leave the KB exactly as found: every source detached.
            builder.open_knowledge_base(force=True)
            for name in source_names:
                builder.detach_source(name)
            final_state = {name: builder.kb_is_attached(name) for name in source_names}
            results["all_detached_at_end"] = {"ok": not any(final_state.values()), "state": final_state}
            print("\nFinal detach state:", final_state)

        finally:
            new_page.close()
            agents.open(force=True)
            agents.delete_agent(test_name)
            results["cleanup"] = {"ok": not agents.exists(test_name)}
            print("Cleanup (test agent deleted):", results["cleanup"]["ok"])

        ctx.close()
        browser.close()

    return results


def main() -> None:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    screenshot_dir = REPORTS / f"{run_id}-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
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
