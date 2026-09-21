import json
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent

MAX_ANALYZED_CHARS = 4000
MAX_TOPICS = 5


class _SentimentLLM(BaseAgent):
    """Minimal BaseAgent subclass whose only purpose is real `_llm_call`'s Claude/GPT-4o
    failover + circuit-breaker plumbing -- same carrier pattern as `_PlannerLLM`
    (`app/planning/planner.py`, Phase 71). `execute()` is never called."""

    def __init__(self):
        super().__init__(
            agent_name="SlackActivityAnalyzer",
            role="Team Discussion Sentiment & Topic Analyst",
            system_prompt="You analyze real team Slack messages for overall sentiment and discussion topics.",
        )

    async def execute(self, task_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError("_SentimentLLM is a carrier for _llm_call only.")


class SlackActivityService:
    """Real Slack channel activity analytics (Phase 72). `activity_by_hour`/`message_count`
    are deterministic computations over real message timestamps -- no LLM involved. Sentiment/
    topics are the one piece that genuinely needs NLP, via a real LLM call that falls back to
    an honest empty result (never a fabricated fixed number) whenever there's nothing to
    analyze or the call fails."""

    def __init__(self):
        self._llm = _SentimentLLM()

    @staticmethod
    def compute_activity_by_hour(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hour_counts: Counter = Counter()
        for m in messages:
            ts = m.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            hour_counts[dt.strftime("%H:00")] += 1
        return [{"hour": h, "messages": c} for h, c in sorted(hour_counts.items())]

    async def analyze_sentiment_and_topics(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Real LLM-derived sentiment (0.0 very negative -- 1.0 very positive) and topics over
        real message text. Returns honest None/[] -- never a fabricated fixed number -- when
        there's nothing to analyze or the LLM call fails/isn't configured/returns something
        unparseable, same fallback discipline as HTNPlanner.decompose_goal_async (Phase 71)."""
        texts = [m.get("text", "") for m in messages if m.get("text")]
        if not texts:
            return {"sentiment_score": None, "top_discussed_topics": []}

        joined = "\n".join(texts)[:MAX_ANALYZED_CHARS]
        system_prompt = (
            "You analyze a team's real Slack channel messages. Respond with ONLY a JSON "
            'object, no prose, no markdown fences: {"sentiment_score": <float from 0.0 (very '
            'negative) to 1.0 (very positive)>, "top_topics": [<up to 5 short topic phrases>]}.'
        )
        try:
            raw = await self._llm._llm_call(joined, system_prompt, task_category="output_reflection")
            parsed = json.loads(self._extract_json_object(raw))
            score = parsed.get("sentiment_score")
            topics = parsed.get("top_topics")
            if not isinstance(score, (int, float)) or not (0.0 <= score <= 1.0):
                score = None
            if not isinstance(topics, list):
                topics = []
            return {"sentiment_score": score, "top_discussed_topics": [str(t) for t in topics][:MAX_TOPICS]}
        except Exception:
            return {"sentiment_score": None, "top_discussed_topics": []}

    @staticmethod
    def _extract_json_object(text: str) -> str:
        text = text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in LLM response.")
        return text[start:end + 1]
