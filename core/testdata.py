"""Shared helpers for creating and identifying disposable test data.

Every record this suite creates carries E2E_PREFIX so teardown can find it and,
more importantly, so destructive tests can refuse to touch anything else.
"""
from __future__ import annotations

import os
import time
import uuid

E2E_PREFIX = os.environ.get("CC_E2E_PREFIX", "e2e")


def make_uid(tag: str = "user") -> str:
    """Collision-proof, obviously-synthetic identifier."""
    return f"{E2E_PREFIX}_{tag}_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def is_e2e_owned(text: str) -> bool:
    """True only for records this suite created — the destructive-action guard."""
    return f"{E2E_PREFIX}_" in (text or "")
