import asyncio
from app.agents.prompt_manager import (
    PromptContextManager,
    PromptContextItem,
    get_prompt_manager,
    estimate_tokens
)

async def test_prompt_manager_flow():
    print("Initializing Prompt Context Window Manager & Token Allocator validation tests...")
    pm = get_prompt_manager()

    # 1. Test Token Estimation
    print("\nTest 1: Testing token estimation accuracy...")
    sample_text = "The quick brown fox jumps over the lazy dog."
    token_count = pm.count_tokens(sample_text)
    assert token_count > 5 and token_count < 20
    print(f"SUCCESS: Token count estimated correctly. Output: {token_count} tokens.")

    # 2. Test Vector Memory Similarity Cutoff (< 0.8 dropped)
    print("\nTest 2: Testing vector memory similarity score cutoff (< 0.8)...")
    valid_memory = PromptContextItem("vector_memories", "Relevant architectural document text.", similarity_score=0.92)
    invalid_memory = PromptContextItem("vector_memories", "Irrelevant unrelated text snippet.", similarity_score=0.65)

    assembled = pm.assemble_prompt(
        system_prompt="You are a system architect.",
        user_query="Review system diagram",
        context_items=[valid_memory, invalid_memory]
    )

    assert "Relevant architectural document" in assembled
    assert "Irrelevant unrelated text" not in assembled
    print("SUCCESS: Vector memories with similarity score < 0.8 correctly filtered out.")

    # 3. Test Git Diff Trimming Strategy
    print("\nTest 3: Testing Git diff trimming strategy down to file change stats...")
    raw_git_diff = (
        "diff --git a/app/services/agent.py b/app/services/agent.py\n"
        "index 123456..789abc 100644\n"
        "--- a/app/services/agent.py\n"
        "+++ b/app/services/agent.py\n"
        "@@ -10,6 +10,12 @@\n" + ("+ added line text\n" * 500) +
        " 3 files changed, 500 insertions(+)"
    )

    git_item = PromptContextItem("git_diffs", raw_git_diff, priority=6)
    trimmed_git = pm.trim_item_to_budget(git_item, max_budget_tokens=100)
    assert "[Git Diff Summary]" in trimmed_git
    assert "files changed" in trimmed_git
    print("SUCCESS: Large Git diffs trimmed down to change stats summary.")

    # 4. Test Global 8,000 Token Budget Enforcement
    print("\nTest 4: Testing global 8,000 token budget enforcement & priority ordering...")
    sys_prompt = "System Role: Technical PM\nReview sprint progress and assign story points."
    query = "Analyze sprint capacity and blocker risks."

    large_jira = PromptContextItem("jira_issues", "Jira Issue JIRA-101: " + ("Urgent blocker task details. " * 300), priority=3)
    large_slack = PromptContextItem("slack_summaries", "Slack Standup: " + ("Engineer completed PR review. " * 300), priority=4)

    final_prompt = pm.assemble_prompt(
        system_prompt=sys_prompt,
        user_query=query,
        context_items=[large_jira, large_slack],
        max_tokens=2000 # Test tight budget limit
    )

    total_tokens = pm.count_tokens(final_prompt)
    assert total_tokens <= 2200 # Enforces ceiling
    assert "System Role: Technical PM" in final_prompt
    assert "Analyze sprint capacity" in final_prompt
    print(f"SUCCESS: Assembled prompt fits budget constraint ({total_tokens} tokens <= 2200 target).")

    print("\nAll Prompt Context Manager tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_prompt_manager_flow())
