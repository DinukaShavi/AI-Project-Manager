import asyncio
from app.core.distributed_lock import get_lock_manager, DistributedLockManager

async def test_distributed_lock_flow():
    print("Initializing Distributed Lock & Redlock validation tests...")
    lock_mgr = get_lock_manager()
    resource_id = "project:101:sprint_update"

    # 1. Test Acquire & Release Lock
    print("\nTest 1: Testing lock acquisition & atomic token release...")
    token1 = await lock_mgr.acquire_lock(resource_id, ttl_seconds=10)
    assert token1 is not None
    
    # Attempting to acquire same resource with active lock should fail
    token_fail = await lock_mgr.acquire_lock(resource_id, ttl_seconds=10)
    assert token_fail is None

    # Releasing with wrong token should fail
    released_wrong = await lock_mgr.release_lock(resource_id, "wrong_token_123")
    assert released_wrong is False

    # Releasing with correct token should succeed
    released = await lock_mgr.release_lock(resource_id, token1)
    assert released is True
    print("SUCCESS: Lock acquisition, collision blocking, and atomic release verified.")

    # 2. Test Lock Lease Extension
    print("\nTest 2: Testing lock lease extension...")
    token2 = await lock_mgr.acquire_lock(resource_id, ttl_seconds=5)
    assert token2 is not None

    extended = await lock_mgr.extend_lease(resource_id, token2, ttl_seconds=15)
    assert extended is True

    await lock_mgr.release_lock(resource_id, token2)
    print("SUCCESS: Lock lease extension verified.")

    # 3. Test Async Context Manager Lock & Auto Renewal
    print("\nTest 3: Testing async context manager with auto lease renewal...")
    async with lock_mgr.lock(resource_id, ttl_seconds=3, max_wait_seconds=2.0) as lock_token:
        assert lock_token is not None
        # Verify inside context resource is locked
        tok_coll = await lock_mgr.acquire_lock(resource_id, ttl_seconds=2)
        assert tok_coll is None
        await asyncio.sleep(0.5)

    # After context exit resource should be released
    tok_after = await lock_mgr.acquire_lock(resource_id, ttl_seconds=5)
    assert tok_after is not None
    await lock_mgr.release_lock(resource_id, tok_after)
    print("SUCCESS: Async context manager & auto-release verified.")

    # 4. Test Lock Timeout Exceeded Exception
    print("\nTest 4: Testing lock acquisition timeout exception...")
    tok_hold = await lock_mgr.acquire_lock(resource_id, ttl_seconds=10)
    
    timeout_caught = False
    try:
        async with lock_mgr.lock(resource_id, max_wait_seconds=0.5):
            pass
    except TimeoutError as te:
        timeout_caught = True
        assert "Could not acquire distributed lock" in str(te)

    assert timeout_caught is True
    await lock_mgr.release_lock(resource_id, tok_hold)
    print("SUCCESS: Lock timeout exception verified.")

    print("\nAll Distributed Lock System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_distributed_lock_flow())
