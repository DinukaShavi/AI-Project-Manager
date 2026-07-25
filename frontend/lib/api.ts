// Backward-compatible façade delegating to the modular frontend/api service layer
import {
  projectApi,
  taskApi,
  analyticsApi,
  agentApi,
  workflowApi,
  contextApi,
  observabilityApi,
  securityApi,
  rateLimiterApi,
  modelRouterApi,
  costsApi,
  graphApi,
  githubApi,
  jiraApi,
  slackApi,
  calendarApi,
  httpClient,
} from "../api";

export { githubApi, jiraApi, slackApi, calendarApi };

export const apiRequest = httpClient;

// Workspaces & Projects
export const getWorkspaces = (orgId: string) => projectApi.getWorkspaces(orgId);
export const getProjects = (workspaceId: string) => projectApi.getProjects(workspaceId);

// Tasks & Kanban
export const getProjectTasks = (projectId: string) => taskApi.getProjectTasks(projectId);
export const createProjectTask = (taskData: any) => taskApi.createTask(taskData);
export const updateTaskStatus = (taskId: string, status: string) => taskApi.updateTaskStatus(taskId, status);

// Analytics
export const getSprintAnalytics = (projectId: string) => analyticsApi.getSprintAnalytics(projectId);

// AI Agents & Workflows
export const executeAgentPersona = (agentType: string, taskInput: string, orgId: string, projectId?: string) =>
  agentApi.executeAgentPersona({ agent_type: agentType, task: taskInput, organization_id: orgId, project_id: projectId });

export const executeWorkflowDAG = (template: string, orgId: string, projectId?: string) =>
  workflowApi.executeWorkflow({ template, organization_id: orgId, project_id: projectId });

// Context Engine & Memory Search
export const searchContextEngine = (query: string, orgId: string) =>
  contextApi.searchContext({ organization_id: orgId, query, query_text: query });

export const searchLongTermMemory = (query: string, orgId: string) =>
  contextApi.searchMemory({ organization_id: orgId, query });

// Observability & Tracing
export const getObservabilityTraces = () => observabilityApi.getTraces();
export const getObservabilityMetrics = () => observabilityApi.getMetrics();

// Security & Prompt Guard
export const scanPromptInjection = (text: string) => securityApi.scanPrompt(text);
export const sanitizeSecurityInput = (text: string) => securityApi.sanitizeInput(text);

// Rate Limiter
export const checkRateLimit = (dimension: string, identifier: string, tokensNeeded: number = 1.0) =>
  rateLimiterApi.checkRateLimit(dimension, identifier, tokensNeeded);

// Model Router
export const getModelMatrix = () => modelRouterApi.getModelMatrix();
export const routeModelTask = (taskCategory: string, budgetTier: string = "standard", payloadLength: number = 500) =>
  modelRouterApi.routeTask(taskCategory, budgetTier, payloadLength);

// AI Cost Monitoring
export const getCostSummary = (orgId: string) => costsApi.getCostSummary(orgId);
export const getCostAlerts = (orgId: string) => costsApi.getCostAlerts(orgId);

// Graph Evolution
export const traverseKnowledgeGraph = (startNodeId: string, minWeight: number = 0.10) =>
  graphApi.traverseGraph(startNodeId, minWeight);
