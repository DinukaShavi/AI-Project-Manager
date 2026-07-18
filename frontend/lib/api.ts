const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const defaultHeaders = {
    "Content-Type": "application/json",
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API Error (${response.status}): ${errorText}`);
    }

    return await response.json();
  } catch (error) {
    console.warn(`Request failed for ${endpoint}:`, error);
    throw error;
  }
}

// Workspaces & Projects
export async function getWorkspaces(orgId: string) {
  return apiRequest<{ workspaces_count: number; workspaces: any[] }>(`/workspaces?organization_id=${orgId}`);
}

export async function getProjects(workspaceId: string) {
  return apiRequest<{ projects_count: number; projects: any[] }>(`/projects?workspace_id=${workspaceId}`);
}

// Tasks & Kanban
export async function getProjectTasks(projectId: string) {
  return apiRequest<{ tasks_count: number; tasks: any[] }>(`/tasks?project_id=${projectId}`);
}

export async function createProjectTask(taskData: {
  project_id: string;
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  story_points?: number;
}) {
  return apiRequest<{ task_id: string; title: string; status: string }>("/tasks", {
    method: "POST",
    body: JSON.stringify(taskData),
  });
}

export async function updateTaskStatus(taskId: string, status: string) {
  return apiRequest<{ task_id: string; status: string }>(`/tasks/${taskId}`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

// Analytics
export async function getSprintAnalytics(projectId: string) {
  return apiRequest<{
    project_id: string;
    total_tasks: number;
    completed_tasks: number;
    in_progress_tasks: number;
    todo_tasks: number;
    high_risk_open_tasks: number;
    total_story_points: number;
    completed_story_points: number;
    completion_rate_percentage: number;
    delivery_risk_index: number;
    risk_level: string;
  }>(`/analytics/sprint?project_id=${projectId}`);
}

// AI Agents & Workflows
export async function executeAgentPersona(agentType: string, taskInput: string, orgId: string, projectId?: string) {
  return apiRequest<{ execution_id: string; status: string; output: any }>("/agents/execute", {
    method: "POST",
    body: JSON.stringify({
      agent_type: agentType,
      task_input: taskInput,
      organization_id: orgId,
      project_id: projectId,
    }),
  });
}

export async function executeWorkflowDAG(template: string, orgId: string, projectId?: string) {
  return apiRequest<{ execution_id: string; status: string; state: any }>("/workflows/execute", {
    method: "POST",
    body: JSON.stringify({
      template,
      organization_id: orgId,
      project_id: projectId,
    }),
  });
}

// Context Engine & Memory Search
export async function searchContextEngine(query: string, orgId: string) {
  return apiRequest<{ query: string; results_count: number; results: any[] }>("/context/search", {
    method: "POST",
    body: JSON.stringify({
      organization_id: orgId,
      query_text: query,
      top_k: 5,
    }),
  });
}

export async function searchLongTermMemory(query: string, orgId: string) {
  return apiRequest<{ query: string; results_count: number; results: any[] }>("/memory/search", {
    method: "POST",
    body: JSON.stringify({
      organization_id: orgId,
      query: query,
      limit: 5,
    }),
  });
}
