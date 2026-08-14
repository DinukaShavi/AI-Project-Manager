"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, analyticsApi, Project, SprintAnalytics, ApiError } from "../../api";
import { FolderKanban, Plus, ShieldCheck, AlertTriangle, ArrowRight } from "lucide-react";

type LoadState = "loading" | "empty" | "error" | "ready";

export default function ProjectsPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  // Real tenant/workspace/project context -- never a hardcoded id (matches the
  // established pattern from frontend/app/page.tsx and agent-dashboard/page.tsx).
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState<string | null>(null);

  // Each real project's own sprint analytics, never a single dummy project's data
  // reused across every card.
  const [analyticsByProject, setAnalyticsByProject] = useState<Record<string, SprintAnalytics>>({});

  const [newProjectName, setNewProjectName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    if (!organizationId) return;
    setProjectsState("loading");
    setProjectsError(null);
    try {
      const wsRes = await projectApi.getWorkspaces(organizationId);
      if (!wsRes.workspaces || wsRes.workspaces.length === 0) {
        setWorkspaceId(null);
        setProjects([]);
        setProjectsState("empty");
        return;
      }
      // New projects are attached to the organization's first workspace.
      setWorkspaceId(wsRes.workspaces[0].workspace_id);

      const projectLists = await Promise.all(wsRes.workspaces.map((ws) => projectApi.getProjects(ws.workspace_id)));
      const allProjects = projectLists.flatMap((p) => p.projects);
      setProjects(allProjects);
      setProjectsState(allProjects.length > 0 ? "ready" : "empty");
    } catch (err) {
      setProjectsError(err instanceof ApiError ? err.message : "Failed to load your projects.");
      setProjectsState("error");
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Fetch real sprint analytics per-project. A failure for one project never blocks
  // the others, and no fabricated fallback numbers are shown.
  useEffect(() => {
    if (projects.length === 0) return;
    let cancelled = false;
    (async () => {
      const entries = await Promise.all(
        projects.map(async (p) => {
          try {
            const a = await analyticsApi.getSprintAnalytics(p.project_id);
            return [p.project_id, a] as const;
          } catch {
            return null;
          }
        })
      );
      if (!cancelled) {
        const map: Record<string, SprintAnalytics> = {};
        for (const entry of entries) {
          if (entry) map[entry[0]] = entry[1];
        }
        setAnalyticsByProject(map);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projects]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || !workspaceId) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await projectApi.createProject({ name: newProjectName, workspace_id: workspaceId });
      setProjects((prev) => [created, ...prev]);
      setProjectsState("ready");
      setNewProjectName("");
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Failed to create the project.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="projects" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <FolderKanban className="w-8 h-8 text-indigo-400" /> Active Software Projects
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Workspace project management, sprint velocity tracking, and project intelligence.
              </p>
            </div>

            {workspaceId && (
              <form onSubmit={handleCreateProject} className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="New project name..."
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="px-3 py-2 rounded-xl text-xs bg-white/5 border border-white/10 text-slate-200 w-56"
                />
                <button
                  type="submit"
                  disabled={creating || !newProjectName.trim()}
                  className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2 disabled:opacity-50"
                >
                  <Plus className="w-4 h-4" /> New Project
                </button>
              </form>
            )}
          </div>

          {createError && (
            <div className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
              {createError}
            </div>
          )}

          {projectsState === "loading" && (
            <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-3">
              <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              Loading your projects...
            </div>
          )}

          {projectsState === "error" && (
            <div className="p-8 rounded-2xl bg-white/5 border border-white/10 text-center space-y-3">
              <p className="text-rose-400 font-semibold">Unable to load your projects.</p>
              <p className="text-xs text-slate-400">{projectsError}</p>
              <button onClick={loadProjects} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600/30 hover:bg-indigo-600/40">
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
                className="inline-flex px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-indigo-600/30 hover:bg-indigo-600/40"
              >
                Go to Integrations
              </Link>
            </div>
          )}

          {projectsState === "ready" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {projects.map((proj) => {
                const analytics = analyticsByProject[proj.project_id];
                return (
                  <div key={proj.project_id} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl hover:border-indigo-500/40 transition-all space-y-4 shadow-xl">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-xl font-bold text-white">{proj.name}</h3>
                        {proj.description && <p className="text-xs text-slate-400 mt-1">{proj.description}</p>}
                      </div>
                      {analytics && (
                        analytics.risk_level === "low" ? (
                          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                            <ShieldCheck className="w-3.5 h-3.5" /> Healthy
                          </span>
                        ) : (
                          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5" /> Attention
                          </span>
                        )
                      )}
                    </div>

                    {analytics && (
                      <div className="p-4 rounded-xl bg-white/5 space-y-2 border border-white/5">
                        <div className="flex justify-between text-xs text-slate-300">
                          <span>Sprint Story Points</span>
                          <span className="font-bold text-indigo-300">{analytics.completed_story_points} / {analytics.total_story_points} Completed</span>
                        </div>
                        <div className="w-full bg-slate-900 rounded-full h-2">
                          <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${Math.min(100, analytics.completion_rate_percentage)}%` }} />
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-white/5">
                      <span>{proj.created_at ? `Created: ${new Date(proj.created_at).toLocaleDateString()}` : ""}</span>
                      <Link href="/tasks" className="text-indigo-400 font-semibold flex items-center gap-1 hover:text-indigo-300">
                        Project Details <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
