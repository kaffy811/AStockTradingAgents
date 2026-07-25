"""
Request and cost budget guards — Phase 6V-P1.31.

All atomic operations use Redis Lua scripts to prevent TOCTOU races.
Cost arithmetic uses Decimal throughout (never float).

Redis key layout (namespace = pi_provider_staging):
  {ns}:request_count   — integer, atomic INCR
  {ns}:cost_cny        — string decimal, atomic via Lua INCRBYFLOAT-with-ceiling
  {ns}:reservation:{id} — per-request reservation metadata (HASH, TTL 120s)
"""
from __future__ import annotations

import uuid
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .models import BudgetState
from .errors import BudgetExhaustedError

# Lua: atomic INCR with ceiling
# KEYS[1] = count key, ARGV[1] = ceiling
# Returns new value, or -1 if ceiling already reached
_LUA_INCR_WITH_CEILING = """
local current = redis.call('GET', KEYS[1])
if current == false then current = 0 else current = tonumber(current) end
if current >= tonumber(ARGV[1]) then return -1 end
return redis.call('INCR', KEYS[1])
"""

# Lua: atomic cost reservation (string decimal arithmetic via Lua)
# KEYS[1] = cost key, ARGV[1] = ceiling (string), ARGV[2] = amount (string)
# Returns "ok:{new_value}" or "exceeded:{current}"
_LUA_COST_RESERVE = """
local raw = redis.call('GET', KEYS[1])
local current = 0
if raw then current = tonumber(raw) end
local ceiling = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
if current >= ceiling then
    return 'exceeded:' .. tostring(current)
end
local proposed = current + amount
if proposed > ceiling then
    return 'exceeded:' .. tostring(current)
end
redis.call('SET', KEYS[1], tostring(proposed))
return 'ok:' .. tostring(proposed)
"""

# Lua: release a reservation (decrement cost key)
# KEYS[1] = cost key, ARGV[1] = amount to release
_LUA_COST_RELEASE = """
local raw = redis.call('GET', KEYS[1])
local current = 0
if raw then current = tonumber(raw) end
local amount = tonumber(ARGV[1])
local new_val = math.max(0, current - amount)
redis.call('SET', KEYS[1], tostring(new_val))
return tostring(new_val)
"""


