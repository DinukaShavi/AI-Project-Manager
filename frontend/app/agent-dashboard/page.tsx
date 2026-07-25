"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import ProjectHealthOverview from "../../components/agent-dashboard/ProjectHealthOverview";
import DeveloperWorkloadPanel from "../../components/agent-dashboard/DeveloperWorkloadPanel";
import PullRequestIntelligence from "../../components/agent-dashboard/PullRequestIntelligence";
import AIRecommendationsPanel from "../../components/agent-dashboard/AIRecommendationsPanel";
import AgentActionsConsole from "../../components/agent-dashboard/AgentActionsConsole";
import { getSprintAnalytics, githubApi, jiraApi } from "../../lib/api";
import { Bot, RefreshCw, LayoutDashboard } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";
const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function AgentDashboardPage() {
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

  const [pullRequests, setPullRequests] = useState<any[]>([]);
  const [workload, setWorkload] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const aData = await getSprintAnalytics(DUMMY_PROJECT_ID);
      if (aData) setAnalytics(aData);
    } catch (e) {
      // Fallback active
    }

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
    setLoading(false);
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

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
                Single pane of glass across GitHub, Jira, Slack, and Google Calendar.
              </p>
            </div>

            <button
              onClick={loadDashboardData}
              disabled={loading}
              className="px-4 py-2.5 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 font-semibold text-sm border border-purple-500/30 transition-all flex items-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh PM Telemetry
            </button>
          </div>

          {/* Section 1: Project Health Overview */}
          <ProjectHealthOverview analytics={analytics} />

          {/* Section 2 & Section 3: Developer Workload & Pull Request Intelligence Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <DeveloperWorkloadPanel workload={workload} />
            <PullRequestIntelligence pullRequests={pullRequests} />
          </div>

          {/* Section 4: AI Autonomous Recommendations */}
          <AIRecommendationsPanel />

          {/* Section 5: Agent Action Execution Console */}
          <AgentActionsConsole />
        </main>
      </div>
    </div>
  );
}
