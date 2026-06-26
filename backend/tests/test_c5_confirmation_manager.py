"""
C5 ConfirmationManager — unit tests.

Tests:
  1. make_confirmation returns correct structure with status=pending
  2. is_expired returns False for fresh confirmation
  3. is_expired returns True for expired confirmation
  4. is_executable returns True for pending + not expired
  5. is_executable returns False for non-pending status
  6. is_executable returns False for expired
  7. is_expired handles missing/malformed expires_at gracefully
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.chat_confirmation import is_executable, is_expired, make_confirmation


def test_make_confirmation_structure():
    conf = make_confirmation(
        action_type="add_watchlist",
        text="是否将 688146 加入自选股？",
        params={"market": "CN", "symbol": "688146", "name": "中船特气"},
    )
    assert conf["type"]         == "add_watchlist"
    assert conf["status"]       == "pending"
    assert conf["text"]         == "是否将 688146 加入自选股？"
    assert conf["params"]["symbol"] == "688146"
    assert conf["id"].startswith("confirm_add_watchlist_")
    assert conf["created_at"]   is not None
    assert conf["expires_at"]   is not None
    assert conf["confirmed_at"] is None
    assert conf["executed_at"]  is None
    assert conf["error"]        is None


def test_make_confirmation_id_uniqueness():
    """Two confirmations created in the same second have different IDs."""
    c1 = make_confirmation("add_watchlist", "text1", {})
    c2 = make_confirmation("add_watchlist", "text1", {})
    assert c1["id"] != c2["id"]


def test_is_expired_fresh():
    conf = make_confirmation("add_watchlist", "text", {})
    assert is_expired(conf) is False


def test_is_expired_old():
    now = datetime.now(timezone.utc)
    conf = {
        "expires_at": (now - timedelta(minutes=11)).isoformat(),
    }
    assert is_expired(conf) is True


def test_is_expired_exactly_expired():
    now = datetime.now(timezone.utc)
    conf = {
        "expires_at": (now - timedelta(seconds=1)).isoformat(),
    }
    assert is_expired(conf) is True


def test_is_expired_no_expires_at():
    """Missing expires_at → treat as not expired (safe default)."""
    assert is_expired({}) is False
    assert is_expired({"expires_at": None}) is False


def test_is_expired_malformed():
    """Malformed ISO string → treat as not expired."""
    assert is_expired({"expires_at": "not-a-date"}) is False


def test_is_executable_pending_fresh():
    conf = make_confirmation("create_analysis_run", "text", {})
    assert is_executable(conf) is True


def test_is_executable_non_pending_statuses():
    for bad_status in ("confirmed", "cancelled", "expired", "executing", "executed", "failed"):
        conf = make_confirmation("add_watchlist", "text", {})
        conf["status"] = bad_status
        assert is_executable(conf) is False, f"Expected False for status={bad_status}"


def test_is_executable_expired():
    now = datetime.now(timezone.utc)
    conf = make_confirmation("add_watchlist", "text", {})
    conf["expires_at"] = (now - timedelta(minutes=1)).isoformat()
    assert is_executable(conf) is False


def test_expires_in_10_minutes():
    """expires_at should be ~10 minutes after created_at."""
    conf = make_confirmation("create_compare", "text", {})
    created = datetime.fromisoformat(conf["created_at"])
    expires = datetime.fromisoformat(conf["expires_at"])
    delta   = expires - created
    assert 595 <= delta.total_seconds() <= 605, f"Expected ~600s, got {delta.total_seconds()}"
