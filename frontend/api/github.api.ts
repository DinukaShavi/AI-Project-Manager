import { httpClient } from "./client";
import {
  GitHubRepositoriesResponse,
  GitHubPullRequestsResponse,
  GitHubCommitsResponse,
  GitHubIssuesResponse,
} from "../types/github";

export const githubApi = {
  getRepositories: async (orgId: string): Promise<GitHubRepositoriesResponse> => {
    return httpClient<GitHubRepositoriesResponse>(`/integrations/github/repositories?organization_id=${orgId}`);
  },

  getPullRequests: async (orgId: string, repository?: string): Promise<GitHubPullRequestsResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubPullRequestsResponse>(`/integrations/github/pull-requests?organization_id=${orgId}${query}`);
  },

  getCommits: async (orgId: string, repository?: string): Promise<GitHubCommitsResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubCommitsResponse>(`/integrations/github/commits?organization_id=${orgId}${query}`);
  },

  getIssues: async (orgId: string, repository?: string): Promise<GitHubIssuesResponse> => {
    const query = repository ? `&repository=${encodeURIComponent(repository)}` : "";
    return httpClient<GitHubIssuesResponse>(`/integrations/github/issues?organization_id=${orgId}${query}`);
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
