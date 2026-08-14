"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import GithubConnectionCard from "../../components/github/GithubConnectionCard";
import PullRequestDashboard from "../../components/github/PullRequestDashboard";
import CommitActivity from "../../components/github/CommitActivity";
import IssueTracker from "../../components/github/IssueTracker";
import {
  useGithubPullRequests,
  useGithubCommits,
  useGithubIssues,
} from "../../hooks/useGithub";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, githubApi, Project, ApiError } from "../../api";
import { DiscoveredGitHubRepo, LinkedGitHubRepo } from "../../types/github";
import { FolderGit2, GitPullRequest, GitCommit, AlertCircle, RefreshCw, Search, Link2, ShieldAlert } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function GithubIntegrationPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  const [activeTab, setActiveTab] = useState<"repos" | "prs" | "commits" | "issues">("repos");

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established across this session's other real-data-wiring pages).
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  const [linkedRepos, setLinkedRepos] = useState<LinkedGitHubRepo[]>([]);
  const [loadingLinked, setLoadingLinked] = useState(true);
  const [linkedError, setLinkedError] = useState<string | null>(null);

  const [discovered, setDiscovered] = useState<DiscoveredGitHubRepo[] | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [linkingRepoId, setLinkingRepoId] = useState<string | null>(null);

  // These three tabs remain sourced from the documented GitHub mock GET endpoints (confirmed
  // hardcoded server-side, ignoring organization_id entirely) -- real PR/commit/issue listing
  // per repository is a separate, larger piece of work this turn deliberately doesn't build.
  const { pullRequests, loading: loadingPRs, error: errorPRs, refresh: refreshPRs } = useGithubPullRequests(DUMMY_ORG_ID);
  const { commits, loading: loadingCommits, error: errorCommits, refresh: refreshCommits } = useGithubCommits(DUMMY_ORG_ID);
  const { issues, loading: loadingIssues, error: errorIssues, refresh: refreshIssues } = useGithubIssues(DUMMY_ORG_ID);

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

  const loadLinkedRepos = useCallback(async (projectId: string) => {
    setLoadingLinked(true);
    setLinkedError(null);
    try {
      const res = await githubApi.getLinkedRepositories(projectId);
      setLinkedRepos(res.repositories);
    } catch (err) {
      setLinkedError(err instanceof ApiError ? err.message : "Failed to load linked repositories.");
    } finally {
      setLoadingLinked(false);
    }
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadLinkedRepos(selectedProjectId);
    } else {
      setLinkedRepos([]);
      setLoadingLinked(false);
    }
  }, [selectedProjectId, loadLinkedRepos]);

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoverError(null);
    try {
      const res = await githubApi.discoverRepositories();
      setDiscovered(res.repositories);
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Failed to discover repositories.");
    } finally {
      setDiscovering(false);
    }
  };

  const handleLink = async (repo: DiscoveredGitHubRepo) => {
    if (!selectedProjectId) return;
    setLinkingRepoId(repo.external_repo_id);
    try {
      await githubApi.linkRepository({
        project_id: selectedProjectId,
        external_repo_id: repo.external_repo_id,
        name: repo.name,
        clone_url: repo.clone_url,
      });
      await loadLinkedRepos(selectedProjectId);
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Failed to link repository.");
    } finally {
      setLinkingRepoId(null);
    }
  };

  const handleRefreshAll = () => {
    if (selectedProjectId) loadLinkedRepos(selectedProjectId);
    refreshPRs();
    refreshCommits();
    refreshIssues();
  };

  const linkedRepoIds = new Set(linkedRepos.map((r) => r.external_repo_id));

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

            <div className="flex items-center gap-3">
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
              <button
                onClick={handleRefreshAll}
                className="px-4 py-2.5 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 font-semibold text-sm border border-purple-500/30 transition-all flex items-center gap-2 self-start md:self-auto"
              >
                <RefreshCw className="w-4 h-4" /> Refresh All Modules
              </button>
            </div>
          </div>

          {/* GitHub OAuth Connection Card */}
          <GithubConnectionCard orgId={organizationId || ""} onRefreshAll={handleRefreshAll} />

          {/* Connect a Repository -- real GitHub API discovery + real linking */}
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Link2 className="w-5 h-5 text-purple-400" /> Connect a Repository
              </h2>
              <button
                onClick={handleDiscover}
                disabled={discovering || !selectedProjectId}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold flex items-center gap-2 disabled:opacity-50"
              >
                {discovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />} Discover Repositories
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Lists real repositories your connected GitHub account can access, and links one to the selected project.
              Requires GitHub to be connected above.
            </p>

            {discoverError && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                <ShieldAlert className="w-3.5 h-3.5 shrink-0" /> {discoverError}
              </div>
            )}

            {discovered && (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {discovered.length === 0 ? (
                  <p className="text-xs text-slate-500">No repositories found for the connected account.</p>
                ) : (
                  discovered.map((repo) => {
                    const alreadyLinked = linkedRepoIds.has(repo.external_repo_id);
                    return (
                      <div key={repo.external_repo_id} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
                        <div>
                          <p className="text-sm text-white">{repo.name}</p>
                          <p className="text-xs text-slate-500">{repo.private ? "Private" : "Public"} · {repo.default_branch}</p>
                        </div>
                        <button
                          onClick={() => handleLink(repo)}
                          disabled={alreadyLinked || linkingRepoId === repo.external_repo_id || !selectedProjectId}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 disabled:opacity-50"
                        >
                          {alreadyLinked ? "Linked" : linkingRepoId === repo.external_repo_id ? "Linking..." : "Link to Project"}
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>

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
              <FolderGit2 className="w-4 h-4" /> Linked Repositories ({linkedRepos.length})
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
            <div className="space-y-3">
              {loadingLinked ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading linked repositories...</div>
              ) : linkedError ? (
                <div className="p-8 text-center text-rose-300 text-sm">{linkedError}</div>
              ) : !selectedProjectId ? (
                <div className="p-8 text-center text-slate-400 text-sm">Select a project above to view its linked repositories.</div>
              ) : linkedRepos.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  No repositories linked to this project yet. Use "Discover Repositories" above to link one.
                </div>
              ) : (
                linkedRepos.map((repo) => (
                  <div key={repo.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-purple-500/40 backdrop-blur-xl flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                        <FolderGit2 className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-base font-bold text-white">{repo.name}</h4>
                        <p className="text-xs text-slate-400 mt-1 font-mono">{repo.external_repo_id}</p>
                      </div>
                    </div>
                    <a href={repo.clone_url.replace(/\.git$/, "")} target="_blank" rel="noreferrer" className="text-xs text-purple-300 hover:text-purple-200 font-semibold">
                      View on GitHub
                    </a>
                  </div>
                ))
              )}
            </div>
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
