import asyncio
from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.workflows.dag import WorkflowDAG, WorkflowNode
from app.services.agent import AgentService
from app.services.tool import ToolService

class WorkflowExecutor:
    def __init__(
        self,
        session: AsyncSession,
        organization_id: UUID,
        project_id: Optional[UUID] = None
    ):
        """Workflow Executor orchestrating DAG step execution and context state propagation."""
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id
        self.agent_service = AgentService(session)
        self.tool_service = ToolService(session)

    async def execute_dag(
        self,
        dag: WorkflowDAG,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute DAG nodes level by level passing output state across steps."""
        levels = dag.get_execution_levels()
        context_state = dict(initial_context or {})
        node_outputs: Dict[str, Any] = {}

        for level in levels:
            # Execute nodes in current level asynchronously
            level_tasks = [
                self._execute_node(node, context_state, node_outputs)
                for node in level
            ]
            results = await asyncio.gather(*level_tasks, return_exceptions=True)

            # Process node execution results
            for node, res in zip(level, results):
                if isinstance(res, Exception):
                    raise ValueError(f"Workflow execution failed at node '{node.node_id}': {str(res)}")
                
                node_outputs[node.node_id] = res
                context_state[node.node_id] = res

        return {
            "status": "completed",
            "node_outputs": node_outputs,
            "final_context": context_state
        }

    async def _execute_node(
        self,
        node: WorkflowNode,
        context_state: Dict[str, Any],
        previous_outputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an individual node step (Agent persona or Tool)."""
        # Inject outputs from dependent parent nodes
        step_context = dict(context_state)
        for dep in node.depends_on:
            if dep in previous_outputs:
                step_context[f"parent_{dep}"] = previous_outputs[dep]

        if node.step_type == "agent":
            task_prompt = node.input_params.get("task", f"Execute task for step '{node.name}'")
            execution = await self.agent_service.execute_agent(
                agent_type=node.target,
                task_input=task_prompt,
                organization_id=self.organization_id,
                project_id=self.project_id,
                context=step_context
            )
            return execution.output_payload

        elif node.step_type == "tool":
            # Combine static input params with dynamic context
            params = dict(node.input_params)

            # Inject organization_id into tool params if required by tool
            if "organization_id" not in params:
                params["organization_id"] = str(self.organization_id)

            tool_result = await self.tool_service.execute_tool(
                tool_name=node.target,
                parameters=params
            )
            return tool_result
        else:
            raise ValueError(f"Unsupported workflow step type '{node.step_type}' for node '{node.node_id}'.")
