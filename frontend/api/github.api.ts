import { httpClient } from "./client";
import {
  GitHubPullRequestsResponse,
  GitHubCommitsResponse,
  GitHubIssuesResponse,
  LinkGitHubRepositoryRequest,
  LinkGitHubRepositoryResponse,
  DiscoverGitHubRepositoriesResponse,
  LinkedGitHubRepositoriesResponse,
} from "../types/github";

export const githubApi = {
  linkRepository: async (payload: LinkGitHubRepositoryRequest): Promise<LinkGitHubRepositoryResponse> => {
    return httpClient<LinkGitHubRepositoryResponse>("/integrations/github/repositories", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  discoverRepositories: async (): Promise<DiscoverGitHubRepositoriesResponse> => {
    return httpClient<DiscoverGitHubRepositoriesResponse>("/integrations/github/discover-repositories");
  },

  getLinkedRepositories: async (projectId: string): Promise<LinkedGitHubRepositoriesResponse> => {
    return httpClient<LinkedGitHubRepositoriesResponse>(`/integrations/github/linked-repositories?project_id=${projectId}`);
  },

  // Real, project-scoped (via the project's linked repositories) -- organization is derived
  // from the authenticated JWT server-side, never a client-supplied id.
  getPullRequests: async (projectId: string, repository?: string): Promise<GitHubPullRequestsResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubPullRequestsResponse>(`/integrations/github/pull-requests?project_id=${projectId}${query}`);
  },

  getCommits: async (projectId: string, repository?: string): Promise<GitHubCommitsResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubCommitsResponse>(`/integrations/github/commits?project_id=${projectId}${query}`);
  },

  getIssues: async (projectId: string, repository?: string): Promise<GitHubIssuesResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubIssuesResponse>(`/integrations/github/issues?project_id=${projectId}${query}`);
  },

  getAuthorizeUrl: async (orgId: string): Promise<{ authorization_url: string }> => {
    return httpClient<{ authorization_url: string }>(`/integrations/oauth/github/authorize?organization_id=${orgId}`);
  },

  revokeConnection: async (orgId: string): Promise<{ status: string }> => {
    return httpClient<{ status: string }>(`/integrations/oauth/github?organization_id=${orgId}`, {
      method: "DELETE",
    });
  },
};
