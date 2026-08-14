import asyncio
import httpx
from unittest.mock import patch

from app.core.config import settings
from app.agents.tpm import TechnicalPMAgent
from app.core.circuit_breaker import _llm_circuit_breakers


def _reset_llm_circuit_breakers():
    """Circuit breakers are process-wide singletons keyed by model name; clear them between
    sub-tests so a circuit opened by one scenario doesn't fast-fail (or fast-succeed) the next."""
    _llm_circuit_breakers.clear()


async def test_llm_integration_flow():
    print("Initializing Real LLM Provider Integration (Claude/GPT-4o via ModelRouter) validation tests...")

    original_anthropic_key = settings.ANTHROPIC_API_KEY
    original_openai_key = settings.OPENAI_API_KEY

    try:
        # 1. No provider configured (the actual default in this environment) — must still
        # produce the rich synthetic fallback response, exactly as before this change.
        print("\nTest 1: Verifying unconfigured providers fall back to synthetic reasoning...")
        settings.ANTHROPIC_API_KEY = None
        settings.OPENAI_API_KEY = None
        _reset_llm_circuit_breakers()

        agent = TechnicalPMAgent()
        result = await agent.execute("Review sprint velocity", {})
        assert "[TechnicalPMAgent — Sprint Analysis]" in result["analysis"], \
            f"Expected synthetic fallback marker, got: {result['analysis'][:200]}"
        print("SUCCESS: No credentials configured — synthetic fallback used, matching prior behavior.")

        # 2. ANTHROPIC_API_KEY configured, Anthropic Messages API mocked to succeed — the
        # agent must return the REAL provider's response text, not synthetic reasoning.
        print("\nTest 2: Verifying a configured Anthropic key routes through the real Messages API...")
        settings.ANTHROPIC_API_KEY = "sk-ant-test-key-123"
        settings.OPENAI_API_KEY = None
        _reset_llm_circuit_breakers()

        async def fake_anthropic_success(self, url, **kwargs):
            assert "api.anthropic.com/v1/messages" in str(url)
            assert kwargs["headers"]["x-api-key"] == "sk-ant-test-key-123"
            assert kwargs["json"]["model"] == "claude-3-5-sonnet-20241022"
            return httpx.Response(
                200, request=httpx.Request("POST", str(url)),
                json={"content": [{"type": "text", "text": "REAL_CLAUDE_MOCKED_RESPONSE"}]},
            )

        with patch.object(httpx.AsyncClient, "post", new=fake_anthropic_success):
            result = await agent.execute("Review sprint velocity", {})
        assert result["analysis"] == "REAL_CLAUDE_MOCKED_RESPONSE", \
            f"Expected the mocked Claude response verbatim, got: {result['analysis']}"
        print("SUCCESS: Real Anthropic request construction and response parsing verified.")

        # 3. Anthropic call fails (mocked 500), OpenAI configured and mocked to succeed —
        # ModelRouter must fail over to GPT-4o rather than skipping straight to synthetic.
        print("\nTest 3: Verifying failover from a failing Claude call to a working GPT-4o call...")
        settings.ANTHROPIC_API_KEY = "sk-ant-test-key-123"
        settings.OPENAI_API_KEY = "sk-openai-test-key-456"
        _reset_llm_circuit_breakers()

        async def fake_claude_fails_gpt_succeeds(self, url, **kwargs):
            if "api.anthropic.com" in str(url):
                return httpx.Response(500, request=httpx.Request("POST", str(url)), text="Internal Server Error")
            if "api.openai.com/v1/chat/completions" in str(url):
                assert kwargs["headers"]["Authorization"] == "Bearer sk-openai-test-key-456"
                assert kwargs["json"]["model"] == "gpt-4o"
                return httpx.Response(
                    200, request=httpx.Request("POST", str(url)),
                    json={"choices": [{"message": {"content": "REAL_GPT4O_MOCKED_RESPONSE"}}]},
                )
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(httpx.AsyncClient, "post", new=fake_claude_fails_gpt_succeeds):
            result = await agent.execute("Review sprint velocity", {})
        assert result["analysis"] == "REAL_GPT4O_MOCKED_RESPONSE", \
            f"Expected failover to the mocked GPT-4o response, got: {result['analysis']}"
        print("SUCCESS: ModelRouter correctly failed over from Claude to GPT-4o on a real provider error.")

        # 4. Both providers configured but both fail — must still degrade to synthetic
        # reasoning rather than raising an unhandled exception up through the agent.
        print("\nTest 4: Verifying both-providers-failing still degrades to synthetic reasoning...")
        _reset_llm_circuit_breakers()

        async def fake_both_fail(self, url, **kwargs):
            return httpx.Response(503, request=httpx.Request("POST", str(url)), text="Service Unavailable")

        with patch.object(httpx.AsyncClient, "post", new=fake_both_fail):
            result = await agent.execute("Review sprint velocity", {})
        assert "[TechnicalPMAgent — Sprint Analysis]" in result["analysis"], \
            f"Expected synthetic fallback after total provider failure, got: {result['analysis'][:200]}"
        print("SUCCESS: Total provider failure correctly degraded to synthetic reasoning, not an exception.")

    finally:
        settings.ANTHROPIC_API_KEY = original_anthropic_key
        settings.OPENAI_API_KEY = original_openai_key
        _reset_llm_circuit_breakers()

    print("\nAll Real LLM Provider Integration tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_llm_integration_flow())
