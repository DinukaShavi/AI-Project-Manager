"use client";

import React from "react";
import { GitHubPullRequest } from "../../types/github";
import { GitPullRequest, GitMerge, ExternalLink, RefreshCw, AlertCircle, Plus, Minus } from "lucide-react";

interface Props {
  pullRequests: GitHubPullRequest[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export default function PullRequestDashboard({ pullRequests, loading, error, onRefresh }: Props) {
  if (loading) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium">Loading Pull Requests...</p>
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

  if (!pullRequests || pullRequests.length === 0) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl text-center">
        <GitPullRequest className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-white">No Pull Requests Found</h3>
        <p className="text-xs text-slate-400 mt-1">Pull requests opened across repositories will show here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitPullRequest className="w-5 h-5 text-indigo-400" />
          <h3 className="text-lg font-bold text-white">Pull Requests ({pullRequests.length})</h3>
        </div>
        <button onClick={onRefresh} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 transition-all">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3">
        {pullRequests.map((pr) => (
          <div
            key={pr.id}
            className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-indigo-500/40 backdrop-blur-xl transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
          >
            <div className="flex items-start gap-3">
              {pr.state === "merged" ? (
                <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 mt-1">
                  <GitMerge className="w-4 h-4" />
                </div>
              ) : (
                <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mt-1">
                  <GitPullRequest className="w-4 h-4" />
                </div>
              )}

              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono text-slate-400">#{pr.number}</span>
                  <h4 className="text-base font-bold text-white hover:text-indigo-300 transition-colors">
                    {pr.title}
                  </h4>
                  {pr.state === "merged" ? (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                      Merged
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Open
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 mt-2 text-xs text-slate-400 flex-wrap">
                  <span>Author: <strong className="text-slate-200">{pr.author}</strong></span>
                  <span>•</span>
                  <span>Repo: <strong className="text-slate-200">{pr.repository}</strong></span>
                  <span>•</span>
                  <span className="text-emerald-400 font-mono flex items-center gap-0.5">
                    <Plus className="w-3 h-3" />{pr.additions}
                  </span>
                  <span className="text-rose-400 font-mono flex items-center gap-0.5">
                    <Minus className="w-3 h-3" />{pr.deletions}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 self-end md:self-center">
              {pr.labels && pr.labels.map((label) => (
                <span key={label} className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-white/5 text-slate-300 border border-white/10">
                  {label}
                </span>
              ))}
              <a
                href={pr.html_url}
                target="_blank"
                rel="noreferrer"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all ml-2"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
