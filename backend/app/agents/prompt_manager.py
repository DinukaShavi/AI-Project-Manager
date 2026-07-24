import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Token budget defaults (8,000 token total budget target)
CATEGORY_BUDGETS = {
    "system_prompt": 1000, # Priority 1 - Immutable
    "user_query": 1000,    # Priority 2 - Immutable
    "jira_issues": 2000,   # Priority 3
    "slack_summaries": 1500, # Priority 4
    "vector_memories": 1500, # Priority 5
    "git_diffs": 1000      # Priority 6
}

PRIORITY_RANKINGS = {
    "system_prompt": 1,
    "user_query": 2,
    "jira_issues": 3,
    "slack_summaries": 4,
    "vector_memories": 5,
    "git_diffs": 6
}

def estimate_tokens(text: str) -> int:
    """
    Estimate token count for input text.
    Uses tiktoken if installed; falls back to exact word/character token ratio heuristic.
    """
    if not text:
        return 0
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Fallback token estimation heuristic (approx 4 chars or 0.75 words per token)
        words = text.split()
        return max(1, int(len(text) / 3.8))

@dataclass
class PromptContextItem:
    category: str # system_prompt, user_query, jira_issues, slack_summaries, vector_memories, git_diffs
    content: str
    priority: int = 10
    similarity_score: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

class PromptContextManager:
    """Manages prompt context construction by budget filtering, priority reranking, and sliding window trimming."""

    def __init__(self, max_total_tokens: int = 8000):
        self.max_total_tokens = max_total_tokens
        self.category_budgets = CATEGORY_BUDGETS.copy()

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def trim_item_to_budget(self, item: PromptContextItem, max_budget_tokens: int) -> str:
        """Apply category-specific trimming strategy when item exceeds allocated budget."""
        content = item.content
        current_tokens = self.count_tokens(content)
        if current_tokens <= max_budget_tokens:
            return content

        category = item.category.lower()

        # 1. System Prompt & User Query (Immutable)
        if category in ("system_prompt", "user_query"):
            return content

        # 2. Git Diffs: Trim raw diff text down to file change stats summary
        if category == "git_diffs":
            lines = content.splitlines()
            stats = [l for l in lines if l.startswith("diff --git") or "files changed" in l or "insertions" in l or "deletions" in l]
            trimmed = "\n".join(stats) if stats else content[:max_budget_tokens * 4]
            return f"[Git Diff Summary]\n{trimmed}"

        # 3. Vector Memories: Filter low similarity scores (< 0.8) and truncate
        if category == "vector_memories":
            if item.similarity_score < 0.8:
                return "" # Drop memories below 0.8 cosine similarity threshold
            words = content.split()
            target_words = int(max_budget_tokens * 0.75)
            return " ".join(words[:target_words]) + "..."

        # 4. Jira Issues & Slack Summaries: Sliding window / line truncation
        lines = content.splitlines()
        truncated_lines = []
        token_count = 0
        for line in lines:
            line_tokens = self.count_tokens(line)
            if token_count + line_tokens > max_budget_tokens:
                break
            truncated_lines.append(line)
            token_count += line_tokens

        return "\n".join(truncated_lines)

    def assemble_prompt(
        self,
        system_prompt: str,
        user_query: str,
        context_items: Optional[List[PromptContextItem]] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Assemble final context-augmented prompt ensuring strict 8,000 token budget allocation.
        """
        budget_limit = max_tokens or self.max_total_tokens
        items = context_items or []

        # Always include System Prompt (Priority 1) & User Query (Priority 2)
        sys_item = PromptContextItem("system_prompt", system_prompt, priority=1)
        query_item = PromptContextItem("user_query", user_query, priority=2)

        # Filter vector memories below similarity score threshold 0.8
        valid_context = [
            item for item in items
            if item.category != "vector_memories" or item.similarity_score >= 0.8
        ]

        # Sort context items by Priority Rank (1 highest -> 6 lowest)
        all_items = [sys_item, query_item] + valid_context
        all_items.sort(key=lambda x: PRIORITY_RANKINGS.get(x.category.lower(), x.priority))

        assembled_parts = []
        accumulated_tokens = 0

        for item in all_items:
            category = item.category.lower()
            allowed_cat_budget = self.category_budgets.get(category, 1000)
            
            # Trim item content to its category budget limit
            trimmed_text = self.trim_item_to_budget(item, allowed_cat_budget)
            if not trimmed_text:
                continue

            item_tokens = self.count_tokens(trimmed_text)

            # If adding this item exceeds total global token budget limit, trim it down further
            if accumulated_tokens + item_tokens > budget_limit:
                remaining_tokens = budget_limit - accumulated_tokens
                if remaining_tokens <= 50 and category not in ("system_prompt", "user_query"):
                    continue # Skip low priority items if remaining token headroom is minimal

                trimmed_text = self.trim_item_to_budget(
                    PromptContextItem(item.category, trimmed_text, item.priority, item.similarity_score),
                    remaining_tokens
                )
                item_tokens = self.count_tokens(trimmed_text)

            if item_tokens > 0:
                assembled_parts.append(f"--- [{item.category.upper()}] ---\n{trimmed_text}")
                accumulated_tokens += item_tokens

        return "\n\n".join(assembled_parts)


# Singleton Instance Manager
_prompt_manager_instance: Optional[PromptContextManager] = None

def get_prompt_manager() -> PromptContextManager:
    """Get global PromptContextManager singleton."""
    global _prompt_manager_instance
    if _prompt_manager_instance is None:
        _prompt_manager_instance = PromptContextManager()
    return _prompt_manager_instance
