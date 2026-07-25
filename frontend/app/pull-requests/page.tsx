"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import PullRequestDashboard from "../../components/github/PullRequestDashboard";
import { githubApi, securityApi } from "../../api";
import { GitPullRequest, ShieldCheck, Sparkles } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function PullRequestsPage() {
  const [prs, setPRs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPRs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await githubApi.getPullRequests(DUMMY_ORG_ID);
      setPRs(res.pull_requests || []);
    } catch (err: any) {
      setError(err.message || "Failed to load pull requests");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPRs();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="pull_requests" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <GitPullRequest className="w-8 h-8 text-indigo-400" /> Pull Request Monitoring & AI Code Insights
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Automated PR risk scoring, review delay warnings, and AI security insights.
            </p>
          </div>

          <PullRequestDashboard pullRequests={prs} loading={loading} error={error} onRefresh={fetchPRs} />
        </main>
      </div>
    </div>
  );
}
