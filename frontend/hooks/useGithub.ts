"use client";

import { useState, useEffect, useCallback } from "react";
import { githubApi } from "../api/github.api";
import {
  GitHubPullRequest,
  GitHubCommit,
  GitHubIssue,
} from "../types/github";

/**
 * Custom Hook: Fetch & manage GitHub Pull Requests state, scoped to a project's linked
 * repositories. Skips fetching (and clears state) while no project is selected.
 */
export function useGithubPullRequests(projectId: string | null, repository?: string) {
  const [data, setData] = useState<GitHubPullRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPullRequests = useCallback(async () => {
    if (!projectId) {
      setData([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getPullRequests(projectId, repository);
      setData(res.pull_requests || []);
    } catch (err: any) {
      setError(err.message || "Failed to load pull requests");
    } finally {
      setLoading(false);
    }
  }, [projectId, repository]);

  useEffect(() => {
    fetchPullRequests();
  }, [fetchPullRequests]);

  return { pullRequests: data, loading, error, refresh: fetchPullRequests };
}

/**
 * Custom Hook: Fetch & manage GitHub Commit Activity state, scoped to a project's linked
 * repositories. Skips fetching (and clears state) while no project is selected.
 */
export function useGithubCommits(projectId: string | null, repository?: string) {
  const [data, setData] = useState<GitHubCommit[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCommits = useCallback(async () => {
    if (!projectId) {
      setData([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getCommits(projectId, repository);
      setData(res.commits || []);
    } catch (err: any) {
      setError(err.message || "Failed to load commit activity");
    } finally {
      setLoading(false);
    }
  }, [projectId, repository]);

  useEffect(() => {
    fetchCommits();
  }, [fetchCommits]);

  return { commits: data, loading, error, refresh: fetchCommits };
}

/**
 * Custom Hook: Fetch & manage GitHub Issue Tracking state, scoped to a project's linked
 * repositories. Skips fetching (and clears state) while no project is selected.
 */
export function useGithubIssues(projectId: string | null, repository?: string) {
  const [data, setData] = useState<GitHubIssue[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    if (!projectId) {
      setData([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getIssues(projectId, repository);
      setData(res.issues || []);
    } catch (err: any) {
      setError(err.message || "Failed to load GitHub issues");
    } finally {
      setLoading(false);
    }
  }, [projectId, repository]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  return { issues: data, loading, error, refresh: fetchIssues };
}
