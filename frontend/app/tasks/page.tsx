"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, taskApi, Project, TaskItem, ApiError } from "../../api";
import { CheckSquare, Plus, RefreshCw } from "lucide-react";

type LoadState = "loading" | "empty" | "error" | "ready";

export default function TasksPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established in frontend/app/page.tsx, agent-dashboard/page.tsx, projects/page.tsx).
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [tasksState, setTasksState] = useState<LoadState>("loading");
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");

  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

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

  const loadTasks = useCallback(async () => {
    if (!selectedProjectId) return;
    setTasksState("loading");
    setTasksError(null);
    try {
      const res = await taskApi.getProjectTasks(selectedProjectId);
      setTasks(res.tasks || []);
      setTasksState(res.tasks && res.tasks.length > 0 ? "ready" : "empty");
    } catch (err) {
      setTasks([]);
      setTasksError(err instanceof ApiError ? err.message : "Failed to load tasks for this project.");
      setTasksState("error");
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim() || !selectedProjectId) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await taskApi.createTask({ project_id: selectedProjectId, title: newTaskTitle });
      setTasks((prev) => [created, ...prev]);
      setTasksState("ready");
      setNewTaskTitle("");
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Failed to create the task.");
    } finally {
      setCreating(false);
    }
  };

  const filteredTasks = filterStatus === "all" ? tasks : tasks.filter((t) => t.status === filterStatus);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="tasks" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <CheckSquare className="w-8 h-8 text-purple-400" /> Sprint Task Management
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Backlog task tickets, assignment tracking, and status transitions.
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
              <button onClick={loadTasks} className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10">
                <RefreshCw className={`w-4 h-4 ${tasksState === "loading" ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {projectsState === "loading" && (
            <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-3">
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
              {/* Create Task Form */}
              <form onSubmit={handleCreateTask} className="flex items-center gap-2 p-4 rounded-2xl bg-white/5 border border-white/10">
                <input
                  type="text"
                  placeholder="New task title..."
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg text-xs bg-white/5 border border-white/10 text-slate-200"
                />
                <button
                  type="submit"
                  disabled={creating || !newTaskTitle.trim()}
                  className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-sm shadow-lg shadow-purple-500/20 flex items-center gap-2 disabled:opacity-50"
                >
                  <Plus className="w-4 h-4" /> Create Task
                </button>
              </form>

              {createError && (
                <div className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                  {createError}
                </div>
              )}

              {/* Filter Bar */}
              <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl">
                {["all", "todo", "in_progress", "done"].map((st) => (
                  <button
                    key={st}
                    onClick={() => setFilterStatus(st)}
                    className={`px-4 py-2 rounded-xl text-xs font-semibold capitalize transition-all ${
                      filterStatus === st
                        ? "bg-purple-600 text-white shadow-md"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {st.replace("_", " ")}
                  </button>
                ))}
              </div>

              {tasksState === "loading" && (
                <div className="flex items-center justify-center py-16 text-slate-400 text-sm gap-3">
                  <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                  Loading tasks...
                </div>
              )}

              {tasksState === "error" && (
                <div className="p-6 rounded-2xl bg-white/5 border border-white/10 text-center text-sm text-rose-400">
                  {tasksError}
                </div>
              )}

              {tasksState === "empty" && (
                <div className="p-10 rounded-2xl bg-white/5 border border-white/10 text-center text-sm text-slate-400">
                  No tasks yet for this project. Add your first task above.
                </div>
              )}

              {tasksState === "ready" && (
                <div className="space-y-3">
                  {filteredTasks.map((t) => (
                    <div key={t.id || t.task_id} className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-purple-500/40 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all">
                      <div className="flex items-start gap-3">
                        <span className="px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-300 font-mono text-xs font-bold border border-purple-500/20">
                          {t.jira_issue_key || "TASK"}
                        </span>
                        <div>
                          <h4 className="text-base font-bold text-white">{t.title}</h4>
                          <p className="text-xs text-slate-400 mt-1">Priority: <span className="capitalize text-slate-200 font-medium">{t.priority}</span> • {t.story_points} Story Points</p>
                        </div>
                      </div>

                      <span className={`px-3 py-1 rounded-full text-xs font-bold capitalize self-end md:self-center ${
                        t.status === "done" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-300 border border-amber-500/20"
                      }`}>
                        {t.status.replace("_", " ")}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
