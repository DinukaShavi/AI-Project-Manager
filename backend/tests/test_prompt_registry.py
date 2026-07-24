import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.agents.prompt_registry import (
    get_prompt_registry,
    PromptRegistry,
    PromptVersion
)

async def test_prompt_registry_flow():
    print("Initializing Prompt Registry, Canary A/B Router & Rollback validation tests...")
    registry = get_prompt_registry()

    # 1. Test Prompt Registration
    print("\nTest 1: Testing SemVer prompt version registration...")
    key = "test_agent_prompt"
    p1 = registry.register_prompt_version(key, "v1.0.0", "Stable Prompt v1.0.0", is_canary=False)
    p2 = registry.register_prompt_version(key, "v1.1.0-canary", "Canary Prompt v1.1.0", is_canary=True, traffic_weight=1.0) # 100% traffic weight for test determinism
    assert p1.version == "v1.0.0"
    assert p2.version == "v1.1.0-canary"
    print("SUCCESS: SemVer stable and canary prompt versions registered.")

    # 2. Test A/B Traffic Routing
    print("\nTest 2: Testing Canary A/B traffic routing...")
    ver, content = registry.get_active_prompt(key)
    assert ver == "v1.1.0-canary"
    assert "Canary Prompt v1.1.0" in content
    print("SUCCESS: Active prompt routed to canary version based on traffic weight.")

    # 3. Test Outcome Recording & Automated Rollback Trigger (15%+ Failure Rate)
    print("\nTest 3: Testing automated rollback trigger upon failure threshold breach...")
    for _ in range(3):
        registry.record_run_outcome(key, "v1.1.0-canary", success=False)
    for _ in range(2):
        registry.record_run_outcome(key, "v1.1.0-canary", success=True)

    # 3 failures / 5 runs = 60% failure rate > 15% threshold -> triggers auto-rollback!
    rollback_ver, _ = registry.get_active_prompt(key)
    assert rollback_ver == "v1.0.0"
    print("SUCCESS: Automated rollback triggered; canary deactivated and stable v1.0.0 restored.")

    # 4. Test REST API Endpoints
    print("\nTest 4: Testing Prompt Management HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/v1/prompts/tpm_system_prompt
        res_get = await client.get("/api/v1/prompts/tpm_system_prompt")
        assert res_get.status_code == 200
        assert res_get.json()["active_version"] == "v1.0.0"

        # POST /api/v1/prompts/register
        res_reg = await client.post(
            "/api/v1/prompts/register",
            json={
                "prompt_key": "tpm_system_prompt",
                "version": "v1.2.0-canary",
                "content": "Canary v1.2.0 test content",
                "is_canary": True,
                "traffic_weight": 0.50
            }
        )
        assert res_reg.status_code == 201
        assert res_reg.json()["version"] == "v1.2.0-canary"

        # POST /api/v1/prompts/tpm_system_prompt/rollback
        res_roll = await client.post("/api/v1/prompts/tpm_system_prompt/rollback?failed_version=v1.2.0-canary")
        assert res_roll.status_code == 200
        assert res_roll.json()["restored_version"] == "v1.0.0"

        print("SUCCESS: Prompt management REST API endpoints verified.")

    print("\nAll Prompt Registry & Rollback Engine tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_prompt_registry_flow())
