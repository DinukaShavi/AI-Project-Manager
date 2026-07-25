"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { taskApi } from "../../api";
import { CheckSquare, Plus, Filter, User, AlertCircle, RefreshCw } from "lucide-react";

const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function TasksPage() {
  const [tasks, setTasks] = useState<any[]>([
    { id: "t-1", title: "Implement pgvector SQLAlchemy Fallback", status: "done", priority: "high", story_points: 5, jira_issue_key: "TPM-101" },
    { id: "t-2", title: "Build Outbox Pattern Worker Event Bus", status: "done", priority: "critical", story_points: 8, jira_issue_key: "TPM-102" },
    { id: "t-3", title: "Create Multi-Agent DAG Workflow Engine", status: "done", priority: "high", story_points: 8, jira_issue_key: "TPM-103" },
    { id: "t-4", title: "Next.js 15 Dark Glassmorphism Dashboard", status: "in_progress", priority: "medium", story_points: 5, jira_issue_key: "TPM-104" },
    { id: "t-5", title: "Configure Slack & GitHub Webhook HMACs", status: "in_progress", priority: "medium", story_points: 5, jira_issue_key: "TPM-105" },
    { id: "t-6", title: "Setup Continuous Delivery Pipeline", status: "todo", priority: "low", story_points: 3, jira_issue_key: "TPM-106" },
  ]);

  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>("all");

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await taskApi.getProjectTasks(DUMMY_PROJECT_ID);
      if (res && res.tasks && res.tasks.length > 0) setTasks(res.tasks);
    } catch (e) {
      // Fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

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
              <button onClick={fetchTasks} className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10">
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </button>
              <button className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-sm shadow-lg shadow-purple-500/20 flex items-center gap-2">
                <Plus className="w-4 h-4" /> Create Task
              </button>
            </div>
          </div>

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

          {/* Tasks List */}
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
        </main>
      </div>
    </div>
  );
}
