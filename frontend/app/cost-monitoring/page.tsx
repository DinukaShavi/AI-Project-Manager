"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useAuth } from "../../hooks/use-auth";
import { costsApi, CostSummaryResponse, ApiError } from "../../api";
import { DollarSign, ShieldCheck } from "lucide-react";

type LoadState = "loading" | "error" | "ready";

export default function CostMonitoringPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  const [costSummary, setCostSummary] = useState<CostSummaryResponse | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);

  const loadCosts = useCallback(async () => {
    if (!organizationId) return;
    setState("loading");
    setError(null);
    try {
      const res = await costsApi.getCostSummary(organizationId);
      setCostSummary(res);
      setState("ready");
    } catch (e) {
      setCostSummary(null);
      setError(e instanceof ApiError ? e.message : "Failed to load cost data.");
      setState("error");
    }
  }, [organizationId]);

  useEffect(() => {
    loadCosts();
  }, [loadCosts]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="cost_monitoring" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <DollarSign className="w-8 h-8 text-emerald-400" /> AI Infrastructure Cost & LLM Expenditure
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Token consumption tracking and cost breakdown for your organization.
            </p>
          </div>

          {state === "loading" && (
            <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-3">
              <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              Loading cost data...
            </div>
          )}

          {state === "error" && (
            <div className="p-8 rounded-2xl bg-white/5 border border-white/10 text-center space-y-3">
              <p className="text-rose-400 font-semibold">Unable to load cost data.</p>
              <p className="text-xs text-slate-400">{error}</p>
              <button onClick={loadCosts} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-emerald-600/30 hover:bg-emerald-600/40">
                Retry
              </button>
            </div>
          )}

          {state === "ready" && costSummary && (
            <>
              {costSummary.total_calls === 0 ? (
                <div className="p-10 rounded-2xl bg-white/5 border border-white/10 text-center space-y-2">
                  <ShieldCheck className="w-8 h-8 text-emerald-400 mx-auto" />
                  <p className="text-slate-300 font-medium">No LLM usage recorded yet for your organization.</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                      <span className="text-xs text-slate-400">Total Spend</span>
                      <p className="text-3xl font-extrabold text-emerald-400">${costSummary.total_cost_usd.toFixed(4)}</p>
                      <span className="text-xs text-slate-400">{costSummary.total_calls} LLM call(s) recorded</span>
                    </div>

                    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                      <span className="text-xs text-slate-400">Total Prompt Tokens</span>
                      <p className="text-3xl font-extrabold text-white">{costSummary.total_prompt_tokens.toLocaleString()}</p>
                    </div>

                    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
                      <span className="text-xs text-slate-400">Total Completion Tokens</span>
                      <p className="text-3xl font-extrabold text-purple-400">{costSummary.total_completion_tokens.toLocaleString()}</p>
                    </div>
                  </div>

                  {Object.keys(costSummary.cost_by_model).length > 0 && (
                    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-3">
                      <h3 className="text-sm font-bold text-white">Cost by Model</h3>
                      {Object.entries(costSummary.cost_by_model).map(([model, cost]) => (
                        <div key={model} className="flex items-center justify-between text-xs text-slate-300">
                          <span>{model}</span>
                          <span className="font-semibold text-emerald-300">${cost.toFixed(4)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
