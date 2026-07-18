from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.base import BaseTool
from app.services.context import ContextEngineService

class ContextSearchTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="context_search",
            description="Execute semantic vector search over project documentation, PRs, issues, and context memory.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "organization_id": {"type": "string", "description": "Organization UUID"},
                    "query": {"type": "string", "description": "Natural language semantic query"},
                    "top_k": {"type": "integer", "description": "Number of top context chunks to retrieve", "default": 5}
                },
                "required": ["organization_id", "query"]
            }
        )

    async def execute(self, params: Dict[str, Any], session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        self.validate_parameters(params)
        org_id = UUID(str(params["organization_id"]))
        query_text = params["query"]
        top_k = params.get("top_k", 5)

        if not session:
            # Fallback mock when no session is injected
            return {
                "status": "success",
                "query": query_text,
                "results_count": 1,
                "results": [
                    {
                        "chunk_id": "mock-chunk-1",
                        "source_type": "doc",
                        "content": f"Relevant context snippet for query '{query_text}'",
                        "score": 0.88
                    }
                ]
            }

        service = ContextEngineService(session)
        results = await service.search_context(
            organization_id=org_id,
            query_text=query_text,
            top_k=top_k
        )
        return {
            "status": "success",
            "query": query_text,
            "results_count": len(results),
            "results": results
        }
