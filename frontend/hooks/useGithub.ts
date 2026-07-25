"use client";

import { useState, useEffect, useCallback } from "react";
import { githubApi } from "../api/github.api";
import {
  GitHubRepository,
  GitHubPullRequest,
  GitHubCommit,
  GitHubIssue,
} from "../types/github";

/**
 * Custom Hook: Fetch & manage GitHub Repositories state
 */
export function useGithubRepositories(orgId: string) {
  const [data, setData] = useState<GitHubRepository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRepositories = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getRepositories(orgId);
      setData(res.repositories || []);
    } catch (err: any) {
      setError(err.message || "Failed to load GitHub repositories");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);

  return { repositories: data, loading, error, refresh: fetchRepositories };
}

/**
 * Custom Hook: Fetch & manage GitHub Pull Requests state
 */
export function useGithubPullRequests(orgId: string, repository?: string) {
  const [data, setData] = useState<GitHubPullRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPullRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getPullRequests(orgId, repository);
      setData(res.pull_requests || []);
    } catch (err: any) {
      setError(err.message || "Failed to load pull requests");
    } finally {
      setLoading(false);
    }
  }, [orgId, repository]);

  useEffect(() => {
    fetchPullRequests();
  }, [fetchPullRequests]);

  return { pullRequests: data, loading, error, refresh: fetchPullRequests };
}

/**
 * Custom Hook: Fetch & manage GitHub Commit Activity state
 */
export function useGithubCommits(orgId: string, repository?: string) {
  const [data, setData] = useState<GitHubCommit[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCommits = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getCommits(orgId, repository);
      setData(res.commits || []);
    } catch (err: any) {
      setError(err.message || "Failed to load commit activity");
    } finally {
      setLoading(false);
    }
  }, [orgId, repository]);

  useEffect(() => {
    fetchCommits();
  }, [fetchCommits]);

  return { commits: data, loading, error, refresh: fetchCommits };
}

/**
 * Custom Hook: Fetch & manage GitHub Issue Tracking state
 */
export function useGithubIssues(orgId: string, repository?: string) {
  const [data, setData] = useState<GitHubIssue[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getIssues(orgId, repository);
      setData(res.issues || []);
    } catch (err: any) {
      setError(err.message || "Failed to load GitHub issues");
    } finally {
      setLoading(false);
    }
  }, [orgId, repository]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  return { issues: data, loading, error, refresh: fetchIssues };
}
