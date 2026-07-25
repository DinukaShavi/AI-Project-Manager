"use client";

import React from "react";
import { GitHubIssue } from "../../types/github";
import { AlertCircle, CheckCircle2, MessageSquare, ExternalLink, RefreshCw } from "lucide-react";

interface Props {
  issues: GitHubIssue[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export default function IssueTracker({ issues, loading, error, onRefresh }: Props) {
  if (loading) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-amber-400 animate-spin" />
        <p className="text-sm text-slate-400 font-medium">Loading GitHub Issues...</p>
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

  if (!issues || issues.length === 0) {
    return (
      <div className="p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl text-center">
        <AlertCircle className="w-10 h-10 text-slate-500 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-white">No GitHub Issues Found</h3>
        <p className="text-xs text-slate-400 mt-1">Issues created across repositories will display here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-amber-400" />
          <h3 className="text-lg font-bold text-white">GitHub Issues ({issues.length})</h3>
        </div>
        <button onClick={onRefresh} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 transition-all">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-3">
        {issues.map((issue) => (
          <div
            key={issue.id}
            className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-amber-500/40 backdrop-blur-xl transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
          >
            <div className="flex items-start gap-3">
              {issue.state === "closed" ? (
                <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 mt-1">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
              ) : (
                <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 mt-1">
                  <AlertCircle className="w-4 h-4" />
                </div>
              )}

              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono text-slate-400">#{issue.number}</span>
                  <h4 className="text-base font-bold text-white hover:text-amber-300 transition-colors">
                    {issue.title}
                  </h4>
                  {issue.state === "closed" ? (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                      Closed
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      Open
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 mt-2 text-xs text-slate-400 flex-wrap">
                  <span>Author: <strong className="text-slate-200">{issue.author}</strong></span>
                  <span>•</span>
                  <span>Repo: <strong className="text-slate-200">{issue.repository}</strong></span>
                  <span>•</span>
                  <span className="flex items-center gap-1 text-slate-400">
                    <MessageSquare className="w-3.5 h-3.5" /> {issue.comments_count} comments
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 self-end md:self-center">
              {issue.labels && issue.labels.map((label) => (
                <span key={label} className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-white/5 text-slate-300 border border-white/10">
                  {label}
                </span>
              ))}
              <a
                href={issue.html_url}
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
