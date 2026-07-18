from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.workflow import WorkflowService
from app.workflows.dag import WorkflowDAG, WorkflowNode

router = APIRouter()

class NodeSchema(BaseModel):
    node_id: str
    name: str
    step_type: str
    target: str
    input_params: Optional[Dict[str, Any]] = None
    depends_on: Optional[List[str]] = None

class WorkflowDefinitionCreate(BaseModel):
    organization_id: UUID
    name: str
    description: str
    nodes: List[NodeSchema]

class WorkflowExecuteRequest(BaseModel):
    organization_id: UUID
    template: Optional[str] = Field(None, description="Pre-built template: 'sprint_review', 'architecture_audit'")
    definition_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    initial_context: Optional[Dict[str, Any]] = None
    nodes: Optional[List[NodeSchema]] = None

@router.post("/definitions", status_code=status.HTTP_201_CREATED)
async def create_definition(
    payload: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new Workflow DAG definition."""
    dag = WorkflowDAG()
    for n in payload.nodes:
        dag.add_node(WorkflowNode(
            node_id=n.node_id,
            name=n.name,
            step_type=n.step_type,
            target=n.target,
            input_params=n.input_params,
            depends_on=n.depends_on
        ))

    service = WorkflowService(db)
    try:
        wf_def = await service.create_definition(
            name=payload.name,
            description=payload.description,
            dag=dag,
            organization_id=payload.organization_id
        )
        return {
            "definition_id": str(wf_def.id),
            "name": wf_def.name,
            "description": wf_def.description,
            "nodes_count": len(payload.nodes)
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/definitions")
async def list_definitions(
    organization_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List all workflow definitions for an organization."""
    service = WorkflowService(db)
    defs = await service.list_definitions(organization_id)
    return {
        "definitions_count": len(defs),
        "definitions": [
            {
                "definition_id": str(d.id),
                "name": d.name,
                "description": d.description,
                "dag_structure": d.dag_structure
            }
            for d in defs
        ]
    }

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_workflow(
    payload: WorkflowExecuteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a multi-agent Workflow DAG by template, definition ID, or node list."""
    service = WorkflowService(db)
    dag = None

    if payload.template == "sprint_review":
        dag = service.get_sprint_review_template_dag()
    elif payload.template == "architecture_audit":
        dag = service.get_architecture_audit_template_dag()
    elif payload.nodes:
        dag = WorkflowDAG()
        for n in payload.nodes:
            dag.add_node(WorkflowNode(
                node_id=n.node_id,
                name=n.name,
                step_type=n.step_type,
                target=n.target,
                input_params=n.input_params,
                depends_on=n.depends_on
            ))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify a valid template ('sprint_review', 'architecture_audit') or provide 'nodes'."
        )

    try:
        execution = await service.execute_workflow(
            dag=dag,
            organization_id=payload.organization_id,
            project_id=payload.project_id,
            definition_id=payload.definition_id,
            initial_context=payload.initial_context
        )
        return {
            "execution_id": str(execution.id),
            "status": execution.status,
            "state": execution.state_payload
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve workflow execution state by ID."""
    service = WorkflowService(db)
    execution = await service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow execution not found")
    return {
        "execution_id": str(execution.id),
        "definition_id": str(execution.workflow_definition_id) if execution.workflow_definition_id else None,
        "status": execution.status,
        "state": execution.state_payload,
        "created_at": execution.created_at
    }
