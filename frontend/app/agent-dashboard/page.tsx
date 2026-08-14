"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import ProjectHealthOverview from "../../components/agent-dashboard/ProjectHealthOverview";
import DeveloperWorkloadPanel from "../../components/agent-dashboard/DeveloperWorkloadPanel";
import PullRequestIntelligence from "../../components/agent-dashboard/PullRequestIntelligence";
import AIRecommendationsPanel from "../../components/agent-dashboard/AIRecommendationsPanel";
import AgentActionsConsole from "../../components/agent-dashboard/AgentActionsConsole";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, analyticsApi, githubApi, jiraApi, Project, SprintAnalytics, ApiError } from "../../api";
import { Bot, RefreshCw } from "lucide-react";
import Link from "next/link";

// DeveloperWorkloadPanel and PullRequestIntelligence remain sourced from the
// GitHub/Jira mock GET endpoints (confirmed hardcoded server-side, ignoring
// organization_id entirely) -- explicitly out of scope to change here.
const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

type LoadState = "loading" | "empty" | "error" | "ready";

export default function AgentDashboardPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  // Real tenant/project context for ProjectHealthOverview, following the same pattern
  // already established in frontend/app/page.tsx (useAuth -> workspaces -> projects).
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [analytics, setAnalytics] = useState<SprintAnalytics | null>(null);
  const [analyticsState, setAnalyticsState] = useState<LoadState>("loading");

  const [pullRequests, setPullRequests] = useState<any[]>([]);
  const [workload, setWorkload] = useState<any[]>([]);
  const [mockLoading, setMockLoading] = useState(false);

  // 1. Discover the authenticated organization's real workspaces/projects.
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
      setProjectsError(err instanceof ApiError ? err.message : "Failed to load your workspaces and projects.");
      setProjectsState("error");
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // 2. Load real sprint analytics for the selected project (backend enforces tenant/project
  // ownership via _verify_project_ownership -- never trusted client-side).
  const loadAnalytics = useCallback(async () => {
    if (!selectedProjectId) return;
    setAnalyticsState("loading");
    try {
      const aData = await analyticsApi.getSprintAnalytics(selectedProjectId);
      setAnalytics(aData);
      setAnalyticsState("ready");
    } catch (err) {
      setAnalytics(null);
      setAnalyticsState("error");
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  // Unrelated, explicitly out-of-scope panels (hardcoded mock backend endpoints) -- left
  // functionally unchanged.
  const loadMockDashboardData = async () => {
    setMockLoading(true);
    try {
      const prData = await githubApi.getPullRequests(DUMMY_ORG_ID);
      if (prData && prData.pull_requests) setPullRequests(prData.pull_requests);
    } catch (e) {
      // Fallback active
    }

    try {
      const wData = await jiraApi.getWorkload(DUMMY_ORG_ID);
      if (wData && wData.team_workload) setWorkload(wData.team_workload);
    } catch (e) {
      // Fallback active
    }
    setMockLoading(false);
  };

  useEffect(() => {
    loadMockDashboardData();
  }, []);

  const handleRefresh = () => {
    loadProjects();
    loadMockDashboardData();
  };

  const selectedProject = projects.find((p) => p.project_id === selectedProjectId) || null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      {/* Background Neon Glow */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-purple-600/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -right-40 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl" />
      </div>

      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="agent_dashboard" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6 relative z-10">
          {/* Dashboard Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Bot className="w-8 h-8 text-purple-400" /> AI Technical PM Intelligence Dashboard
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                {selectedProject ? selectedProject.name : "Single pane of glass across GitHub, Jira, Slack, and Google Calendar."}
              </p>
            </div>

            <div className="flex items-center gap-3">
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
              <button
                onClick={handleRefresh}
                disabled={mockLoading}
                className="px-4 py-2.5 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 font-semibold text-sm border border-purple-500/30 transition-all flex items-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${mockLoading ? "animate-spin" : ""}`} /> Refresh PM Telemetry
              </button>
            </div>
          </div>

          {/* Section 1: Project Health Overview -- real tenant/project data only */}
          {projectsState === "loading" && (
            <div className="flex items-center justify-center py-16 text-slate-400 text-sm gap-3 rounded-2xl bg-white/5 border border-white/10">
              <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
              Loading your workspace...
            </div>
          )}

          {projectsState === "error" && (
            <div className="p-8 rounded-2xl bg-white/5 border border-white/10 text-center space-y-3">
              <p className="text-rose-400 font-semibold">Unable to load your workspace.</p>
              <p className="text-xs text-slate-400">{projectsError}</p>
              <button onClick={loadProjects} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-purple-600/30 hover:bg-purple-600/40">
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
                className="inline-flex px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-purple-600/30 hover:bg-purple-600/40"
              >
                Go to Integrations
              </Link>
            </div>
          )}

          {projectsState === "ready" && selectedProjectId && (
            <>
              {analyticsState === "loading" && (
                <div className="flex items-center justify-center py-16 text-slate-400 text-sm gap-3 rounded-2xl bg-white/5 border border-white/10">
                  <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                  Loading sprint analytics...
                </div>
              )}

              {analyticsState === "error" && (
                <div className="p-6 rounded-2xl bg-white/5 border border-white/10 text-center text-sm text-rose-400">
                  Sprint analytics are currently unavailable for this project.
                </div>
              )}

              {analyticsState === "ready" && analytics && <ProjectHealthOverview analytics={analytics} />}
            </>
          )}

          {/* Section 2 & Section 3: Developer Workload & Pull Request Intelligence Grid
              (unchanged -- hardcoded mock backend endpoints, out of scope) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <DeveloperWorkloadPanel workload={workload} />
            <PullRequestIntelligence pullRequests={pullRequests} />
          </div>

          {/* Section 4: AI Autonomous Recommendations */}
          <AIRecommendationsPanel />

          {/* Section 5: Agent Action Execution Console -- real org/project context already
              resolved above for ProjectHealthOverview, reused here rather than duplicating
              the workspace/project discovery. */}
          <AgentActionsConsole organizationId={organizationId || null} projectId={selectedProjectId} />
        </main>
      </div>
    </div>
  );
}
