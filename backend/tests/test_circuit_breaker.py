import asyncio
import time
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    get_circuit_breaker
)

async def test_circuit_breaker_flow():
    print("Initializing LLM Circuit Breaker & Exponential Backoff validation tests...")

    # 1. Test Exponential Backoff Calculation
    print("\nTest 1: Testing exponential backoff calculation...")
    cb = CircuitBreaker("TestCB", config=CircuitBreakerConfig(base_delay_seconds=0.1, max_delay_seconds=1.0))
    d0 = cb.calculate_backoff_delay(0) # 0.1s + jitter
    d1 = cb.calculate_backoff_delay(1) # 0.2s + jitter
    d2 = cb.calculate_backoff_delay(2) # 0.4s + jitter
    assert d0 >= 0.1 and d0 <= 0.15
    assert d1 >= 0.2 and d1 <= 0.25
    assert d2 >= 0.4 and d2 <= 0.45
    print("SUCCESS: Exponential backoff delay calculation formula verified.")

    # 2. Test State Transitions: CLOSED -> OPEN (50%+ error rate)
    print("\nTest 2: Testing CLOSED -> OPEN state transition upon failure threshold...")
    cb2 = CircuitBreaker("ThresholdCB", config=CircuitBreakerConfig(failure_threshold_pct=0.50, window_seconds=5.0, recovery_timeout_seconds=0.5))
    can_exec, route = cb2.can_execute()
    assert cb2.state == CircuitBreakerState.CLOSED
    assert can_exec is True
    assert route == "primary"

    # Record 1 success and 2 failures (66% error rate > 50%)
    cb2.record_success()
    cb2.record_failure()
    cb2.record_failure()

    assert cb2.state == CircuitBreakerState.OPEN
    can_exec_open, route_open = cb2.can_execute()
    assert can_exec_open is False
    assert route_open == "fallback"
    print("SUCCESS: Error rate threshold triggered CLOSED -> OPEN transition.")

    # 3. Test Half-Open Probe Recovery & Transition back to CLOSED
    print("\nTest 3: Testing OPEN -> HALF_OPEN -> CLOSED recovery flow...")
    await asyncio.sleep(0.6) # Wait out recovery timeout
    can_exec_probe, route_probe = cb2.can_execute()
    assert cb2.state == CircuitBreakerState.HALF_OPEN
    assert can_exec_probe is True
    assert route_probe == "primary_probe"

    # Probing call succeeds -> closes circuit
    cb2.record_success()
    assert cb2.state == CircuitBreakerState.CLOSED
    print("SUCCESS: Half-open probe success restored circuit to CLOSED.")

    # 4. Test Wrapped Execution & Automatic Model Fallback
    print("\nTest 4: Testing call_with_circuit_breaker wrapped execution & fallback...")
    async def failing_remote():
        raise ConnectionError("Remote LLM API timeout")

    async def fallback_model():
        return "Synthetic Fallback Reasoner Output"

    cb3 = CircuitBreaker("FallbackCB", config=CircuitBreakerConfig(max_retries=2, base_delay_seconds=0.01))
    result = await cb3.call_with_circuit_breaker(
        coro_fn=failing_remote,
        fallback_fn=fallback_model
    )
    assert result == "Synthetic Fallback Reasoner Output"
    print("SUCCESS: Automatic fallback triggered when primary remote call fails.")

    print("\nAll LLM Circuit Breaker System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_circuit_breaker_flow())
