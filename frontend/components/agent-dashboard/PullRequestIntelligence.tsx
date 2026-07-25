"use client";

import React from "react";
import { GitPullRequest, Clock, AlertCircle, ShieldCheck, MessageSquare, ExternalLink } from "lucide-react";

interface Props {
  pullRequests: any[];
}

export default function PullRequestIntelligence({ pullRequests }: Props) {
  const defaultPRs = pullRequests.length > 0 ? pullRequests : [
    {
      id: 501,
      number: 42,
      title: "Implement Multi-Dimensional Rate Limiter & Token Bucket Engine",
      state: "open",
      author: "dinukashavi",
      repository: "DinukaShavi/AI-Project-Manager",
      html_url: "https://github.com/DinukaShavi/AI-Project-Manager/pull/42",
      delay_hours: 28,
      risk: "low",
    },
    {
      id: 504,
      number: 39,
      title: "Next.js 15 Dark Glassmorphism Dashboard UI Polish",
      state: "open",
      author: "frontend-dev",
      repository: "DinukaShavi/AI-Project-Manager",
      html_url: "https://github.com/DinukaShavi/AI-Project-Manager/pull/39",
      delay_hours: 14,
      risk: "low",
    },
  ];

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <GitPullRequest className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Pull Request Intelligence & Review Delays</h3>
            <p className="text-xs text-slate-400">Automated risk analysis and pending code review bottlenecks</p>
          </div>
        </div>
      </div>

      <div className="space-y-3 pt-1">
        {defaultPRs.map((pr) => (
          <div
            key={pr.id}
            className="p-4 rounded-xl bg-white/5 border border-white/5 hover:border-indigo-500/30 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 mt-0.5">
                <GitPullRequest className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono text-slate-400">#{pr.number}</span>
                  <h4 className="text-sm font-bold text-white">{pr.title}</h4>
                </div>
                <p className="text-xs text-slate-400 mt-1">Author: {pr.author} • Repo: {pr.repository}</p>
              </div>
            </div>

            <div className="flex items-center gap-3 self-end md:self-center">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                <Clock className="w-3 h-3" /> {pr.delay_hours || 24}h Review Delay
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <ShieldCheck className="w-3 h-3" /> Low Risk Diff
              </span>
              <a
                href={pr.html_url}
                target="_blank"
                rel="noreferrer"
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
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