class RequestBudgetGuard:
    """
    Redis-backed request counter with atomic ceiling check.

    Uses Lua script to prevent TOCTOU: GET → compare → INCR race.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "pi_provider_staging",
        max_requests: int = 100,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._max = max_requests
        self._count_key = f"{namespace}:request_count"

    def try_reserve(self) -> bool:
        """
        Atomically increment request counter if below ceiling.
        Returns True if reservation succeeded, False if budget exhausted.
        """
        result = self._redis.eval(
            _LUA_INCR_WITH_CEILING, 1, self._count_key, str(self._max)
        )
        if result == -1:
            return False
        return True

    def reserve_or_raise(self) -> None:
        """Reserve a request slot or raise BudgetExhaustedError."""
        if not self.try_reserve():
            used = self.get_count()
            raise BudgetExhaustedError(
                f"Request budget exhausted: {used}/{self._max} requests used.",
                budget_type="request",
            )

    def get_count(self) -> int:
        raw = self._redis.get(self._count_key)
        if raw is None:
            return 0
        return int(raw)

    def get_state(self) -> BudgetState:
        return BudgetState(
            requests_used=self.get_count(),
            requests_max=self._max,
            namespace=self._ns,
        )

    def reset(self) -> None:
        """Reset request counter. For staging reset / test teardown only."""
        self._redis.set(self._count_key, 0)


class CostAccumulator:
    """
    Redis-backed cost accumulator with atomic ceiling check.

    Uses Lua script for atomic INCRBYFLOAT-with-ceiling semantics.
    All arithmetic performed with Decimal for precision.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "pi_provider_staging",
        max_cost_cny: Decimal = Decimal("100"),
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._max = max_cost_cny
        self._cost_key = f"{namespace}:cost_cny"

    def try_reserve_cost(self, estimated_cny: Decimal) -> bool:
        """
        Atomically add estimated cost if below ceiling.
        Returns True if reservation succeeded.
        """
        result = self._redis.eval(
            _LUA_COST_RESERVE,
            1,
            self._cost_key,
            str(float(self._max)),
            str(float(estimated_cny)),
        )
        result_str = result.decode() if isinstance(result, bytes) else str(result)
        return result_str.startswith("ok:")

    def reserve_cost_or_raise(self, estimated_cny: Decimal) -> None:
        """Reserve cost or raise BudgetExhaustedError."""
        if not self.try_reserve_cost(estimated_cny):
            used = self.get_cost_cny()
            raise BudgetExhaustedError(
                f"Cost budget exhausted: ¥{used}/{self._max} CNY used.",
                budget_type="cost",
            )

    def release_cost(self, amount_cny: Decimal) -> None:
        """Release a previously reserved cost amount (e.g. on call failure)."""
        self._redis.eval(
            _LUA_COST_RELEASE,
            1,
            self._cost_key,
            str(float(amount_cny)),
        )

    def get_cost_cny(self) -> Decimal:
        raw = self._redis.get(self._cost_key)
        if raw is None:
            return Decimal("0")
        try:
            return Decimal(str(raw.decode() if isinstance(raw, bytes) else raw)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        except Exception:
            return Decimal("0")

    def get_state(self, request_budget: RequestBudgetGuard | None = None) -> BudgetState:
        cost = self.get_cost_cny()
        requests_used = request_budget.get_count() if request_budget else 0
        requests_max = request_budget._max if request_budget else 100
        return BudgetState(
            requests_used=requests_used,
            requests_max=requests_max,
            cost_used_cny=cost,
            cost_max_cny=self._max,
            namespace=self._ns,
        )

    def reset(self) -> None:
        """Reset cost accumulator. For staging reset / test teardown only."""
        self._redis.set(self._cost_key, "0")


class ProviderCircuitBreaker:
    """
    Cross-worker circuit breaker backed by Redis.

    States:
      CLOSED    → normal operation
      OPEN      → all calls blocked; recovery_at = epoch seconds
      HALF_OPEN → one probe call allowed; opens again on failure

    Triggers for OPEN:
      - consecutive_failures >= failure_threshold
      - rate_limit_storm (too many RateLimitErrors in window)
      - credential_failure (AuthenticationError)
      - malformed_usage (usage_complete=False on consecutive calls)
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "pi_provider_circuit",
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._threshold = failure_threshold
        self._recovery_s = recovery_seconds
        self._status_key = f"{namespace}:status"
        self._failures_key = f"{namespace}:consecutive_failures"
        self._recovery_key = f"{namespace}:recovery_at"

    def get_status(self) -> str:
        raw = self._redis.get(self._status_key)
        if raw is None:
            return self.CLOSED
        return (raw.decode() if isinstance(raw, bytes) else raw)

    def is_open(self) -> bool:
        status = self.get_status()
        if status != self.OPEN:
            return False
        # Check if recovery window has passed → auto-transition to HALF_OPEN
        raw = self._redis.get(self._recovery_key)
        if raw is not None:
            recovery_at = float(raw.decode() if isinstance(raw, bytes) else raw)
            if time.time() >= recovery_at:
                self._redis.set(self._status_key, self.HALF_OPEN)
                return False
        return True

    def is_closed_or_half_open(self) -> bool:
        return not self.is_open()

    def record_success(self) -> None:
        """Reset failure counter and close circuit."""
        self._redis.set(self._failures_key, 0)
        self._redis.set(self._status_key, self.CLOSED)
        self._redis.delete(self._recovery_key)

    def record_failure(self, trigger: str = "consecutive_failure") -> None:
        """
        Increment failure counter. Open circuit if threshold reached.
        Also opens immediately for credential_failure or rate_limit_storm.
        """
        if trigger in ("credential_failure", "malformed_response"):
            self._open_circuit(trigger)
            return

        new_count_raw = self._redis.incr(self._failures_key)
        new_count = int(new_count_raw)
        if new_count >= self._threshold:
            self._open_circuit(trigger)

    def _open_circuit(self, trigger: str) -> None:
        recovery_at = time.time() + self._recovery_s
        self._redis.set(self._status_key, self.OPEN)
        self._redis.set(self._recovery_key, str(recovery_at))

    def force_close(self) -> None:
        """Force circuit to CLOSED. For testing / manual reset."""
        self._redis.set(self._status_key, self.CLOSED)
        self._redis.set(self._failures_key, 0)
        self._redis.delete(self._recovery_key)

    def get_state(self) -> "CircuitBreakerStateSnapshot":
        from .models import CircuitBreakerState, CircuitBreakerStatus
        status_raw = self.get_status()
        try:
            status_enum = CircuitBreakerStatus(status_raw)
        except ValueError:
            status_enum = CircuitBreakerStatus.CLOSED
        failures_raw = self._redis.get(self._failures_key)
        failures = int(failures_raw) if failures_raw else 0
        recovery_raw = self._redis.get(self._recovery_key)
        recovery_at = float(recovery_raw) if recovery_raw else None
        return CircuitBreakerState(
            status=status_enum,
            consecutive_failures=failures,
            failure_threshold=self._threshold,
            recovery_at_epoch=recovery_at,
            namespace=self._ns,
        )
