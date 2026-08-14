"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, analyticsApi, observabilityApi, Project, SprintAnalytics, ApiError } from "../../api";
import { TrendingUp, ShieldCheck, AlertTriangle } from "lucide-react";

type LoadState = "loading" | "empty" | "error" | "ready";

export default function AnalyticsPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established in frontend/app/page.tsx, agent-dashboard/page.tsx, projects/page.tsx).
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [sprintAnalytics, setSprintAnalytics] = useState<SprintAnalytics | null>(null);
  const [analyticsState, setAnalyticsState] = useState<LoadState>("loading");
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  // Observability metrics are organization-wide platform telemetry, not project-scoped --
  // loaded independently and allowed to fail without blocking the sprint analytics section.
  const [metrics, setMetrics] = useState<any>(null);

  const loadProjects = useCallback(async () => {
    if (!organizationId) return;
    setProjectsState("loading");
    setProjectsError(null);
    try {
      const wsRes = await projectApi.getWorkspaces(organizationId);
      if (!wsRes.workspaces || wsRes.workspaces.length === 0) {
        setProjects([]);
        setSelectedProjectId(null);
        setProjectsState("empty");
        return;
      }
      const projectLists = await Promise.all(wsRes.workspaces.map((ws) => projectApi.getProjects(ws.workspace_id)));
      const allProjects = projectLists.flatMap((p) => p.projects);
      setProjects(allProjects);
      if (allProjects.length === 0) {
        setSelectedProjectId(null);
        setProjectsState("empty");
      } else {
        setSelectedProjectId((prev) => (prev && allProjects.some((p) => p.project_id === prev) ? prev : allProjects[0].project_id));
        setProjectsState("ready");
      }
    } catch (err) {
      setProjectsError(err instanceof ApiError ? err.message : "Failed to load your projects.");
      setProjectsState("error");
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const loadAnalytics = useCallback(async () => {
    if (!selectedProjectId) return;
    setAnalyticsState("loading");
    setAnalyticsError(null);
    try {
      const aData = await analyticsApi.getSprintAnalytics(selectedProjectId);
      setSprintAnalytics(aData);
      setAnalyticsState("ready");
    } catch (err) {
      setSprintAnalytics(null);
      setAnalyticsError(err instanceof ApiError ? err.message : "Failed to load sprint analytics for this project.");
      setAnalyticsState("error");
    }

    try {
      const mData = await observabilityApi.getMetrics();
      setMetrics(mData);
    } catch (err) {
      setMetrics(null);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  const selectedProject = projects.find((p) => p.project_id === selectedProjectId) || null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="analytics" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <TrendingUp className="w-8 h-8 text-emerald-400" /> Team Analytics & Project Metrics
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                {selectedProject ? selectedProject.name : "Sprint velocity, completion rate, and delivery risk insights."}
              </p>
            </div>

            {projects.length > 1 && (
              <select
                value={selectedProjectId || ""}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="px-3 py-2 rounded-xl text-xs bg-white/5 border border-white/10 text-slate-200"
              >
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id} className="bg-slate-900">
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {projectsState === "loading" && (
            <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-3">
              <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              Loading your workspace...
            </div>
          )}

          {projectsState === "error" && (
            <div className="p-8 rounded-2xl bg-white/5 border border-white/10 text-center space-y-3">
              <p className="text-rose-400 font-semibold">Unable to load your workspace.</p>
              <p className="text-xs text-slate-400">{projectsError}</p>
              <button onClick={loadProjects} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-emerald-600/30 hover:bg-emerald-600/40">
                Retry
              </button>
            </div>
          )}

          {projectsState === "empty" && (
            <div className="p-10 rounded-2xl bg-white/5 border border-white/10 text-center space-y-4">
              <p className="text-slate-300 font-medium">
                No active projects in workspace. Connect your first integration to get started.
              </p>
              <Link
                href="/integrations"
                className="inline-flex px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-emerald-600/30 hover:bg-emerald-600/40"
              >
                Go to Integrations
              </Link>
            </div>
          )}

          {projectsState === "ready" && (
            <>
              {analyticsState === "loading" && (
                <div className="flex items-center justify-center py-16 text-slate-400 text-sm gap-3">
                  <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                  Loading sprint analytics...
                </div>
              )}

              {analyticsState === "error" && (
                <div className="p-6 rounded-2xl bg-white/5 border border-white/10 text-center text-sm text-rose-400">
                  {analyticsError}
                </div>
              )}

              {analyticsState === "ready" && sprintAnalytics && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                    <span className="text-xs text-slate-400">Delivery Risk Index</span>
                    <p className="text-3xl font-extrabold text-emerald-400">{sprintAnalytics.delivery_risk_index}</p>
                    {sprintAnalytics.risk_level === "low" ? (
                      <span className="text-xs text-emerald-400 flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" /> Low Risk Level</span>
                    ) : (
                      <span className="text-xs text-amber-300 flex items-center gap-1 capitalize"><AlertTriangle className="w-3.5 h-3.5" /> {sprintAnalytics.risk_level} Risk Level</span>
                    )}
                  </div>

                  <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                    <span className="text-xs text-slate-400">Completion Percentage</span>
                    <p className="text-3xl font-extrabold text-purple-400">{sprintAnalytics.completion_rate_percentage}%</p>
                    <span className="text-xs text-purple-300">{sprintAnalytics.completed_story_points} / {sprintAnalytics.total_story_points} Story Points Completed</span>
                  </div>

                  <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                    <span className="text-xs text-slate-400">Open Telemetry Spans</span>
                    <p className="text-3xl font-extrabold text-blue-400">{metrics?.total_spans_recorded ?? "—"}</p>
                    <span className="text-xs text-blue-300">Platform-wide observability telemetry</span>
                  </div>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
