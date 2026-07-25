"use client";

import { useState, useEffect, useCallback } from "react";
import { jiraApi } from "../api/jira.api";
import {
  JiraProject,
  JiraIssue,
  JiraSprint,
  JiraTeamWorkload,
  JiraVelocityMetrics,
} from "../types/jira";

export function useJiraProjects(orgId: string) {
  const [projects, setProjects] = useState<JiraProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getProjects(orgId);
      setProjects(res.projects || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira projects");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return { projects, loading, error, refresh: fetchProjects };
}

export function useJiraIssues(orgId: string, projectKey: string = "TPM") {
  const [issues, setIssues] = useState<JiraIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getIssues(orgId, projectKey);
      setIssues(res.issues || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira issues");
    } finally {
      setLoading(false);
    }
  }, [orgId, projectKey]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  return { issues, loading, error, refresh: fetchIssues };
}

export function useJiraSprints(orgId: string, projectKey: string = "TPM") {
  const [sprints, setSprints] = useState<JiraSprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSprints = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getSprints(orgId, projectKey);
      setSprints(res.sprints || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira sprints");
    } finally {
      setLoading(false);
    }
  }, [orgId, projectKey]);

  useEffect(() => {
    fetchSprints();
  }, [fetchSprints]);

  return { sprints, loading, error, refresh: fetchSprints };
}

export function useJiraMetrics(orgId: string) {
  const [workload, setWorkload] = useState<JiraTeamWorkload[]>([]);
  const [velocity, setVelocity] = useState<JiraVelocityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [wRes, vRes] = await Promise.all([
        jiraApi.getWorkload(orgId),
        jiraApi.getVelocity(orgId),
      ]);
      setWorkload(wRes.team_workload || []);
      setVelocity(vRes);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira velocity & workload metrics");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return { workload, velocity, loading, error, refresh: fetchMetrics };
}
