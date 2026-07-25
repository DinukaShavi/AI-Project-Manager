"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import GithubConnectionCard from "../../components/github/GithubConnectionCard";
import RepositoryList from "../../components/github/RepositoryList";
import PullRequestDashboard from "../../components/github/PullRequestDashboard";
import CommitActivity from "../../components/github/CommitActivity";
import IssueTracker from "../../components/github/IssueTracker";
import {
  useGithubRepositories,
  useGithubPullRequests,
  useGithubCommits,
  useGithubIssues,
} from "../../hooks/useGithub";
import { FolderGit2, GitPullRequest, GitCommit, AlertCircle, RefreshCw } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function GithubIntegrationPage() {
  const [activeTab, setActiveTab] = useState<"repos" | "prs" | "commits" | "issues">("repos");

  const { repositories, loading: loadingRepos, error: errorRepos, refresh: refreshRepos } = useGithubRepositories(DUMMY_ORG_ID);
  const { pullRequests, loading: loadingPRs, error: errorPRs, refresh: refreshPRs } = useGithubPullRequests(DUMMY_ORG_ID);
  const { commits, loading: loadingCommits, error: errorCommits, refresh: refreshCommits } = useGithubCommits(DUMMY_ORG_ID);
  const { issues, loading: loadingIssues, error: errorIssues, refresh: refreshIssues } = useGithubIssues(DUMMY_ORG_ID);

  const handleRefreshAll = () => {
    refreshRepos();
    refreshPRs();
    refreshCommits();
    refreshIssues();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      {/* Background Neon Glow */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-purple-600/10 rounded-full blur-3xl" />
        <div className="absolute top-1/3 -right-40 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl" />
      </div>

      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="github" onTabChange={() => {}} />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6 relative z-10">
          {/* Header Title */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                GitHub Repository & PR Integration
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Real-time pull request dashboard, commit activity tracking, and GitHub issue sync.
              </p>
            </div>

            <button
              onClick={handleRefreshAll}
              className="px-4 py-2.5 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 font-semibold text-sm border border-purple-500/30 transition-all flex items-center gap-2 self-start md:self-auto"
            >
              <RefreshCw className="w-4 h-4" /> Refresh All Modules
            </button>
          </div>

          {/* GitHub OAuth Connection Card */}
          <GithubConnectionCard orgId={DUMMY_ORG_ID} onRefreshAll={handleRefreshAll} />

          {/* Sub-Navigation Tabs */}
          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-x-auto">
            <button
              onClick={() => setActiveTab("repos")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "repos"
                  ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <FolderGit2 className="w-4 h-4" /> Repositories ({repositories.length})
            </button>

            <button
              onClick={() => setActiveTab("prs")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "prs"
                  ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <GitPullRequest className="w-4 h-4" /> Pull Requests ({pullRequests.length})
            </button>

            <button
              onClick={() => setActiveTab("commits")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "commits"
                  ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <GitCommit className="w-4 h-4" /> Commit Activity ({commits.length})
            </button>

            <button
              onClick={() => setActiveTab("issues")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "issues"
                  ? "bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-lg shadow-purple-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <AlertCircle className="w-4 h-4" /> Issue Tracker ({issues.length})
            </button>
          </div>

          {/* Active Tab Panel */}
          {activeTab === "repos" && (
            <RepositoryList
              repositories={repositories}
              loading={loadingRepos}
              error={errorRepos}
              onRefresh={refreshRepos}
            />
          )}

          {activeTab === "prs" && (
            <PullRequestDashboard
              pullRequests={pullRequests}
              loading={loadingPRs}
              error={errorPRs}
              onRefresh={refreshPRs}
            />
          )}

          {activeTab === "commits" && (
            <CommitActivity
              commits={commits}
              loading={loadingCommits}
              error={errorCommits}
              onRefresh={refreshCommits}
            />
          )}

          {activeTab === "issues" && (
            <IssueTracker
              issues={issues}
              loading={loadingIssues}
              error={errorIssues}
              onRefresh={refreshIssues}
            />
          )}
        </main>
      </div>
    </div>
  );
}
