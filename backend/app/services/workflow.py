from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.workflow import WorkflowDefinition, WorkflowExecution
from app.workflows.dag import WorkflowDAG, WorkflowNode
from app.workflows.executor import WorkflowExecutor

class WorkflowService:
    def __init__(self, session: AsyncSession):
        """Workflow Service managing definitions, DAG templates, and execution persistence."""
        self.session = session

    async def create_definition(
        self,
        name: str,
        description: str,
        dag: WorkflowDAG,
        organization_id: UUID,
        is_template: bool = False
    ) -> WorkflowDefinition:
        """Persist a WorkflowDefinition record in PostgreSQL."""
        dag.validate_dag()
        dag_dict = {
            "nodes": [node.to_dict() for node in dag.nodes.values()]
        }
        wf_def = WorkflowDefinition(
            organization_id=organization_id,
            name=name,
            description=description,
            dag_structure=dag_dict,
            is_active=True
        )
        self.session.add(wf_def)
        await self.session.commit()
        await self.session.refresh(wf_def)
        return wf_def

    async def list_definitions(self, organization_id: UUID) -> List[WorkflowDefinition]:
        """Fetch all workflow definitions for an organization."""
        res = await self.session.execute(
            select(WorkflowDefinition).where(
                (WorkflowDefinition.organization_id == organization_id) | (WorkflowDefinition.organization_id == None)
            )
        )
        return res.scalars().all()

    def get_sprint_review_template_dag(self) -> WorkflowDAG:
        """Factory for pre-built Sprint Review Multi-Agent DAG."""
        dag = WorkflowDAG()
        dag.add_node(WorkflowNode(
            node_id="tpm_analysis",
            name="Sprint Velocity & Blocker Analysis",
            step_type="agent",
            target="tpm",
            input_params={"task": "Analyze sprint progress, developer velocity, and open blockers."}
        ))
        dag.add_node(WorkflowNode(
            node_id="code_quality",
            name="Code Quality & Diff Inspection",
            step_type="agent",
            target="code_analyst",
            input_params={"task": "Evaluate pull request diffs, code quality, and test coverage."},
            depends_on=["tpm_analysis"]
        ))
        dag.add_node(WorkflowNode(
            node_id="risk_evaluation",
            name="Delivery Risk & Scope Creep Assessment",
            step_type="agent",
            target="risk_manager",
            input_params={"task": "Assess schedule risks, delivery delays, and scope creep mitigations."},
            depends_on=["code_quality"]
        ))
        return dag

    def get_architecture_audit_template_dag(self) -> WorkflowDAG:
        """Factory for pre-built Architecture Audit Multi-Agent DAG."""
        dag = WorkflowDAG()
        dag.add_node(WorkflowNode(
            node_id="arch_review",
            name="System Architecture & API Contract Review",
            step_type="agent",
            target="architect",
            input_params={"task": "Audit system design patterns and REST/event API contract consistency."}
        ))
        dag.add_node(WorkflowNode(
            node_id="code_audit",
            name="Code Architecture Implementation Audit",
            step_type="agent",
            target="code_analyst",
            input_params={"task": "Audit implementation code for Clean Architecture compliance."},
            depends_on=["arch_review"]
        ))
        return dag

    async def execute_workflow(
        self,
        dag: WorkflowDAG,
        organization_id: UUID,
        project_id: Optional[UUID] = None,
        definition_id: Optional[UUID] = None,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """Execute WorkflowDAG and record execution in PostgreSQL workflow_executions table."""
        executor = WorkflowExecutor(self.session, organization_id, project_id)
        result = await executor.execute_dag(dag, initial_context)

        # Create WorkflowExecution record
        execution = WorkflowExecution(
            workflow_definition_id=definition_id,
            status=result["status"],
            state_payload={
                "node_outputs": result["node_outputs"],
                "final_context": result["final_context"]
            }
        )
        self.session.add(execution)
        await self.session.commit()
        await self.session.refresh(execution)
        return execution

    async def get_execution(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Fetch workflow execution by ID."""
        res = await self.session.execute(select(WorkflowExecution).where(WorkflowExecution.id == execution_id))
        return res.scalar_one_or_none()
