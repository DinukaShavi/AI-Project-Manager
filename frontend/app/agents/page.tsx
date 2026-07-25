"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { agentApi } from "../../api";
import { Bot, Play, CheckCircle2, Cpu, History, RefreshCw } from "lucide-react";

export default function AgentsPage() {
  const [personas, setPersonas] = useState<any[]>([
    { type: "TechnicalPMAgent", role: "Technical Project Manager", description: "Sprint velocity analysis, task bottleneck identification, and story points allocation" },
    { type: "SprintPlanningAgent", role: "Sprint Planning Specialist", description: "Backlog grooming, dependency resolution, and capacity estimation" },
    { type: "RiskAnalysisAgent", role: "Risk Assessment Engine", description: "Predictive delivery risk evaluation and Monte Carlo simulation execution" },
    { type: "ArchitectureReviewAgent", role: "System Architecture Auditor", description: "Database RLS, security guard sanitization, and OTel tracing audit" },
  ]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="agents" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Bot className="w-8 h-8 text-purple-400" /> AI Agent Framework Personas & Executions
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Active persona capabilities, HTN planner state machines, and execution history.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {personas.map((agent) => (
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
                  <span className="text-[11px] text-slate-500">State: IDLE / READY</span>
                  <button className="px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold flex items-center gap-1.5">
                    <Play className="w-3.5 h-3.5" /> Execute Agent
                  </button>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
