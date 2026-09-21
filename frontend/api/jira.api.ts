import { httpClient } from "./client";
import {
  JiraProject,
  JiraIssue,
  JiraSprint,
  JiraTeamWorkload,
  JiraVelocityMetrics,
} from "../types/jira";

export const jiraApi = {
  getProjects: async (): Promise<{ projects: JiraProject[] }> => {
    return httpClient<{ projects: JiraProject[] }>("/integrations/jira/projects");
  },

  // Real, project-scoped via the project's configured jira_project_key (Phase 62) --
  // organization is derived from the authenticated JWT server-side.
  getIssues: async (projectId: string): Promise<{ issues: JiraIssue[] }> => {
    return httpClient<{ issues: JiraIssue[] }>(`/integrations/jira/issues?project_id=${projectId}`);
  },

  getSprints: async (projectId: string): Promise<{ sprints: JiraSprint[] }> => {
    return httpClient<{ sprints: JiraSprint[] }>(`/integrations/jira/sprints?project_id=${projectId}`);
  },

  // Real, project-scoped (Phase 72) -- aggregated from the same real issues/sprints data
  // getIssues/getSprints already fetch.
  getWorkload: async (projectId: string): Promise<{ team_workload: JiraTeamWorkload[] }> => {
    return httpClient<{ team_workload: JiraTeamWorkload[] }>(`/integrations/jira/workload?project_id=${projectId}`);
  },

  getVelocity: async (projectId: string): Promise<JiraVelocityMetrics> => {
    return httpClient<JiraVelocityMetrics>(`/integrations/jira/velocity?project_id=${projectId}`);
  },
};
