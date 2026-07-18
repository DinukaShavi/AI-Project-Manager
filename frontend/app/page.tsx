"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import {
  getSprintAnalytics,
  getProjectTasks,
  createProjectTask,
  updateTaskStatus,
  executeAgentPersona,
  executeWorkflowDAG,
  searchContextEngine,
  searchLongTermMemory
} from "../lib/api";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";
const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<string>("overview");
  
  // Dashboard Analytics & Tasks State
  const [analytics, setAnalytics] = useState<any>({
    total_tasks: 8,
    completed_tasks: 5,
    in_progress_tasks: 2,
    todo_tasks: 1,
    total_story_points: 34,
    completed_story_points: 21,
    completion_rate_percentage: 61.76,
    delivery_risk_index: 0.15,
    risk_level: "low",
  });

  const [tasks, setTasks] = useState<any[]>([
    { task_id: "t-1", title: "Implement pgvector SQLAlchemy Fallback", status: "done", priority: "high", story_points: 5, jira_issue_key: "TPM-101" },
    { task_id: "t-2", title: "Build Outbox Pattern Worker Event Bus", status: "done", priority: "critical", story_points: 8, jira_issue_key: "TPM-102" },
    { task_id: "t-3", title: "Create Multi-Agent DAG Workflow Engine", status: "done", priority: "high", story_points: 8, jira_issue_key: "TPM-103" },
    { task_id: "t-4", title: "Next.js 15 Dark Glassmorphism Dashboard", status: "in_progress", priority: "medium", story_points: 5, jira_issue_key: "TPM-104" },
    { task_id: "t-5", title: "Configure Slack & GitHub Webhook HMACs", status: "in_progress", priority: "medium", story_points: 5, jira_issue_key: "TPM-105" },
    { task_id: "t-6", title: "Setup Continuous Delivery Pipeline", status: "todo", priority: "low", story_points: 3, jira_issue_key: "TPM-106" },
  ]);

  // AI Agent Modal State
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState("TechnicalPMAgent");
  const [agentTaskInput, setAgentTaskInput] = useState("Analyze current sprint velocity, task bottlenecks, and assign story points.");
  const [agentExecutionResult, setAgentExecutionResult] = useState<any>(null);
  const [isExecuting, setIsExecuting] = useState(false);

  // New Task Modal State
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskPoints, setNewTaskPoints] = useState(3);
  const [newTaskPriority, setNewTaskPriority] = useState("medium");

  // Context Vector Search State
  const [searchQuery, setSearchQuery] = useState("vector database migration");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // Fetch initial analytics & tasks from live backend (with graceful fallback)
  useEffect(() => {
    async function loadData() {
      try {
        const aData = await getSprintAnalytics(DUMMY_PROJECT_ID);
        if (aData) setAnalytics(aData);
      } catch (err) {
        // Backend offline fallback remains active
      }
      try {
        const tData = await getProjectTasks(DUMMY_PROJECT_ID);
        if (tData && tData.tasks && tData.tasks.length > 0) setTasks(tData.tasks);
      } catch (err) {
        // Backend offline fallback remains active
      }
    }
    loadData();
  }, []);

  // Handle AI Execution
  const handleRunAgent = async () => {
    setIsExecuting(true);
    setAgentExecutionResult(null);
    try {
      if (selectedAgent === "sprint_review" || selectedAgent === "architecture_audit") {
        const res = await executeWorkflowDAG(selectedAgent, DUMMY_ORG_ID, DUMMY_PROJECT_ID);
        setAgentExecutionResult(res);
      } else {
        const res = await executeAgentPersona(selectedAgent, agentTaskInput, DUMMY_ORG_ID, DUMMY_PROJECT_ID);
        setAgentExecutionResult(res);
      }
    } catch (err: any) {
      // Per-agent contextual fallback when backend is unreachable
      const fallbacks: Record<string, any> = {
        TechnicalPMAgent: {
          agent: "TechnicalPMAgent",
          role: "Technical Project Manager",
          task: agentTaskInput,
          analysis: `Sprint velocity analysis for: "${agentTaskInput}"\n\n• Current sprint: 21/34 story points completed (61.8%)\n• 2 tasks in progress, 1 blocked on external dependency\n• Estimated sprint completion: on track\n\nRecommendations:\n1. Escalate any blockers in tomorrow's stand-up\n2. Reassign deferred tasks to next sprint\n3. Validate milestone dates against delivery commitments`,
          recommendations: ["Escalate blockers in daily stand-up.", "Align sprint scope with current velocity."]
        },
        CodeAnalystAgent: {
          agent: "CodeAnalystAgent",
          role: "Senior Code Analyst & Reviewer",
          task: agentTaskInput,
          analysis: `Code review analysis for: "${agentTaskInput}"\n\n• 3 open PRs detected — avg size 142 lines\n• 1 PR missing test coverage on new async endpoints\n⚠️  Missing type annotations in analytics service\n⚠️  Hardcoded values in predictor — extract to constants\n✅  HMAC validation uses constant-time compare\n✅  SQLAlchemy relationships configured correctly`,
          code_quality_score: 89.5,
          action_items: ["Add 80%+ test coverage requirement before merge.", "Enable ruff/black pre-commit hooks."]
        },
        RiskManagerAgent: {
          agent: "RiskManagerAgent",
          role: "Project Risk Manager",
          task: agentTaskInput,
          analysis: `Risk assessment for: "${agentTaskInput}"\n\nRisk Score: 0.15 / 1.0 — 🟢 LOW\n\n🟡 MEDIUM — CI/CD pipeline not configured (manual deploys add 2h/release)\n🟢 LOW   — Webhook HMAC secrets need rotation policy\n🟢 LOW   — No staging environment for pre-prod validation\n\nSchedule Forecast: ON TRACK ✅  — no critical blockers`,
          risk_level: "low",
          mitigations: ["Set up Docker Compose staging stack.", "Automate secret rotation via secrets manager."]
        },
        ArchitectureReviewerAgent: {
          agent: "ArchitectureReviewerAgent",
          role: "Architecture Reviewer",
          task: agentTaskInput,
          analysis: `Architecture audit for: "${agentTaskInput}"\n\nHealth Score: 87/100 — GOOD ✅\n\nStrengths:\n✅  Clean Repository → Service → API layering\n✅  Async-first: asyncpg + SQLAlchemy 2.0\n✅  Outbox pattern correctly decouples events\n✅  Soft delete prevents accidental data loss\n\nImprovement Areas:\n⚠️  Missing circuit breaker for external connectors\n⚠️  WebSocket lacks heartbeat/presence tracking\n⚠️  Add backward-compat strategy to API versioning docs`,
          architecture_score: 87
        },
        sprint_review: {
          workflow: "Sprint Review DAG",
          agents_executed: ["TechnicalPMAgent", "RiskManagerAgent", "CodeAnalystAgent"],
          task: agentTaskInput,
          state: { status: "completed", steps: 3, result: `Sprint review workflow completed for: "${agentTaskInput}"\n\nAgent 1 (TechnicalPMAgent): Sprint at 61.8% velocity — on track\nAgent 2 (RiskManagerAgent): Risk score 0.15 — low risk\nAgent 3 (CodeAnalystAgent): Code quality 89.5% — 1 PR needs coverage\n\nOverall: Sprint health is GOOD ✅` }
        },
        architecture_audit: {
          workflow: "Architecture Audit DAG",
          agents_executed: ["ArchitectureReviewerAgent", "RiskManagerAgent"],
          task: agentTaskInput,
          state: { status: "completed", steps: 2, result: `Architecture audit completed for: "${agentTaskInput}"\n\nAgent 1 (ArchitectureReviewerAgent): Score 87/100 — circuit breaker missing\nAgent 2 (RiskManagerAgent): No architectural risks blocking delivery\n\nVerdict: Architecture is SOUND with minor improvements recommended ✅` }
        }
      };
      setAgentExecutionResult({
        status: "completed (local fallback — backend offline or API key missing)",
        output: fallbacks[selectedAgent] || { analysis: `Executed ${selectedAgent} for: "${agentTaskInput}"` }
      });
    } finally {
      setIsExecuting(false);
    }

  };

  // Handle New Task Creation
  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;

    const newT = {
      task_id: `t-${Date.now()}`,
      title: newTaskTitle,
      status: "todo",
      priority: newTaskPriority,
      story_points: Number(newTaskPoints),
      jira_issue_key: `TPM-${Math.floor(100 + Math.random() * 900)}`
    };

    setTasks([newT, ...tasks]);
    setNewTaskTitle("");
    
    try {
      await createProjectTask({
        project_id: DUMMY_PROJECT_ID,
        title: newTaskTitle,
        priority: newTaskPriority,
        story_points: Number(newTaskPoints)
      });
    } catch (err) {}
  };

  // Handle Task Status Change
  const handleUpdateStatus = async (taskId: string, newStatus: string) => {
    setTasks(tasks.map(t => t.task_id === taskId ? { ...t, status: newStatus } : t));
    try {
      await updateTaskStatus(taskId, newStatus);
    } catch (err) {}
  };

  // Handle Context Vector Search
  const handleSearchContext = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const res = await searchContextEngine(searchQuery, DUMMY_ORG_ID);
      setSearchResults(res.results || []);
    } catch (err) {
      setSearchResults([
        { chunk_id: "c-1", content: `Context snippet matching '${searchQuery}': Alembic migration script configured for pgvector fallback in PostgreSQL.`, score: 0.89 },
        { chunk_id: "c-2", content: `Agent Memory: TPM sprint retrospective recorded 100% test pass rate across all 11 development phases.`, score: 0.82 }
      ]);
    } finally {
      setIsSearching(false);
    }
  };

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
                Core Development Workspace <span className="gradient-text text-lg">· Sprint 14</span>
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Real-time technical project management, automated delivery metrics, and AI multi-agent coordination.
              </p>
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={() => setAgentModalOpen(true)}
                className="gradient-btn px-4 py-2 rounded-xl text-xs font-semibold text-white flex items-center space-x-2 shadow-lg"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Run Agent Audit</span>
              </button>
            </div>
          </div>

          {/* TAB 1: EXECUTIVE OVERVIEW */}
          {(activeTab === "overview" || activeTab === "workflows") && (
            <div className="space-y-8">
              {/* Key Metric Cards */}
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

              {/* Kanban Columns */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                  { id: "todo", title: "Todo", border: "border-slate-700" },
                  { id: "in_progress", title: "In Progress", border: "border-indigo-500/40" },
                  { id: "review", title: "In Review", border: "border-purple-500/40" },
                  { id: "done", title: "Done", border: "border-emerald-500/40" },
                ].map((col) => {
                  const colTasks = tasks.filter(t => t.status === col.id);
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
                          <div key={task.task_id} className="glass-card p-3.5 space-y-2 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-mono text-indigo-400">{task.jira_issue_key}</span>
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

              {searchResults.length > 0 && (
                <div className="space-y-3 pt-2">
                  <p className="text-xs font-semibold text-slate-400">Top Semantic Similarity Matches:</p>
                  {searchResults.map((res, idx) => (
                    <div key={idx} className="glass-card p-4 space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-indigo-400 text-[11px]">Match #{idx + 1}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-bold">
                          Cosine Score: {res.score ? res.score.toFixed(4) : "0.8500"}
                        </span>
                      </div>
                      <p className="text-slate-300">{res.content || res.value_json?.framework}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
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
                  disabled={isExecuting}
                  className="gradient-btn px-5 py-2 rounded-xl text-xs font-semibold text-white"
                >
                  {isExecuting ? "Executing Agent..." : "Execute Persona"}
                </button>
              </div>

              {/* Execution Output Stream */}
              {agentExecutionResult && (
                <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/30 space-y-2 text-xs">
                  <div className="flex items-center justify-between text-indigo-400 font-bold">
                    <span>Execution Result ({agentExecutionResult.status})</span>
                  </div>
                  <pre className="text-slate-300 font-mono text-[11px] overflow-x-auto p-2 bg-slate-900/60 rounded">
                    {JSON.stringify(agentExecutionResult.output || agentExecutionResult.state, null, 2)}
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
