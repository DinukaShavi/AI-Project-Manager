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
      task: taskInput,           // backend schema field is 'task' not 'task_input'
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
      query: query,
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

// Observability & Tracing
export async function getObservabilityTraces() {
  return apiRequest<{ total_traces: number; spans: any[] }>("/observability/traces");
}

export async function getObservabilityMetrics() {
  return apiRequest<{ total_spans_recorded: number; telemetry_metrics: Record<string, any> }>("/observability/metrics");
}

// Security & Prompt Guard
export async function scanPromptInjection(text: string) {
  return apiRequest<{ is_injection: boolean; risk_score: number; matched_patterns: string[]; action: string }>("/security/scan-prompt", {
    method: "POST",
    body: JSON.stringify({ input_text: text }),
  });
}

export async function sanitizeSecurityInput(text: string) {
  return apiRequest<{ status: string; reason?: string; risk_score: number; sanitized_text: string; pii_masked_counts: Record<string, number> }>("/security/sanitize", {
    method: "POST",
    body: JSON.stringify({ input_text: text }),
  });
}

// Rate Limiter
export async function checkRateLimit(dimension: string, identifier: string, tokensNeeded: number = 1.0) {
  return apiRequest<{ allowed: boolean; remaining: number; limit: number; retry_after_sec: number }>("/rate-limit/check", {
    method: "POST",
    body: JSON.stringify({ dimension, identifier, tokens_needed: tokensNeeded }),
  });
}

// Model Router
export async function getModelMatrix() {
  return apiRequest<{ default_tier: string; total_categories: number; routing_matrix: Record<string, any> }>("/models/matrix");
}

export async function routeModelTask(taskCategory: string, budgetTier: string = "standard", payloadLength: number = 500) {
  return apiRequest<{ task_category: string; budget_tier: string; selected_model: string; secondary_fallback_model: string; estimated_latency_ms: number }>("/models/route", {
    method: "POST",
    body: JSON.stringify({ task_category: taskCategory, budget_tier: budgetTier, payload_token_length: payloadLength }),
  });
}

// AI Cost Monitoring
export async function getCostSummary(orgId: string) {
  return apiRequest<{ organization_id: string; total_cost_usd: number; total_prompt_tokens: number; total_completion_tokens: number; total_cache_hits: number }>(`/costs/summary/${orgId}`);
}

export async function getCostAlerts(orgId: string) {
  return apiRequest<{ organization_id: string; alert_status: string; utilization_percentage: number; current_spend_usd: number; budget_limit_usd: number }>(`/costs/alerts/${orgId}`);
}

// Graph Evolution
export async function traverseKnowledgeGraph(startNodeId: string, minWeight: number = 0.10) {
  return apiRequest<{ start_node_id: string; active_outbound_edges: any[]; total_active_edges: number }>(`/graph-evolution/traverse/${startNodeId}?min_weight=${minWeight}`);
}

