"""
Cross-worker concurrency semaphore — Phase 6V-P1.31.

Uses Redis lease-based semaphore: each slot is a SETNX with TTL.
Crash recovery: TTL ensures abandoned leases are automatically released.
"""
from __future__ import annotations

import uuid
import time
from contextlib import contextmanager
from typing import Any, Generator

from .models import ConcurrencyState
from .errors import ConcurrencyLimitError

# Lua: try to acquire one lease slot
# KEYS[1..N] = slot keys for slots 0..max_slots-1, ARGV[1] = owner, ARGV[2] = ttl seconds
# Returns slot index (0-based) or -1 if all full
_LUA_ACQUIRE_SLOT = """
local owner = ARGV[1]
local ttl = tonumber(ARGV[2])
for i = 1, #KEYS do
    local key = KEYS[i]
    local result = redis.call('SET', key, owner, 'NX', 'EX', ttl)
    if result then
        return i - 1
    end
end
return -1
"""

# Lua: release a specific slot (only if owned by caller)
# KEYS[1] = slot key, ARGV[1] = owner token
_LUA_RELEASE_SLOT = """
local current = redis.call('GET', KEYS[1])
if current == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""


class LeaseSemaphore:
    """
    Redis-based distributed semaphore using lease slots.

    Each slot is a separate Redis key. Lua script atomically checks all slots
    and acquires the first empty one. TTL provides crash recovery.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "pi_provider_concurrency",
        max_slots: int = 2,
        lease_ttl_seconds: int = 60,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._max = max_slots
        self._ttl = lease_ttl_seconds
        self._slot_keys = [f"{namespace}:slot:{i}" for i in range(max_slots)]

    def try_acquire(self) -> tuple[bool, str | None, int | None]:
        """
        Try to acquire a concurrency slot.
        Returns (acquired, owner_token, slot_index).
        """
        owner = str(uuid.uuid4())
        result = self._redis.eval(
            _LUA_ACQUIRE_SLOT,
            len(self._slot_keys),
            *self._slot_keys,
            owner,
            str(self._ttl),
        )
        slot_idx = int(result)
        if slot_idx == -1:
            return False, None, None
        return True, owner, slot_idx

    def acquire_or_raise(self) -> tuple[str, int]:
        """Acquire a slot or raise ConcurrencyLimitError. Returns (owner_token, slot_idx)."""
        acquired, owner, slot_idx = self.try_acquire()
        if not acquired:
            active = self.get_active_count()
            raise ConcurrencyLimitError(
                f"Concurrency limit reached: {active}/{self._max} slots active.",
                active_slots=active,
            )
        return owner, slot_idx  # type: ignore[return-value]

    def release(self, slot_idx: int, owner_token: str) -> bool:
        """Release a specific slot. Returns True if successfully released."""
        if slot_idx < 0 or slot_idx >= len(self._slot_keys):
            return False
        result = self._redis.eval(
            _LUA_RELEASE_SLOT,
            1,
            self._slot_keys[slot_idx],
            owner_token,
        )
        return int(result) == 1

    def get_active_count(self) -> int:
        """Count how many slots are currently occupied."""
        count = 0
        for key in self._slot_keys:
            if self._redis.exists(key):
                count += 1
        return count

    def get_state(self) -> ConcurrencyState:
        return ConcurrencyState(
            active_slots=self.get_active_count(),
            max_slots=self._max,
            namespace=self._ns,
        )

    @contextmanager
    def acquire_context(self) -> Generator[tuple[str, int], None, None]:
        """Context manager: acquire on enter, release on exit (even on error)."""
        owner, slot_idx = self.acquire_or_raise()
        try:
            yield owner, slot_idx
        finally:
            self.release(slot_idx, owner)
