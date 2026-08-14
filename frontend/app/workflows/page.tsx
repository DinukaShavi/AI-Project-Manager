"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, workflowApi, Project, ApiError } from "../../api";
import { Network, Play, CheckCircle2, RefreshCw } from "lucide-react";

export default function WorkflowsPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established in frontend/app/page.tsx, agent-dashboard/page.tsx, projects/page.tsx).
  // A project is optional here: project_id is an optional field on the backend workflow
  // execution contract, so an organization with no projects yet can still run a workflow.
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  const [selectedTemplate, setSelectedTemplate] = useState("sprint_planning");
  const [loading, setLoading] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    if (!organizationId) return;
    setProjectsLoading(true);
    try {
      const wsRes = await projectApi.getWorkspaces(organizationId);
      if (!wsRes.workspaces || wsRes.workspaces.length === 0) {
        setProjects([]);
        setSelectedProjectId(null);
        return;
      }
      const projectLists = await Promise.all(wsRes.workspaces.map((ws) => projectApi.getProjects(ws.workspace_id)));
      const allProjects = projectLists.flatMap((p) => p.projects);
      setProjects(allProjects);
      setSelectedProjectId((prev) => (prev && allProjects.some((p) => p.project_id === prev) ? prev : allProjects[0]?.project_id || null));
    } catch (err) {
      // A failure to discover projects doesn't block workflow execution -- project_id is
      // optional, so we simply proceed without one rather than showing a hard error state.
      setProjects([]);
      setSelectedProjectId(null);
    } finally {
      setProjectsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleExecuteWorkflow = async () => {
    if (!organizationId) return;
    setLoading(true);
    setExecutionResult(null);
    setExecutionError(null);
    try {
      const res = await workflowApi.executeWorkflow({
        template: selectedTemplate,
        organization_id: organizationId,
        project_id: selectedProjectId || undefined,
      });
      setExecutionResult(res);
    } catch (err) {
      setExecutionError(err instanceof ApiError ? err.message : "Workflow execution failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="workflows" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Network className="w-8 h-8 text-indigo-400" /> Multi-Agent DAG Workflow Engine
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Execute asynchronous agent DAG execution graphs with topological sort dependency resolution.
              </p>
            </div>

            {projects.length > 1 && (
              <select
                value={selectedProjectId || ""}
                onChange={(e) => setSelectedProjectId(e.target.value || null)}
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

          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
            <h3 className="text-lg font-bold text-white">Select Workflow Template</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { id: "sprint_planning", name: "Sprint Planning & Backlog Grooming", agents: "TechnicalPMAgent -> SprintPlanningAgent" },
                { id: "pr_review", name: "Pull Request & Code Review Sync", agents: "TechnicalPMAgent -> RiskAnalysisAgent" },
                { id: "risk_assessment", name: "Monte Carlo Delivery Risk Audit", agents: "RiskAnalysisAgent -> ArchitectureReviewAgent" },
              ].map((tmpl) => (
                <div
                  key={tmpl.id}
                  onClick={() => setSelectedTemplate(tmpl.id)}
                  className={`p-4 rounded-xl cursor-pointer border transition-all ${
                    selectedTemplate === tmpl.id
                      ? "bg-indigo-600/20 border-indigo-500/50 shadow-lg shadow-indigo-500/10"
                      : "bg-white/5 border-white/5 hover:border-white/20"
                  }`}
                >
                  <h4 className="text-sm font-bold text-white">{tmpl.name}</h4>
                  <p className="text-xs text-slate-400 mt-1">{tmpl.agents}</p>
                </div>
              ))}
            </div>

            {!projectsLoading && projects.length === 0 && (
              <p className="text-xs text-slate-400">
                No project selected -- this workflow will run without project-specific context.
              </p>
            )}

            <button
              onClick={handleExecuteWorkflow}
              disabled={loading || !organizationId}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Execute Asynchronous DAG Workflow
            </button>

            {executionError && (
              <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                {executionError}
              </div>
            )}

            {executionResult && (
              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono text-indigo-300 space-y-1">
                <p className="text-white font-bold text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" /> DAG Execution Completed
                </p>
                <pre className="overflow-x-auto text-[11px] opacity-80 mt-2">{JSON.stringify(executionResult, null, 2)}</pre>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
