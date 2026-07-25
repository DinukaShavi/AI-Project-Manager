"use client";

import React from "react";
import { GitHubCommit } from "../../types/github";
import { GitCommit, ExternalLink, RefreshCw, AlertCircle, Clock, User } from "lucide-react";

interface Props {
  commits: GitHubCommit[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export default function CommitActivity({ commits, loading, error, onRefresh }: Props) {
  if (loading) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium">Loading Commit Activity Log...</p>
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

  if (!commits || commits.length === 0) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl text-center">
        <GitCommit className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-white">No Commits Found</h3>
        <p className="text-xs text-slate-400 mt-1">Commits pushed to active repositories will log here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitCommit className="w-5 h-5 text-cyan-400" />
          <h3 className="text-lg font-bold text-white">Commit Log ({commits.length})</h3>
        </div>
        <button onClick={onRefresh} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 transition-all">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3">
        {commits.map((commit) => (
          <div
            key={commit.sha}
            className="p-4 rounded-2xl bg-white/5 border border-white/10 hover:border-cyan-500/40 backdrop-blur-xl transition-all flex flex-col md:flex-row md:items-center justify-between gap-3"
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 mt-0.5">
                <GitCommit className="w-4 h-4" />
              </div>

              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-2 py-0.5 rounded-md font-mono text-[11px] font-bold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                    {commit.short_sha}
                  </span>
                  <h4 className="text-sm font-semibold text-white">
                    {commit.message}
                  </h4>
                </div>

                <div className="flex items-center gap-3 mt-2 text-xs text-slate-400 flex-wrap">
                  <span className="flex items-center gap-1">
                    <User className="w-3 h-3 text-slate-400" /> {commit.author}
                  </span>
                  <span>•</span>
                  <span>Repo: <strong className="text-slate-200">{commit.repository}</strong></span>
                  <span>•</span>
                  <span className="flex items-center gap-1 text-slate-500">
                    <Clock className="w-3 h-3" /> {new Date(commit.timestamp).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            <a
              href={commit.html_url}
              target="_blank"
              rel="noreferrer"
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all self-end md:self-center"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
