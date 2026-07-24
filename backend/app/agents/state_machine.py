from enum import Enum
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import AgentExecution
from app.events.redis_bus import get_event_bus

class AgentState(str, Enum):

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REFLECTION = "REFLECTION"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

# Valid state transition matrix according to Enterprise Architecture Spec
VALID_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.CREATED: {AgentState.QUEUED, AgentState.PLANNING, AgentState.EXECUTING, AgentState.CANCELLED, AgentState.FAILED},
    AgentState.QUEUED: {AgentState.PLANNING, AgentState.EXECUTING, AgentState.CANCELLED, AgentState.FAILED},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.CANCELLED, AgentState.FAILED},
    AgentState.EXECUTING: {
        AgentState.WAITING_TOOL,
        AgentState.WAITING_APPROVAL,
        AgentState.REFLECTION,
        AgentState.COMPLETED,
        AgentState.FAILED,
        AgentState.CANCELLED
    },
    AgentState.WAITING_TOOL: {AgentState.EXECUTING, AgentState.REFLECTION, AgentState.FAILED, AgentState.CANCELLED},
    AgentState.WAITING_APPROVAL: {AgentState.EXECUTING, AgentState.PLANNING, AgentState.CANCELLED, AgentState.FAILED},
    AgentState.REFLECTION: {AgentState.RETRYING, AgentState.COMPLETED, AgentState.PLANNING, AgentState.FAILED, AgentState.CANCELLED},
    AgentState.RETRYING: {AgentState.EXECUTING, AgentState.PLANNING, AgentState.FAILED, AgentState.CANCELLED},
    AgentState.COMPLETED: set(),
    AgentState.CANCELLED: set(),
    AgentState.FAILED: {AgentState.RETRYING, AgentState.PLANNING} # Allow recovery replanning
}

# Message broker event routing key mapping
STATE_EVENT_MAP: Dict[AgentState, str] = {
    AgentState.CREATED: "agent.run.created",
    AgentState.QUEUED: "agent.run.queued",
    AgentState.PLANNING: "agent.run.planning.started",
    AgentState.EXECUTING: "agent.run.executing",
    AgentState.WAITING_TOOL: "agent.run.tool.waiting",
    AgentState.WAITING_APPROVAL: "agent.run.approval.waiting",
    AgentState.REFLECTION: "agent.run.reflection",
    AgentState.RETRYING: "agent.run.retrying",
    AgentState.COMPLETED: "agent.run.completed",
    AgentState.CANCELLED: "agent.run.cancelled",
    AgentState.FAILED: "agent.run.failed",
}


class AgentStateMachine:
    """Persistent crash-safe Agent Lifecycle State Machine enforcing state transitions, retries, and event publishing."""

    def __init__(
        self,
        execution_id: uuid.UUID,
        agent_name: str,
        initial_status: AgentState = AgentState.CREATED,
        max_retries: int = 3,
        retry_count: int = 0,
        heartbeat_timeout_seconds: int = 30,
        organization_id: Optional[uuid.UUID] = None,
        db_session: Optional[AsyncSession] = None
    ):
        self.execution_id = execution_id
        self.agent_name = agent_name
        self.current_state = initial_status if isinstance(initial_status, AgentState) else AgentState(initial_status)
        self.max_retries = max_retries
        self.retry_count = retry_count
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.last_heartbeat = datetime.now(timezone.utc)
        self.organization_id = organization_id
        self.db_session = db_session
        self.state_history: List[Dict[str, Any]] = [{
            "state": self.current_state.value,
            "timestamp": self.last_heartbeat.isoformat(),
            "reason": "Initial state creation"
        }]

    def can_transition(self, target_state: AgentState) -> bool:
        """Check if target state is a valid transition from current state."""
        target = target_state if isinstance(target_state, AgentState) else AgentState(target_state)
        allowed = VALID_TRANSITIONS.get(self.current_state, set())
        return target in allowed

    async def transition_to(
        self,
        target_state: AgentState,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate, transition state, emit message bus event, and sync to database."""
        target = target_state if isinstance(target_state, AgentState) else AgentState(target_state)

        if not self.can_transition(target):
            raise ValueError(
                f"Invalid state transition for agent '{self.agent_name}' ({self.execution_id}): "
                f"Cannot move from '{self.current_state.value}' to '{target.value}'."
            )

        previous_state = self.current_state
        self.current_state = target
        self.last_heartbeat = datetime.now(timezone.utc)

        if target == AgentState.RETRYING:
            self.retry_count += 1
            if self.retry_count > self.max_retries:
                # Exceeded retries limit -> Transition to FAILED
                self.current_state = AgentState.FAILED
                reason = f"Exceeded maximum retries limit ({self.max_retries})."

        transition_record = {
            "execution_id": str(self.execution_id),
            "agent_name": self.agent_name,
            "from_state": previous_state.value,
            "to_state": self.current_state.value,
            "retry_count": self.retry_count,
            "timestamp": self.last_heartbeat.isoformat(),
            "reason": reason or f"Transition to {self.current_state.value}",
            "metadata": metadata or {}
        }

        self.state_history.append(transition_record)

        # 1. Emit Event Bus Event
        event_routing_key = STATE_EVENT_MAP.get(self.current_state, "agent.run.state_changed")
        try:
            event_bus = get_event_bus()
            if event_bus:
                await event_bus.publish(
                    stream_name="agent_events",
                    event_data={
                        "routing_key": event_routing_key,
                        "organization_id": str(self.organization_id) if self.organization_id else "00000000-0000-0000-0000-000000000001",
                        "payload": transition_record
                    }
                )
        except Exception:
            pass # Non-blocking event publication fallback

        # 2. Persist State Update to Database if Session Provided
        if self.db_session:
            res = await self.db_session.execute(
                select(AgentExecution).where(AgentExecution.id == self.execution_id)
            )
            db_exec = res.scalar_one_or_none()
            if db_exec:
                db_exec.status = self.current_state.value
                if metadata:
                    db_exec.output_payload = {**(db_exec.output_payload or {}), **metadata}
                await self.db_session.commit()

        return transition_record

    def record_heartbeat(self) -> datetime:
        """Update last heartbeat timestamp."""
        self.last_heartbeat = datetime.now(timezone.utc)
        return self.last_heartbeat

    def is_stale(self) -> bool:
        """Check if worker missed heartbeat timeout indicating worker crash."""
        if self.current_state in (AgentState.COMPLETED, AgentState.CANCELLED, AgentState.FAILED):
            return False
        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return elapsed > self.heartbeat_timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Export JSON Schema compliant state dictionary."""
        return {
            "execution_id": str(self.execution_id),
            "agent_name": self.agent_name,
            "status": self.current_state.value,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "heartbeat_timeout_seconds": self.heartbeat_timeout_seconds,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "state_history_count": len(self.state_history)
        }
