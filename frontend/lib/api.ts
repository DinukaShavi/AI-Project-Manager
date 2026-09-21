// Backward-compatible façade delegating to the modular frontend/api service layer.
// Trimmed in Phase 67 to its only two real callers (AgentActionsConsole.tsx) -- everything
// else here was an unused re-export with zero call sites anywhere in the app.
import { taskApi, agentApi } from "../api";

export const createProjectTask = (taskData: any) => taskApi.createTask(taskData);

export const executeAgentPersona = (agentType: string, taskInput: string, orgId: string, projectId?: string) =>
  agentApi.executeAgentPersona({ agent_type: agentType, task: taskInput, organization_id: orgId, project_id: projectId });
