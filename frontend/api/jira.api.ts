import { httpClient } from "./client";
import {
  JiraProject,
  JiraIssue,
  JiraSprint,
  JiraTeamWorkload,
  JiraVelocityMetrics,
} from "../types/jira";

export const jiraApi = {
  getProjects: async (orgId: string): Promise<{ projects: JiraProject[] }> => {
    return httpClient<{ projects: JiraProject[] }>(`/integrations/jira/projects?organization_id=${orgId}`);
  },

  getIssues: async (orgId: string, projectKey: string = "TPM"): Promise<{ issues: JiraIssue[] }> => {
    return httpClient<{ issues: JiraIssue[] }>(`/integrations/jira/issues?organization_id=${orgId}&project_key=${projectKey}`);
  },

  getSprints: async (orgId: string, projectKey: string = "TPM"): Promise<{ sprints: JiraSprint[] }> => {
    return httpClient<{ sprints: JiraSprint[] }>(`/integrations/jira/sprints?organization_id=${orgId}&project_key=${projectKey}`);
  },

  getWorkload: async (orgId: string): Promise<{ team_workload: JiraTeamWorkload[] }> => {
    return httpClient<{ team_workload: JiraTeamWorkload[] }>(`/integrations/jira/workload?organization_id=${orgId}`);
  },

  getVelocity: async (orgId: string): Promise<JiraVelocityMetrics> => {
    return httpClient<JiraVelocityMetrics>(`/integrations/jira/velocity?organization_id=${orgId}`);
  },
};
