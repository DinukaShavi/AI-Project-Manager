// TypeScript Interfaces for GitHub Integration Data Models

export interface GitHubRepository {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  description?: string;
  default_branch: string;
  open_issues_count: number;
  stargazers_count: number;
  updated_at: string;
}

export interface GitHubPullRequest {
  id: number;
  number: number;
  title: string;
  state: "open" | "closed" | "merged" | string;
  author: string;
  repository: string;
  html_url: string;
  created_at: string;
  draft: boolean;
  additions: number;
  deletions: number;
  labels: string[];
}

export interface GitHubCommit {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  author_email: string;
  repository: string;
  timestamp: string;
  html_url: string;
}

export interface GitHubIssue {
  id: number;
  number: number;
  title: string;
  state: "open" | "closed" | string;
  author: string;
  repository: string;
  html_url: string;
  created_at: string;
  comments_count: number;
  labels: string[];
}

export interface GitHubRepositoriesResponse {
  organization_id: string;
  total_repositories: number;
  repositories: GitHubRepository[];
}

export interface GitHubPullRequestsResponse {
  organization_id: string;
  total_pull_requests: number;
  pull_requests: GitHubPullRequest[];
}

export interface GitHubCommitsResponse {
  organization_id: string;
  total_commits: number;
  commits: GitHubCommit[];
}

export interface GitHubIssuesResponse {
  organization_id: string;
  total_issues: number;
  issues: GitHubIssue[];
}

export interface LinkGitHubRepositoryRequest {
  project_id: string;
  external_repo_id: string;
  name: string;
  clone_url: string;
}

export interface LinkGitHubRepositoryResponse {
  id: string;
  project_id: string;
  external_repo_id: string;
  name: string;
  clone_url: string;
  status: string;
}

// Real repository discovery/linking (distinct from the mock GitHubRepository shape above)
export interface DiscoveredGitHubRepo {
  external_repo_id: string;
  name: string;
  clone_url: string;
  private: boolean;
  default_branch: string | null;
  updated_at: string | null;
}

export interface DiscoverGitHubRepositoriesResponse {
  total_repositories: number;
  repositories: DiscoveredGitHubRepo[];
}

export interface LinkedGitHubRepo {
  id: string;
  external_repo_id: string;
  name: string;
  clone_url: string;
}

export interface LinkedGitHubRepositoriesResponse {
  project_id: string;
  total_repositories: number;
  repositories: LinkedGitHubRepo[];
}
