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

export function useJiraProjects() {
  const [projects, setProjects] = useState<JiraProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getProjects();
      setProjects(res.projects || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return { projects, loading, error, refresh: fetchProjects };
}

export function useJiraIssues(projectId: string | null) {
  const [issues, setIssues] = useState<JiraIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    if (!projectId) {
      setIssues([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getIssues(projectId);
      setIssues(res.issues || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira issues");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  return { issues, loading, error, refresh: fetchIssues };
}

export function useJiraSprints(projectId: string | null) {
  const [sprints, setSprints] = useState<JiraSprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSprints = useCallback(async () => {
    if (!projectId) {
      setSprints([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await jiraApi.getSprints(projectId);
      setSprints(res.sprints || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira sprints");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchSprints();
  }, [fetchSprints]);

  return { sprints, loading, error, refresh: fetchSprints };
}

export function useJiraMetrics(projectId: string | null) {
  const [workload, setWorkload] = useState<JiraTeamWorkload[]>([]);
  const [velocity, setVelocity] = useState<JiraVelocityMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (!projectId) {
      setWorkload([]);
      setVelocity(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [wRes, vRes] = await Promise.all([
        jiraApi.getWorkload(projectId),
        jiraApi.getVelocity(projectId),
      ]);
      setWorkload(wRes.team_workload || []);
      setVelocity(vRes);
    } catch (err: any) {
      setError(err.message || "Failed to load Jira velocity & workload metrics");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return { workload, velocity, loading, error, refresh: fetchMetrics };
}
