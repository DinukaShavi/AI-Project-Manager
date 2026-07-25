"use client";

import React from "react";
import { ShieldCheck, AlertTriangle, CheckCircle2, TrendingUp, Activity, Layers } from "lucide-react";

interface Props {
  analytics: any;
}

export default function ProjectHealthOverview({ analytics }: Props) {
  const completionPct = analytics?.completion_rate_percentage || 61.8;
  const riskIndex = analytics?.delivery_risk_index || 0.15;
  const riskLevel = analytics?.risk_level || "low";

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-6 shadow-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Project Health Overview</h2>
            <p className="text-xs text-slate-400">Synthesized real-time telemetry across Jira, GitHub & Slack</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {riskLevel === "low" ? (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4" /> Healthy • Low Risk
            </span>
          ) : (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" /> Attention Required
            </span>
          )}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
          <span className="text-xs text-slate-400">Delivery Risk Index</span>
          <p className="text-2xl font-extrabold text-emerald-400">{riskIndex} <span className="text-xs font-normal text-slate-400">/ 1.0</span></p>
          <div className="w-full bg-slate-900 rounded-full h-1.5 mt-2">
            <div className="bg-emerald-400 h-1.5 rounded-full" style={{ width: `${riskIndex * 100}%` }} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
          <span className="text-xs text-slate-400">Sprint Story Points</span>
          <p className="text-2xl font-extrabold text-white">{analytics?.completed_story_points || 21} <span className="text-xs font-normal text-slate-400">/ {analytics?.total_story_points || 34}</span></p>
          <div className="w-full bg-slate-900 rounded-full h-1.5 mt-2">
            <div className="bg-purple-500 h-1.5 rounded-full" style={{ width: `${completionPct}%` }} />
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
          <span className="text-xs text-slate-400">Sprint Task Status</span>
          <p className="text-2xl font-extrabold text-white">{analytics?.completed_tasks || 5} <span className="text-xs font-normal text-slate-400">Done ({analytics?.in_progress_tasks || 2} Active)</span></p>
          <p className="text-[11px] text-emerald-400 flex items-center gap-1 mt-1">
            <CheckCircle2 className="w-3 h-3" /> {completionPct.toFixed(1)}% Completed
          </p>
        </div>

        <div className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-1">
          <span className="text-xs text-slate-400">Active Blockers</span>
          <p className="text-2xl font-extrabold text-amber-400">1 <span className="text-xs font-normal text-slate-400">External Dependency</span></p>
          <p className="text-[11px] text-amber-300 mt-1">TPM-105 Slack HMAC HMAC verify</p>
        </div>
      </div>
    </div>
  );
}
