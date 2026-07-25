// TypeScript Interfaces for AI-TPM API Request & Response Contracts

// Auth & User
export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string;
  organization_id?: string;
  role?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

export interface UserUpdateRequest {
  full_name?: string;
  avatar_url?: string;
}

// Workspaces & Projects
export interface Workspace {
  id: string;
  name: string;
  organization_id: string;
  description?: string;
  created_at?: string;
}

export interface WorkspacesResponse {
  workspaces_count: number;
  workspaces: Workspace[];
}

export interface Project {
  id: string;
  name: string;
  workspace_id: string;
  description?: string;
  created_at?: string;
}

export interface ProjectsResponse {
  projects_count: number;
  projects: Project[];
}

// Tasks & Sprint Backlog
export interface TaskItem {
  id?: string;
  task_id?: string;
  project_id: string;
  title: string;
  description?: string;
  status: "todo" | "in_progress" | "done" | string;
  priority: "low" | "medium" | "high" | "critical" | string;
  story_points: number;
  jira_issue_key?: string;
  created_at?: string;
}

export interface TasksResponse {
  tasks_count: number;
  tasks: TaskItem[];
}

export interface CreateTaskRequest {
  project_id: string;
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  story_points?: number;
}

export interface UpdateTaskRequest {
  title?: string;
  status?: string;
  priority?: string;
  story_points?: number;
}

// Analytics
export interface SprintAnalytics {
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
  risk_level: "low" | "medium" | "high" | "critical" | string;
}

export interface BurndownDataPoint {
  day: number;
  ideal_remaining: number;
  actual_remaining: number;
}

export interface BurndownResponse {
  project_id: string;
  trajectory: BurndownDataPoint[];
}

export interface PredictiveCompletionForecast {
  project_id: string;
  forecast_days: number;
  confidence_90_pct_days: number;
  risk_score: number;
}

// Agents & Workflows
export interface AgentExecutionRequest {
  agent_type: string;
  task: string;
  organization_id: string;
  project_id?: string;
}

export interface AgentExecutionResponse {
  execution_id: string;
  status: string;
  output: any;
}

export interface AgentPersona {
  type: string;
  role: string;
  description: string;
}

export interface WorkflowExecutionRequest {
  template: string;
  organization_id: string;
  project_id?: string;
}

export interface WorkflowExecutionResponse {
  execution_id: string;
  status: string;
  state: any;
}

// Context Engine & Memory
export interface ContextSearchRequest {
  organization_id: string;
  query?: string;
  query_text?: string;
  project_id?: string;
  top_k?: number;
}

export interface ContextSearchResult {
  chunk_id: string;
  score: number;
  content: string;
  source_type?: string;
}

export interface ContextSearchResponse {
  query: string;
  results_count: number;
  results: ContextSearchResult[];
}

export interface IndexDocumentRequest {
  organization_id: string;
  source_type: string;
  source_id: string;
  text: string;
  project_id?: string;
  metadata?: Record<string, any>;
}

export interface MemorySearchRequest {
  organization_id: string;
  query: string;
  limit?: number;
}

export interface MemorySearchResponse {
  query: string;
  results_count: number;
  results: any[];
}

// Observability
export interface TelemetrySpan {
  trace_id: string;
  span_id: string;
  name: string;
  traceparent: string;
  tracestate: string;
  duration_ms: number;
  status_code: string;
}

export interface TracesResponse {
  total_traces: number;
  spans: TelemetrySpan[];
}

export interface MetricsSummaryResponse {
  total_spans_recorded: number;
  telemetry_metrics: Record<string, any>;
}

// Security & Prompt Guard
export interface SecurityScanResponse {
  is_injection: boolean;
  risk_score: number;
  matched_patterns: string[];
  action: "ALLOW" | "BLOCK" | string;
}

export interface SecuritySanitizeResponse {
  status: "PASSED" | "BLOCKED" | string;
  reason?: string;
  risk_score: number;
  sanitized_text: string;
  pii_masked_counts: Record<string, number>;
}

// Rate Limiter
export interface RateLimitCheckResponse {
  allowed: boolean;
  remaining: number;
  limit: number;
  burst_limit?: number;
  retry_after_sec: number;
}

// Model Router
export interface ModelMatrixResponse {
  default_tier: string;
  total_categories: number;
  routing_matrix: Record<string, any>;
}

export interface ModelRouteResponse {
  task_category: string;
  budget_tier: string;
  selected_model: string;
  secondary_fallback_model: string;
  estimated_latency_ms: number;
}

// Cost Monitoring
export interface CostSummaryResponse {
  organization_id: string;
  total_cost_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cache_hits: number;
}

export interface CostAlertResponse {
  organization_id: string;
  alert_status: "NORMAL" | "WARNING_BUDGET_NEAR_LIMIT" | "CRITICAL_BUDGET_EXCEEDED" | string;
  utilization_percentage: number;
  current_spend_usd: number;
  budget_limit_usd: number;
}

// Knowledge Graph
export interface GraphTraverseResponse {
  start_node_id: string;
  active_outbound_edges: any[];
  total_active_edges: number;
}
