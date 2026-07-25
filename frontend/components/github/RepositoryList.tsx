"use client";

import React from "react";
import { GitHubRepository } from "../../types/github";
import { FolderGit2, Star, AlertCircle, ExternalLink, RefreshCw, Lock, Globe } from "lucide-react";

interface Props {
  repositories: GitHubRepository[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export default function RepositoryList({ repositories, loading, error, onRefresh }: Props) {
  if (loading) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-purple-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium">Fetching GitHub Repositories...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertCircle className="w-5 h-5" />
          <span className="text-sm font-medium">{error}</span>
        </div>
        <button onClick={onRefresh} className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-xs font-semibold">
          Retry
        </button>
      </div>
    );
  }

  if (!repositories || repositories.length === 0) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl text-center">
        <FolderGit2 className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-white">No Repositories Found</h3>
        <p className="text-xs text-slate-400 mt-1">Connect your GitHub organization account to sync repositories.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderGit2 className="w-5 h-5 text-purple-400" />
          <h3 className="text-lg font-bold text-white">Repositories ({repositories.length})</h3>
        </div>
        <button onClick={onRefresh} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 transition-all">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {repositories.map((repo) => (
          <div
            key={repo.id}
            className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-purple-500/40 backdrop-blur-xl transition-all group"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-base font-bold text-white group-hover:text-purple-300 transition-colors">
                    {repo.name}
                  </h4>
                  {repo.private ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      <Lock className="w-2.5 h-2.5" /> Private
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      <Globe className="w-2.5 h-2.5" /> Public
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">{repo.description || "No description provided."}</p>
              </div>
              <a
                href={repo.html_url}
                target="_blank"
                rel="noreferrer"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>

            <div className="flex items-center gap-4 mt-4 pt-3 border-t border-white/5 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <Star className="w-3.5 h-3.5 text-amber-400" /> {repo.stargazers_count} stars
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 text-purple-400" /> {repo.open_issues_count} open issues
              </span>
              <span className="ml-auto font-mono text-[11px] text-slate-500">{repo.default_branch}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
