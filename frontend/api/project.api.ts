import { httpClient } from "./client";
import { WorkspacesResponse, ProjectsResponse, Workspace, Project } from "./types";

export const projectApi = {
  getWorkspaces: async (orgId: string): Promise<WorkspacesResponse> => {
    return httpClient<WorkspacesResponse>(`/workspaces?organization_id=${orgId}`);
  },

  createWorkspace: async (payload: { name: string; organization_id: string; description?: string }): Promise<Workspace> => {
    return httpClient<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify(payload),
    });
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

  getProjectById: async (projectId: string): Promise<Project> => {
    return httpClient<Project>(`/projects/${projectId}`);
  },
};
