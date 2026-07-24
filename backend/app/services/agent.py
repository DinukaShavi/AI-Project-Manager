import time
from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.base import BaseAgent
from app.agents.tpm import TechnicalPMAgent
from app.agents.code_analyst import CodeAnalystAgent
from app.agents.risk_manager import RiskManagerAgent
from app.agents.architect import ArchitectureReviewerAgent
from app.models.agent import AgentExecution
from app.models.tenant import Organization, Workspace
from app.models.project import Project

class AgentService:
    def __init__(self, session: AsyncSession):
        """Agent Service orchestrating specialized AI agent execution and database logging."""
        self.session = session

    def get_agent(self, agent_type: str) -> BaseAgent:
        """Agent factory instantiating requested specialized persona."""
        t = agent_type.lower().replace("-", "_").replace(" ", "_")
        if t in ["tpm", "technicalpmagent", "technical_pm", "technical_project_manager"]:
            return TechnicalPMAgent()
        elif t in ["code_analyst", "codeanalystagent", "code_reviewer", "reviewer"]:
            return CodeAnalystAgent()
        elif t in ["risk_manager", "riskmanageragent", "risk"]:
            return RiskManagerAgent()
        elif t in ["architect", "architecturerevieweragent", "architecture_reviewer", "system_architect"]:
            return ArchitectureReviewerAgent()
        else:
            raise ValueError(f"Unknown agent type: '{agent_type}'. Supported types: tpm, code_analyst, risk_manager, architect, TechnicalPMAgent, CodeAnalystAgent, RiskManagerAgent, ArchitectureReviewerAgent.")

    async def execute_agent(
        self,
        agent_type: str,
        task_input: str,
        organization_id: UUID,
        project_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentExecution:
        """Run agent persona task and persist execution metrics in database."""
        agent = self.get_agent(agent_type)
        
        # Ensure Organization and Project exist in DB to satisfy foreign key constraints
        org_res = await self.session.execute(select(Organization).where(Organization.id == organization_id))
        org = org_res.scalar_one_or_none()
        if not org:
            org = Organization(id=organization_id, name="Default Workspace Org", domain="default.org")
            self.session.add(org)
            await self.session.flush()

        if project_id:
            proj_res = await self.session.execute(select(Project).where(Project.id == project_id))
            proj = proj_res.scalar_one_or_none()
            if not proj:
                # Ensure a workspace exists for the project
                ws_res = await self.session.execute(select(Workspace).where(Workspace.organization_id == organization_id))
                ws = ws_res.scalars().first()
                if not ws:
                    ws = Workspace(organization_id=organization_id, name="Default Workspace")
                    self.session.add(ws)
                    await self.session.flush()
                proj = Project(id=project_id, workspace_id=ws.id, name="Default Demo Project")
                self.session.add(proj)
                await self.session.flush()

        # Create AgentExecution record with CREATED state
        execution = AgentExecution(
            organization_id=organization_id,
            project_id=project_id,
            agent_name=agent.agent_name,
            agent_role=agent.role,
            status="CREATED",
            input_payload={"task": task_input, "context": context or {}},
            output_payload={},
            execution_time_ms=0
        )
        self.session.add(execution)
        await self.session.commit()
        await self.session.refresh(execution)

        # Drive Execution Lifecycle through AgentStateMachine
        from app.agents.state_machine import AgentStateMachine, AgentState
        sm = AgentStateMachine(
            execution_id=execution.id,
            agent_name=agent.agent_name,
            initial_status=AgentState.CREATED,
            organization_id=organization_id,
            db_session=self.session
        )

        # Transition: CREATED -> EXECUTING -> REFLECTION -> COMPLETED
        await sm.transition_to(AgentState.EXECUTING, reason="Agent execution started")
        
        start_time = time.time()
        result_payload = await agent.execute(task_input, context)
        duration_ms = int((time.time() - start_time) * 1000)

        await sm.transition_to(AgentState.REFLECTION, reason="Evaluating persona execution results")
        await sm.transition_to(AgentState.COMPLETED, reason="Persona task completed successfully", metadata=result_payload)

        # Final database refresh
        res = await self.session.execute(select(AgentExecution).where(AgentExecution.id == execution.id))
        updated_exec = res.scalar_one()
        updated_exec.execution_time_ms = duration_ms
        updated_exec.output_payload = result_payload
        await self.session.commit()
        await self.session.refresh(updated_exec)

        return updated_exec

    async def get_execution(self, execution_id: UUID) -> Optional[AgentExecution]:
        """Fetch execution record by ID."""
        res = await self.session.execute(select(AgentExecution).where(AgentExecution.id == execution_id))
        return res.scalar_one_or_none()
