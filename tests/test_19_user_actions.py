"""USR_043 - USR_045 : deactivate / reactivate / delete.
USR_077 - USR_080 : confirmation behaviour (added).

SAFETY: every test here acts only on a user this suite created (UID carries the
E2E prefix). The guard below hard-fails rather than touching a real user.
"""
from __future__ import annotations

import re

import pytest

from conftest import is_e2e_owned

SCENARIO = "User Actions - Deactivate/Delete"
CONFIRM_SCENARIO = "User Actions - Confirmations"

VIEW, DEACTIVATE, DELETE = 0, 1, 2


def _locate(users, uid: str) -> int:
    """Find a suite-owned user's row index, refusing to act on anything else."""
    users.open()
    if users.search_box() is not None:
        users.search(uid)
    idx = users._row_index_for(uid)
    assert idx >= 0, f"Seeded user {uid} not found in the list"
    row_text = users.rows().nth(idx).inner_text()
    assert is_e2e_owned(row_text), (
        f"SAFETY STOP: row {idx} does not carry the e2e prefix — refusing to run a "
        f"destructive action against a real user. Row reads: {row_text[:120]!r}"
    )
    return idx


@pytest.mark.tc(id="USR_043", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify deactivating a user",
                expected="User moves to Deactivated Users, no longer in Active")
def test_usr_043_deactivate(users, seeded_user):
    idx = _locate(users, seeded_user)

    control = users.row_action(idx, DEACTIVATE)
    assert control is not None, "No deactivate control on the user row"
    control.click()
    users.page.wait_for_timeout(900)
    users.accept_confirm()

    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    assert users.row_for_uid(seeded_user) is None, (
        f"{seeded_user} still appears in Active Users after deactivation"
    )

    users.switch_tab("Deactivated")
    if users.search_box() is not None:
        users.search(seeded_user)
    assert users.row_for_uid(seeded_user) is not None, (
        f"{seeded_user} was removed from Active but does not appear in Deactivated Users"
    )


@pytest.mark.tc(id="USR_044", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify reactivating a deactivated user",
                expected="User returns to the Active Users list")
def test_usr_044_reactivate(users, seeded_user):
    idx = _locate(users, seeded_user)
    control = users.row_action(idx, DEACTIVATE)
    assert control is not None, "No deactivate control on the user row"
    control.click()
    users.page.wait_for_timeout(900)
    users.accept_confirm()

    users.switch_tab("Deactivated")
    if users.search_box() is not None:
        users.search(seeded_user)
    d_idx = users._row_index_for(seeded_user)
    assert d_idx >= 0, "Precondition failed: user is not in the Deactivated tab"

    reactivate = users.row_action(d_idx, 0)
    assert reactivate is not None, "No reactivate control on the deactivated row"
    reactivate.click()
    users.page.wait_for_timeout(900)
    users.accept_confirm()

    users.switch_tab("Active")
    if users.search_box() is not None:
        users.search(seeded_user)
    assert users.row_for_uid(seeded_user) is not None, (
        f"{seeded_user} did not return to Active Users after reactivation"
    )


@pytest.mark.tc(id="USR_045", scenario=SCENARIO, sentiment="Positive", priority="High",
                title="Verify deleting a user", expected="User permanently removed from the list")
def test_usr_045_delete(users, user_factory):
    uid = user_factory(name="E2E To Delete")
    idx = _locate(users, uid)

    control = users.row_action(idx, DELETE)
    assert control is not None, "No delete control on the user row"
    control.click()
    users.page.wait_for_timeout(900)
    users.accept_confirm()

    users.open()
    if users.search_box() is not None:
        users.search(uid)
    assert users.row_for_uid(uid) is None, f"{uid} still appears after deletion"


# ---------------------------------------------------------------------------
# Added during review — the cancel paths
# ---------------------------------------------------------------------------
@pytest.mark.tc(id="USR_077", scenario=CONFIRM_SCENARIO, sentiment="Positive", priority="High",
                title="Verify cancelling the deactivate confirmation",
                expected="User remains active and stays in the Active Users tab")
def test_usr_077_cancel_deactivate(users, seeded_user):
    idx = _locate(users, seeded_user)

    control = users.row_action(idx, DEACTIVATE)
    assert control is not None, "No deactivate control on the user row"
    control.click()
    users.page.wait_for_timeout(900)

    assert users.confirm_dialog() is not None, (
        "Deactivate fired with no confirmation dialog — a destructive action should confirm"
    )
    users.dismiss_confirm()

    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    assert users.row_for_uid(seeded_user) is not None, (
        f"{seeded_user} was deactivated despite cancelling the confirmation"
    )


@pytest.mark.tc(id="USR_078", scenario=CONFIRM_SCENARIO, sentiment="Positive",
                priority="High / Critical",
                title="Verify cancelling the delete confirmation",
                expected="User remains in the list, nothing deleted")
def test_usr_078_cancel_delete(users, seeded_user):
    idx = _locate(users, seeded_user)

    control = users.row_action(idx, DELETE)
    assert control is not None, "No delete control on the user row"
    control.click()
    users.page.wait_for_timeout(900)

    assert users.confirm_dialog() is not None, (
        "Delete fired with no confirmation dialog — a permanent action must confirm"
    )
    users.dismiss_confirm()

    users.open()
    if users.search_box() is not None:
        users.search(seeded_user)
    assert users.row_for_uid(seeded_user) is not None, (
        f"{seeded_user} was deleted despite cancelling the confirmation"
    )


@pytest.mark.tc(id="USR_079", scenario=CONFIRM_SCENARIO, sentiment="Positive",
                priority="Medium / High",
                title="Verify delete confirmation states the action is permanent",
                expected="Dialog warns the deletion is permanent and names the user")
def test_usr_079_delete_confirm_copy(users, seeded_user):
    idx = _locate(users, seeded_user)

    control = users.row_action(idx, DELETE)
    assert control is not None, "No delete control on the user row"
    control.click()
    users.page.wait_for_timeout(900)

    try:
        assert users.confirm_dialog() is not None, "Delete showed no confirmation dialog"
        copy = users.confirm_dialog_text()
        assert re.search(r"permanent|cannot be undone|irreversible|can't be undone", copy, re.I), (
            f"Delete confirmation does not warn the action is permanent. Reads: {copy[:200]!r}"
        )
        assert seeded_user in copy, (
            f"Delete confirmation does not name the user being deleted. Reads: {copy[:200]!r}"
        )
    finally:
        users.dismiss_confirm()


@pytest.mark.tc(id="USR_080", scenario=CONFIRM_SCENARIO, sentiment="Positive", priority="High",
                title="Verify actions available on the Deactivated Users tab",
                expected="Reactivate and delete actions, not a deactivate action")
def test_usr_080_deactivated_tab_actions(users, seeded_user):
    idx = _locate(users, seeded_user)
    control = users.row_action(idx, DEACTIVATE)
    assert control is not None, "No deactivate control on the user row"
    control.click()
    users.page.wait_for_timeout(900)
    users.accept_confirm()

    users.switch_tab("Deactivated")
    if users.search_box() is not None:
        users.search(seeded_user)
    d_idx = users._row_index_for(seeded_user)
    assert d_idx >= 0, "User not found in the Deactivated tab"

    controls = users.row_action_controls(d_idx)
    assert controls >= 2, (
        f"Deactivated row exposes only {controls} action control(s) — expected at least "
        "reactivate and delete"
    )
