"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { workflowApi } from "../../api";
import { Network, Play, CheckCircle2, RefreshCw, Cpu, Layers } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";
const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function WorkflowsPage() {
  const [selectedTemplate, setSelectedTemplate] = useState("sprint_planning");
  const [loading, setLoading] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);

  const handleExecuteWorkflow = async () => {
    setLoading(true);
    setExecutionResult(null);
    try {
      const res = await workflowApi.executeWorkflow({
        template: selectedTemplate,
        organization_id: DUMMY_ORG_ID,
        project_id: DUMMY_PROJECT_ID,
      });
      setExecutionResult(res);
    } catch (err: any) {
      setExecutionResult({ error: err.message || "Workflow execution failed" });
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
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Network className="w-8 h-8 text-indigo-400" /> Multi-Agent DAG Workflow Engine
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Execute asynchronous agent DAG execution graphs with topological sort dependency resolution.
              </p>
            </div>
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

            <button
              onClick={handleExecuteWorkflow}
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Execute Asynchronous DAG Workflow
            </button>

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
