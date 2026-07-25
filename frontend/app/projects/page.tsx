"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { projectApi, analyticsApi } from "../../api";
import { FolderKanban, Plus, Layers, Activity, ShieldCheck, ArrowRight, RefreshCw } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";
const DUMMY_PROJECT_ID = "00000000-0000-0000-0000-000000000002";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([
    { id: DUMMY_PROJECT_ID, name: "AI-Project-Manager Enterprise", description: "Multi-agent technical project manager kernel & pgvector context engine", created_at: "2026-07-20T00:00:00Z" },
    { id: "proj-102", name: "Cloud Infrastructure Terraform Pipeline", description: "AWS RDS PostgreSQL, Redis ElastiCache & EKS Kubernetes manifests", created_at: "2026-07-22T00:00:00Z" },
  ]);
  const [analytics, setAnalytics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const aData = await analyticsApi.getSprintAnalytics(DUMMY_PROJECT_ID);
        setAnalytics(aData);
      } catch (e) {
        // Fallback
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="projects" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <FolderKanban className="w-8 h-8 text-indigo-400" /> Active Software Projects
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Workspace project management, sprint velocity tracking, and project intelligence.
              </p>
            </div>

            <button className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center gap-2">
              <Plus className="w-4 h-4" /> New Project
            </button>
          </div>

          {/* Projects Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {projects.map((proj) => (
              <div key={proj.id} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl hover:border-indigo-500/40 transition-all space-y-4 shadow-xl">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-xl font-bold text-white">{proj.name}</h3>
                    <p className="text-xs text-slate-400 mt-1">{proj.description}</p>
                  </div>
                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> Healthy
                  </span>
                </div>

                {analytics && proj.id === DUMMY_PROJECT_ID && (
                  <div className="p-4 rounded-xl bg-white/5 space-y-2 border border-white/5">
                    <div className="flex justify-between text-xs text-slate-300">
                      <span>Sprint Story Points</span>
                      <span className="font-bold text-indigo-300">{analytics.completed_story_points} / {analytics.total_story_points} Completed</span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-2">
                      <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${analytics.completion_rate_percentage}%` }} />
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-white/5">
                  <span>Created: {new Date(proj.created_at).toLocaleDateString()}</span>
                  <button className="text-indigo-400 font-semibold flex items-center gap-1 hover:text-indigo-300">
                    Project Details <ArrowRight className="w-3.5 h-3.5" />
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
