import { httpClient } from "./client";
import { WorkspacesResponse, ProjectsResponse, Project } from "./types";

export const projectApi = {
  getWorkspaces: async (orgId: string): Promise<WorkspacesResponse> => {
    return httpClient<WorkspacesResponse>(`/workspaces?organization_id=${orgId}`);
  },

  getProjects: async (workspaceId: string): Promise<ProjectsResponse> => {
    return httpClient<ProjectsResponse>(`/projects?workspace_id=${workspaceId}`);
  },

  createProject: async (payload: { name: string; workspace_id: string; description?: string }): Promise<Project> => {
    return httpClient<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
