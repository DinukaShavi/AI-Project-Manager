"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useJiraProjects, useJiraIssues, useJiraSprints, useJiraMetrics } from "../../hooks/useJira";
import { LayoutGrid, Ticket, Zap, Users, TrendingUp, RefreshCw, AlertCircle } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function JiraIntegrationPage() {
  const [activeTab, setActiveTab] = useState<"projects" | "issues" | "sprints" | "workload" | "velocity">("issues");

  const { projects, loading: loadingProjects, error: errorProjects, refresh: refreshProjects } = useJiraProjects(DUMMY_ORG_ID);
  const { issues, loading: loadingIssues, error: errorIssues, refresh: refreshIssues } = useJiraIssues(DUMMY_ORG_ID);
  const { sprints, loading: loadingSprints, error: errorSprints, refresh: refreshSprints } = useJiraSprints(DUMMY_ORG_ID);
  const { workload, velocity, loading: loadingMetrics, error: errorMetrics, refresh: refreshMetrics } = useJiraMetrics(DUMMY_ORG_ID);

  const handleRefreshAll = () => {
    refreshProjects();
    refreshIssues();
    refreshSprints();
    refreshMetrics();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-blue-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="jira" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          {/* Header Title */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                Jira Platform Integration
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Sprint planning, workload capacity distribution, historical velocity, and Jira issue tracking.
              </p>
            </div>

            <button
              onClick={handleRefreshAll}
              className="px-4 py-2.5 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 font-semibold text-sm border border-blue-500/30 transition-all flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" /> Refresh Jira Sync
            </button>
          </div>

          {/* Sub-Navigation Tabs */}
          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-x-auto">
            <button
              onClick={() => setActiveTab("issues")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "issues"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Ticket className="w-4 h-4" /> Jira Issues ({issues.length})
            </button>

            <button
              onClick={() => setActiveTab("sprints")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "sprints"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Zap className="w-4 h-4" /> Sprints ({sprints.length})
            </button>

            <button
              onClick={() => setActiveTab("projects")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "projects"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <LayoutGrid className="w-4 h-4" /> Projects ({projects.length})
            </button>

            <button
              onClick={() => setActiveTab("workload")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "workload"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Users className="w-4 h-4" /> Team Workload
            </button>

            <button
              onClick={() => setActiveTab("velocity")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "velocity"
                  ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <TrendingUp className="w-4 h-4" /> Velocity Metrics
            </button>
          </div>

          {/* Tab Views */}
          {activeTab === "issues" && (
            <div className="space-y-3">
              {loadingIssues ? (
                <div className="p-8 text-center text-slate-400 font-medium flex items-center justify-center gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-blue-400" /> Loading Jira Issues...
                </div>
              ) : errorIssues ? (
                <div className="p-4 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-between">
                  <span>{errorIssues}</span>
                  <button onClick={refreshIssues} className="px-3 py-1 rounded bg-rose-500/20 text-xs font-semibold">Retry</button>
                </div>
              ) : (
                issues.map((iss) => (
                  <div key={iss.id} className="p-4 rounded-2xl bg-white/5 border border-white/10 hover:border-blue-500/40 backdrop-blur-xl flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 font-mono text-xs font-bold border border-blue-500/20">{iss.key}</span>
                      <div>
                        <h4 className="text-sm font-bold text-white">{iss.summary}</h4>
                        <p className="text-xs text-slate-400 mt-0.5">Assignee: {iss.assignee} • Points: {iss.story_points}</p>
                      </div>
                    </div>
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{iss.status}</span>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "sprints" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {loadingSprints ? (
                <div className="p-8 text-center text-slate-400 font-medium col-span-2">Loading Sprints...</div>
              ) : (
                sprints.map((sprint) => (
                  <div key={sprint.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-base font-bold text-white">{sprint.name}</h4>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${sprint.state === "active" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-slate-800 text-slate-400"}`}>
                        {sprint.state}
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-2 overflow-hidden">
                      <div className="bg-gradient-to-r from-blue-500 to-indigo-500 h-2" style={{ width: `${(sprint.completed_story_points / sprint.total_story_points) * 100}%` }} />
                    </div>
                    <p className="text-xs text-slate-400">{sprint.completed_story_points} / {sprint.total_story_points} Story Points Completed</p>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "workload" && (
            <div className="space-y-3">
              {workload.map((member) => (
                <div key={member.assignee} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-bold text-white">{member.assignee}</h4>
                    <p className="text-xs text-slate-400">{member.assigned_issues} issues • {member.total_story_points} story points</p>
                  </div>
                  <span className="text-sm font-bold text-blue-400">{member.capacity_percentage}% Capacity</span>
                </div>
              ))}
            </div>
          )}

          {activeTab === "velocity" && velocity && (
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">Historical Velocity Trend</h3>
                <span className="text-sm font-bold text-emerald-400">Avg: {velocity.average_velocity} Points / Sprint</span>
              </div>
              <div className="grid grid-cols-4 gap-3 pt-2">
                {velocity.sprint_velocity_history.map((hist) => (
                  <div key={hist.sprint} className="p-3 rounded-xl bg-white/5 text-center">
                    <p className="text-xs text-slate-400">{hist.sprint}</p>
                    <p className="text-lg font-extrabold text-white mt-1">{hist.completed} / {hist.committed}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
