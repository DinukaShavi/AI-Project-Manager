import asyncio
import time
import random
from enum import Enum
from typing import Callable, Coroutine, Any, Optional, List, Tuple
from app.core.config import settings

class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreakerConfig:
    def __init__(
        self,
        failure_threshold_pct: float = 0.50,
        window_seconds: float = 10.0,
        recovery_timeout_seconds: float = 60.0,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 10.0,
        connect_timeout_seconds: float = 10.0,
        write_timeout_seconds: float = 30.0
    ):
        self.failure_threshold_pct = failure_threshold_pct
        self.window_seconds = window_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.write_timeout_seconds = write_timeout_seconds

class CircuitBreaker:
    """Production Circuit Breaker State Machine & Exponential Backoff Router."""

    def __init__(self, name: str = "LLMCircuitBreaker", config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.open_since: Optional[float] = None
        self._history: List[Tuple[float, bool]] = [] # List of (timestamp, success_flag)

    def _clean_history(self, now: float) -> None:
        """Purge records older than rolling window_seconds."""
        cutoff = now - self.config.window_seconds
        self._history = [h for h in self._history if h[0] >= cutoff]

    def can_execute(self) -> Tuple[bool, str]:
        """Check if execution can proceed or if fallback model should be routed."""
        now = time.time()
        self._clean_history(now)

        if self.state == CircuitBreakerState.CLOSED:
            return True, "primary"

        if self.state == CircuitBreakerState.OPEN:
            if self.open_since and (now - self.open_since) >= self.config.recovery_timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                return True, "primary_probe"
            return False, "fallback"

        if self.state == CircuitBreakerState.HALF_OPEN:
            return True, "primary_probe"

        return False, "fallback"

    def record_success(self) -> None:
        """Record successful call and reset circuit if probing in HALF_OPEN state."""
        now = time.time()
        self._clean_history(now)
        self._history.append((now, True))

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            self.open_since = None
            self._history.clear()

    def record_failure(self) -> None:
        """Record failure and open circuit if error rate exceeds failure_threshold_pct."""
        now = time.time()
        self._clean_history(now)
        self._history.append((now, False))

        total_requests = len(self._history)
        if total_requests >= 2: # Require minimum sample size of 2 to open circuit
            failures = sum(1 for _, success in self._history if not success)
            error_rate = failures / total_requests

            if error_rate >= self.config.failure_threshold_pct:
                self.state = CircuitBreakerState.OPEN
                self.open_since = now

    def calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter:
        Delay = min(Cap, Base * 2^attempt) + jitter
        """
        exponent_delay = self.config.base_delay_seconds * (2 ** attempt)
        capped_delay = min(self.config.max_delay_seconds, exponent_delay)
        jitter = random.uniform(0.0, 0.1 * capped_delay)
        return capped_delay + jitter

    async def call_with_circuit_breaker(
        self,
        coro_fn: Callable[[], Coroutine[Any, Any, Any]],
        fallback_fn: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None
    ) -> Any:
        """
        Execute coroutine wrapped with Circuit Breaker inspection, timeout, exponential backoff, and fallback routing.
        """
        can_exec, route = self.can_execute()

        if not can_exec:
            if fallback_fn:
                return await fallback_fn()
            raise RuntimeError(f"CircuitBreaker '{self.name}' is OPEN. Requests blocked to primary model.")

        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                # Enforce total execution timeout (connect 10s, write/read 30s)
                result = await asyncio.wait_for(
                    coro_fn(),
                    timeout=self.config.write_timeout_seconds
                )
                self.record_success()
                return result

            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    backoff = self.calculate_backoff_delay(attempt)
                    await asyncio.sleep(backoff)

        # All retries exhausted
        self.record_failure()

        if fallback_fn:
            return await fallback_fn()

        raise RuntimeError(f"CircuitBreaker '{self.name}' call failed after {self.config.max_retries} attempts: {last_exception}")


# Singleton Instance Manager
_llm_circuit_breaker: Optional[CircuitBreaker] = None

def get_circuit_breaker() -> CircuitBreaker:
    """Get global LLM Circuit Breaker singleton instance."""
    global _llm_circuit_breaker
    if _llm_circuit_breaker is None:
        _llm_circuit_breaker = CircuitBreaker(name="GlobalLLMCircuitBreaker")
    return _llm_circuit_breaker
