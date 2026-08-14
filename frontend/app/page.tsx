"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import { useAuth } from "../hooks/use-auth";
import {
  projectApi,
  taskApi,
  analyticsApi,
  agentApi,
  workflowApi,
  contextApi,
  Project,
  TaskItem,
  SprintAnalytics,
  ContextSearchResult,
  ApiError,
} from "../api";

type LoadState = "loading" | "empty" | "error" | "ready";

export default function Dashboard() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<string>("overview");

  // Real tenant/project context -- the authenticated user's own organization/projects,
  // never a hardcoded id (ui_ux_design.md §2 "Main Dashboard").
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState<string | null>(null);

  // Dashboard data, sourced entirely from the selected real project.
  const [analytics, setAnalytics] = useState<SprintAnalytics | null>(null);
  const [analyticsState, setAnalyticsState] = useState<LoadState>("loading");
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [tasksState, setTasksState] = useState<LoadState>("loading");
  const [taskActionError, setTaskActionError] = useState<string | null>(null);

  // AI Agent Modal State
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState("TechnicalPMAgent");
  const [agentTaskInput, setAgentTaskInput] = useState("Analyze current sprint velocity, task bottlenecks, and assign story points.");
  const [agentExecutionResult, setAgentExecutionResult] = useState<any>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // New Task Modal State
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskPoints, setNewTaskPoints] = useState(3);
  const [newTaskPriority, setNewTaskPriority] = useState("medium");

  // Context Vector Search State
  const [searchQuery, setSearchQuery] = useState("vector database migration");
  const [searchResults, setSearchResults] = useState<ContextSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchAttempted, setSearchAttempted] = useState(false);

  const organizationId = user?.organization_id;

  // 1. Discover the authenticated organization's real workspaces and projects. An
  // organization with zero projects renders the documented empty state instead of any
  // fabricated data (ui_ux_design.md §2 Empty State).
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

  // 2. Load real sprint analytics and tasks for the selected project. Each section fails
  // independently -- an analytics outage never blocks the task board and vice versa, and
  // neither is ever replaced by fabricated data on failure.
  const loadProjectData = useCallback(async () => {
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

    setTasksState("loading");
    try {
      const tData = await taskApi.getProjectTasks(selectedProjectId);
      setTasks(tData.tasks || []);
      setTasksState(tData.tasks && tData.tasks.length > 0 ? "ready" : "empty");
    } catch (err) {
      setTasks([]);
      setTasksState("error");
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadProjectData();
  }, [loadProjectData]);

  // Handle AI Execution -- real backend result only. A failure is reported as an error,
  // never as a fabricated "successful" analysis.
  const handleRunAgent = async () => {
    if (!organizationId) return;
    setIsExecuting(true);
    setAgentExecutionResult(null);
    setAgentError(null);
    try {
      if (selectedAgent === "sprint_review" || selectedAgent === "architecture_audit") {
        const res = await workflowApi.executeWorkflow({
          template: selectedAgent,
          organization_id: organizationId,
          project_id: selectedProjectId || undefined,
        });
        setAgentExecutionResult(res);
      } else {
        const res = await agentApi.executeAgentPersona({
          agent_type: selectedAgent,
          task: agentTaskInput,
          organization_id: organizationId,
          project_id: selectedProjectId || undefined,
        });
        setAgentExecutionResult(res);
      }
    } catch (err) {
      setAgentError(err instanceof ApiError ? err.message : "Agent execution failed. The AI provider may be unavailable.");
    } finally {
      setIsExecuting(false);
    }
  };

  // Handle New Task Creation -- only reflects the task locally once the backend confirms
  // it was actually persisted.
  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim() || !selectedProjectId) return;
    setTaskActionError(null);
    try {
      const created = await taskApi.createTask({
        project_id: selectedProjectId,
        title: newTaskTitle,
        priority: newTaskPriority,
        story_points: Number(newTaskPoints),
      });
      setTasks((prev) => [created, ...prev]);
      setTasksState("ready");
      setNewTaskTitle("");
    } catch (err) {
      setTaskActionError(err instanceof ApiError ? err.message : "Failed to create the task.");
    }
  };

  // Handle Task Status Change -- reflects the real persisted status from the response.
  const handleUpdateStatus = async (taskId: string | undefined, newStatus: string) => {
    if (!taskId) return;
    setTaskActionError(null);
    try {
      const updated = await taskApi.updateTaskStatus(taskId, newStatus);
      setTasks((prev) => prev.map((t) => (t.task_id === taskId ? { ...t, status: updated.status } : t)));
    } catch (err) {
      setTaskActionError(err instanceof ApiError ? err.message : "Failed to update the task status.");
    }
  };

  // Handle Context Vector Search -- a failed search shows an error, never fabricated matches.
  const handleSearchContext = async () => {
    if (!searchQuery.trim() || !organizationId) return;
    setIsSearching(true);
    setSearchError(null);
    setSearchAttempted(true);
    try {
      const res = await contextApi.searchContext({ organization_id: organizationId, query: searchQuery, query_text: searchQuery });
      setSearchResults(res.results || []);
    } catch (err) {
      setSearchResults([]);
      setSearchError(err instanceof ApiError ? err.message : "Context search failed.");
    } finally {
      setIsSearching(false);
    }
  };

  const selectedProject = projects.find((p) => p.project_id === selectedProjectId) || null;

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col">
      {/* Top Navigation Bar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenAgentModal={() => setAgentModalOpen(true)}
      />

      <div className="flex flex-1">
        {/* Left Sidebar Navigation */}
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

        {/* Main Content View */}
        <main className="flex-1 p-6 lg:p-8 space-y-8 overflow-y-auto max-w-7xl mx-auto w-full">
          {/* Executive Overview Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
                {selectedProject ? selectedProject.name : "Executive Overview"}
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Real-time technical project management, automated delivery metrics, and AI multi-agent coordination.
              </p>
            </div>

            <div className="flex items-center gap-3">
              {projects.length > 1 && (
                <select
                  value={selectedProjectId || ""}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="glass-input px-3 py-2 rounded-xl text-xs"
                >
                  {projects.map((p) => (
                    <option key={p.project_id} value={p.project_id} className="bg-slate-900">
                      {p.name}
                    </option>
                  ))}
                </select>
              )}
              <button
                onClick={() => setAgentModalOpen(true)}
                disabled={!selectedProjectId}
                className="gradient-btn px-4 py-2 rounded-xl text-xs font-semibold text-white flex items-center space-x-2 shadow-lg disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Run Agent Audit</span>
              </button>
            </div>
          </div>

          {/* Loading state: initial workspace/project discovery in flight */}
          {projectsState === "loading" && (
            <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-3">
              <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              Loading your workspace...
            </div>
          )}

          {/* Error state: the backend call itself failed -- never silently replaced with fake data */}
          {projectsState === "error" && (
            <div className="glass-panel p-8 rounded-2xl text-center space-y-3">
              <p className="text-rose-400 font-semibold">Unable to load your workspace.</p>
              <p className="text-xs text-slate-400">{projectsError}</p>
              <button onClick={loadProjects} className="gradient-btn px-4 py-2 rounded-xl text-xs font-semibold text-white">
                Retry
              </button>
            </div>
          )}

          {/* Documented empty state (ui_ux_design.md §2): no active projects yet */}
          {projectsState === "empty" && (
            <div className="glass-panel p-10 rounded-2xl text-center space-y-4">
              <p className="text-slate-300 font-medium">
                No active projects in workspace. Connect your first integration to get started.
              </p>
              <Link
                href="/integrations"
                className="inline-flex gradient-btn px-5 py-2.5 rounded-xl text-xs font-semibold text-white"
              >
                Go to Integrations
              </Link>
            </div>
          )}

          {projectsState === "ready" && selectedProjectId && (
            <>
              {/* TAB 1: EXECUTIVE OVERVIEW */}
              {(activeTab === "overview" || activeTab === "workflows") && (
                <div className="space-y-8">
                  {/* Key Metric Cards */}
                  {analyticsState === "loading" && (
                    <div className="text-xs text-slate-400 flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /> Loading sprint analytics...
                    </div>
                  )}

                  {analyticsState === "error" && (
                    <div className="glass-card p-4 text-xs text-rose-400">
                      Sprint analytics are currently unavailable for this project.
                    </div>
                  )}

                  {analyticsState === "ready" && analytics && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                      {/* Velocity Card */}
                      <div className="glass-card p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-400">Sprint Velocity</span>
                          <span className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                          </span>
                        </div>
                        <div>
                          <div className="text-2xl font-extrabold text-white">
                            {analytics.completed_story_points} <span className="text-sm font-normal text-slate-400">/ {analytics.total_story_points} Points</span>
                          </div>
                          <div className="w-full bg-slate-800 h-2 rounded-full mt-3 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, analytics.completion_rate_percentage || 0)}%` }}
                            ></div>
                          </div>
                        </div>
                      </div>

                      {/* Completion Rate Card */}
                      <div className="glass-card p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-400">Completion Rate</span>
                          <span className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </span>
                        </div>
                        <div>
                          <div className="text-2xl font-extrabold text-emerald-400">
                            {analytics.completion_rate_percentage}%
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1">
                            {analytics.completed_tasks} of {analytics.total_tasks} tasks completed
                          </p>
                        </div>
                      </div>

                      {/* Delivery Risk Index */}
                      <div className="glass-card p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-400">Delivery Risk Index</span>
                          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            {analytics.risk_level}
                          </span>
                        </div>
                        <div>
                          <div className="text-2xl font-extrabold text-white">
                            {analytics.delivery_risk_index} <span className="text-xs font-normal text-slate-400">/ 1.0</span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1">
                            {analytics.high_risk_open_tasks || 0} open critical bottlenecks
                          </p>
                        </div>
                      </div>

                      {/* Active Agent Personas */}
                      <div className="glass-card p-5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-400">AI Agents Active</span>
                          <span className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L5.594 15.12a2 2 0 00-1.022.547l-1.096 1.096a1 1 0 001.414 1.414l.87-.87 2.387.477a8 8 0 005.146-.69l.318-.158a8 8 0 015.146-.69l2.387.477.87.87a1 1 0 001.414-1.414l-1.096-1.096z" />
                            </svg>
                          </span>
                        </div>
                        <div>
                          <div className="text-2xl font-extrabold text-purple-300">4 Personas</div>
                          <p className="text-[11px] text-slate-400 mt-1">6 Platform Tools Registered</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Specialized Personas Quick Action Grid */}
                  <div className="glass-panel p-6 rounded-2xl space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-bold text-white">AI Agent Personas & Multi-Agent Workflows</h3>
                        <p className="text-xs text-slate-400">Select a specialized agent persona or automated DAG workflow to execute analysis.</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                      {[
                        { id: "TechnicalPMAgent", name: "Technical PM Agent", desc: "Sprint velocity tracking & task assignments", color: "indigo" },
                        { id: "CodeAnalystAgent", name: "Code Analyst Agent", desc: "Pull request diff & code quality review", color: "purple" },
                        { id: "RiskManagerAgent", name: "Risk Manager Agent", desc: "Bottleneck & delivery delay detection", color: "pink" },
                        { id: "ArchitectureReviewerAgent", name: "Architecture Reviewer", desc: "System design & API contract audit", color: "cyan" },
                      ].map((p) => (
                        <button
                          key={p.id}
                          onClick={() => {
                            setSelectedAgent(p.id);
                            setAgentModalOpen(true);
                          }}
                          className="glass-card p-4 text-left space-y-2 hover:border-indigo-500/50 group transition-all"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold text-white group-hover:text-indigo-300 transition-colors">{p.name}</span>
                            <svg className="w-4 h-4 text-slate-500 group-hover:text-indigo-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </div>
                          <p className="text-xs text-slate-400">{p.desc}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: TASK KANBAN BOARD */}
              {(activeTab === "overview" || activeTab === "tasks") && (
                <div className="space-y-6 pt-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-bold text-white">Sprint Task Board</h3>
                      <p className="text-xs text-slate-400">Manage tasks, story points, and status transitions.</p>
                    </div>

                    {/* Add Task Form */}
                    <form onSubmit={handleCreateTask} className="flex items-center space-x-2">
                      <input
                        type="text"
                        placeholder="New task title..."
                        value={newTaskTitle}
                        onChange={(e) => setNewTaskTitle(e.target.value)}
                        className="glass-input px-3 py-1.5 rounded-lg text-xs w-60"
                      />
                      <select
                        value={newTaskPriority}
                        onChange={(e) => setNewTaskPriority(e.target.value)}
                        className="glass-input px-2 py-1.5 rounded-lg text-xs"
                      >
                        <option value="low" className="bg-slate-900">Low</option>
                        <option value="medium" className="bg-slate-900">Medium</option>
                        <option value="high" className="bg-slate-900">High</option>
                        <option value="critical" className="bg-slate-900">Critical</option>
                      </select>
                      <button type="submit" className="gradient-btn px-3 py-1.5 rounded-lg text-xs font-semibold text-white">
                        + Add Task
                      </button>
                    </form>
                  </div>

                  {taskActionError && (
                    <div className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                      {taskActionError}
                    </div>
                  )}

                  {tasksState === "loading" && (
                    <div className="text-xs text-slate-400 flex items-center gap-2 py-8 justify-center">
                      <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" /> Loading tasks...
                    </div>
                  )}

                  {tasksState === "error" && (
                    <div className="glass-card p-4 text-xs text-rose-400 text-center">
                      Tasks are currently unavailable for this project.
                    </div>
                  )}

                  {tasksState === "empty" && (
                    <div className="glass-card p-8 text-xs text-slate-400 text-center">
                      No tasks yet for this project. Add your first task above.
                    </div>
                  )}

                  {(tasksState === "ready" || tasksState === "empty") && (
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      {[
                        { id: "todo", title: "Todo", border: "border-slate-700" },
                        { id: "in_progress", title: "In Progress", border: "border-indigo-500/40" },
                        { id: "review", title: "In Review", border: "border-purple-500/40" },
                        { id: "done", title: "Done", border: "border-emerald-500/40" },
                      ].map((col) => {
                        const colTasks = tasks.filter((t) => t.status === col.id);
                        return (
                          <div key={col.id} className="glass-panel p-4 rounded-xl space-y-3 flex flex-col min-h-[300px]">
                            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                              <span className="text-xs font-bold text-slate-300">{col.title}</span>
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
                                {colTasks.length}
                              </span>
                            </div>

                            <div className="space-y-3 flex-1">
                              {colTasks.map((task) => (
                                <div key={task.task_id || task.id} className="glass-card p-3.5 space-y-2 text-xs">
                                  <div className="flex items-center justify-between">
                                    <span className="text-[10px] font-mono text-indigo-400">{task.jira_issue_key || "—"}</span>
                                    <span className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold ${
                                      task.priority === "critical" ? "bg-red-500/20 text-red-300" :
                                      task.priority === "high" ? "bg-amber-500/20 text-amber-300" : "bg-slate-800 text-slate-400"
                                    }`}>
                                      {task.priority}
                                    </span>
                                  </div>

                                  <p className="font-medium text-slate-200">{task.title}</p>

                                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
                                    <span className="text-[10px] text-slate-400">{task.story_points} pts</span>

                                    {/* Status Action Buttons */}
                                    <div className="flex items-center space-x-1">
                                      {col.id !== "todo" && (
                                        <button
                                          onClick={() => handleUpdateStatus(task.task_id, col.id === "done" ? "review" : col.id === "review" ? "in_progress" : "todo")}
                                          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400"
                                          title="Move Back"
                                        >
                                          ←
                                        </button>
                                      )}
                                      {col.id !== "done" && (
                                        <button
                                          onClick={() => handleUpdateStatus(task.task_id, col.id === "todo" ? "in_progress" : col.id === "in_progress" ? "review" : "done")}
                                          className="p-1 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300"
                                          title="Advance"
                                        >
                                          →
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: CONTEXT VECTOR SEARCH INSPECTOR */}
              {(activeTab === "overview" || activeTab === "context") && (
                <div className="glass-panel p-6 rounded-2xl space-y-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">Context Vector Engine & Memory Inspector</h3>
                    <p className="text-xs text-slate-400">Perform Cosine Similarity vector search over indexed documentation, PR diffs, and agent memories.</p>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="text"
                      placeholder="Enter semantic query e.g. 'Outbox pattern event bus fallback'..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="glass-input flex-1 px-4 py-2 rounded-xl text-xs"
                    />
                    <button
                      onClick={handleSearchContext}
                      disabled={isSearching}
                      className="gradient-btn px-5 py-2 rounded-xl text-xs font-semibold text-white"
                    >
                      {isSearching ? "Searching..." : "Search Vectors"}
                    </button>
                  </div>

                  {searchError && (
                    <div className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                      {searchError}
                    </div>
                  )}

                  {searchAttempted && !isSearching && !searchError && searchResults.length === 0 && (
                    <p className="text-xs text-slate-500">No matching context found for this query.</p>
                  )}

                  {searchResults.length > 0 && (
                    <div className="space-y-3 pt-2">
                      <p className="text-xs font-semibold text-slate-400">Top Semantic Similarity Matches:</p>
                      {searchResults.map((res, idx) => (
                        <div key={res.chunk_id || idx} className="glass-card p-4 space-y-1.5 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-indigo-400 text-[11px]">Match #{idx + 1}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-bold">
                              Cosine Score: {res.score != null ? res.score.toFixed(4) : "—"}
                            </span>
                          </div>
                          <p className="text-slate-300">{res.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* AI AGENT EXECUTION MODAL */}
      {agentModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="glass-panel w-full max-w-2xl rounded-2xl p-6 space-y-5 border border-indigo-500/30 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <span>AI Agent Persona Orchestrator</span>
              </h3>
              <button
                onClick={() => setAgentModalOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">Select Agent Persona or Multi-Agent Workflow DAG</label>
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="glass-input w-full px-3 py-2 rounded-xl text-xs"
                >
                  <option value="TechnicalPMAgent" className="bg-slate-900">TechnicalPMAgent (Sprint Tracking & Assignments)</option>
                  <option value="CodeAnalystAgent" className="bg-slate-900">CodeAnalystAgent (Pull Request & Diff Review)</option>
                  <option value="RiskManagerAgent" className="bg-slate-900">RiskManagerAgent (Bottlenecks & Schedule Risks)</option>
                  <option value="ArchitectureReviewerAgent" className="bg-slate-900">ArchitectureReviewerAgent (System Design Audit)</option>
                  <option value="sprint_review" className="bg-slate-900">[Workflow DAG] Sprint Review (3-Agent Sequence)</option>
                  <option value="architecture_audit" className="bg-slate-900">[Workflow DAG] Architecture Audit (2-Agent Sequence)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5">Task Instructions Prompt</label>
                <textarea
                  rows={3}
                  value={agentTaskInput}
                  onChange={(e) => setAgentTaskInput(e.target.value)}
                  className="glass-input w-full p-3 rounded-xl text-xs"
                ></textarea>
              </div>

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  onClick={() => setAgentModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-white bg-slate-900"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRunAgent}
                  disabled={isExecuting || !selectedProjectId}
                  className="gradient-btn px-5 py-2 rounded-xl text-xs font-semibold text-white disabled:opacity-50"
                >
                  {isExecuting ? "Executing Agent..." : "Execute Persona"}
                </button>
              </div>

              {agentError && (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                  {agentError}
                </div>
              )}

              {/* Execution Output Stream -- the real backend response only */}
              {agentExecutionResult && (
                <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/30 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-indigo-400 font-bold">
                    <span>Execution Result ({agentExecutionResult.status})</span>
                  </div>
                  <pre className="text-slate-300 font-mono text-[11px] overflow-x-auto p-2 bg-slate-900/60 rounded">
                    {JSON.stringify(agentExecutionResult.output ?? agentExecutionResult.state, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
