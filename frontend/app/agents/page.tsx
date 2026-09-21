"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { agentApi, projectApi, Project, ApiError } from "../../api";
import { useAuth } from "../../hooks/use-auth";
import { Bot, Play, CheckCircle2, Cpu, RefreshCw, AlertCircle } from "lucide-react";

interface Persona {
  type: string;
  role: string;
  description: string;
  task: string;
}

const PERSONAS: Persona[] = [
  {
    type: "TechnicalPMAgent",
    role: "Technical Project Manager",
    description: "Sprint velocity analysis, task bottleneck identification, and story points allocation",
    task: "Analyze current sprint velocity and identify task bottlenecks",
  },
  {
    type: "CodeAnalystAgent",
    role: "Code Analysis Specialist",
    description: "Pull request review, commit quality assessment, and code health signals",
    task: "Review recent commits and pull requests for code quality issues",
  },
  {
    type: "RiskManagerAgent",
    role: "Risk Assessment Engine",
    description: "Predictive delivery risk evaluation and Monte Carlo simulation execution",
    task: "Assess delivery risk for the current sprint and flag at-risk items",
  },
  {
    type: "ArchitectureReviewerAgent",
    role: "System Architecture Auditor",
    description: "Database RLS, security guard sanitization, and OTel tracing audit",
    task: "Audit recent changes for architectural and security concerns",
  },
];

type ExecState = { loading: boolean; result: any; error: string | null };

export default function AgentsPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  const [execStates, setExecStates] = useState<Record<string, ExecState>>({});

  const loadProjects = useCallback(async () => {
    if (!organizationId) return;
    setProjectsLoading(true);
    try {
      const wsRes = await projectApi.getWorkspaces(organizationId);
      const projectLists = await Promise.all((wsRes.workspaces || []).map((ws) => projectApi.getProjects(ws.workspace_id)));
      const allProjects = projectLists.flatMap((p) => p.projects);
      setProjects(allProjects);
      setSelectedProjectId((prev) => (prev && allProjects.some((p) => p.project_id === prev) ? prev : allProjects[0]?.project_id || null));
    } catch (err) {
      setProjects([]);
      setSelectedProjectId(null);
    } finally {
      setProjectsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const canExecute = Boolean(organizationId && selectedProjectId);

  const handleExecute = async (persona: Persona) => {
    if (!organizationId || !selectedProjectId) return;
    setExecStates((prev) => ({ ...prev, [persona.type]: { loading: true, result: null, error: null } }));
    try {
      const res = await agentApi.executeAgentPersona({
        agent_type: persona.type,
        task: persona.task,
        organization_id: organizationId,
        project_id: selectedProjectId,
      });
      setExecStates((prev) => ({ ...prev, [persona.type]: { loading: false, result: res, error: null } }));
    } catch (err) {
      setExecStates((prev) => ({
        ...prev,
        [persona.type]: { loading: false, result: null, error: err instanceof ApiError ? err.message : "Execution failed" },
      }));
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="agents" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Bot className="w-8 h-8 text-purple-400" /> AI Agent Framework Personas
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Real persona execution via the AI Agent Framework -- each run makes a real LLM call and persists a real, queryable execution record.
              </p>
            </div>

            <div className="min-w-[220px]">
              <label className="text-xs font-medium text-slate-400 block mb-1">Project</label>
              <select
                value={selectedProjectId || ""}
                onChange={(e) => setSelectedProjectId(e.target.value || null)}
                disabled={projectsLoading || projects.length === 0}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white focus:outline-none focus:border-purple-500 disabled:opacity-50"
              >
                {projects.length === 0 && <option value="">{projectsLoading ? "Loading projects..." : "No projects available"}</option>}
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>{p.name}</option>
                ))}
              </select>
            </div>
          </div>

          {!canExecute && !projectsLoading && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/20 text-sm">
              <AlertCircle className="w-4 h-4 shrink-0" /> Select a real project above before executing an agent.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {PERSONAS.map((agent) => {
              const state = execStates[agent.type];
              return (
                <div key={agent.type} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl hover:border-purple-500/40 transition-all space-y-4 shadow-xl">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                        <Cpu className="w-6 h-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-white">{agent.role}</h3>
                        <span className="text-xs font-mono text-purple-300">{agent.type}</span>
                      </div>
                    </div>

                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Ready
                    </span>
                  </div>

                  <p className="text-xs text-slate-400">{agent.description}</p>

                  <div className="pt-2 border-t border-white/5 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">
                      State: {state?.loading ? "EXECUTING" : state?.result ? "COMPLETED" : state?.error ? "FAILED" : "IDLE / READY"}
                    </span>
                    <button
                      onClick={() => handleExecute(agent)}
                      disabled={!canExecute || state?.loading}
                      className="px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {state?.loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                      {state?.loading ? "Executing..." : "Execute Agent"}
                    </button>
                  </div>

                  {state?.result && (
                    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-1">
                      <div className="font-semibold">Execution {state.result.status} -- {state.result.execution_id}</div>
                      <pre className="text-[11px] font-mono opacity-80 whitespace-pre-wrap">{JSON.stringify(state.result.output, null, 2)}</pre>
                    </div>
                  )}
                  {state?.error && (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
                      {state.error}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}
