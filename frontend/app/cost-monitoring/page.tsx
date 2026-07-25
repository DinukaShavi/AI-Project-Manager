"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { costsApi } from "../../api";
import { DollarSign, ShieldCheck, TrendingUp } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function CostMonitoringPage() {
  const [costSummary, setCostSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchCosts() {
      setLoading(true);
      try {
        const res = await costsApi.getCostSummary(DUMMY_ORG_ID);
        setCostSummary(res);
      } catch (e) {
        // Fallback
      } finally {
        setLoading(false);
      }
    }
    fetchCosts();
  }, []);

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
              Token consumption tracking, monthly spend limits, and cost optimization alerts.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
              <span className="text-xs text-slate-400">Total Monthly Spend</span>
              <p className="text-3xl font-extrabold text-emerald-400">$42.18</p>
              <span className="text-xs text-emerald-300">Under $100.00 Monthly Limit</span>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
              <span className="text-xs text-slate-400">Total Input Tokens</span>
              <p className="text-3xl font-extrabold text-white">1,420,500</p>
            </div>

            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-2">
              <span className="text-xs text-slate-400">Total Output Tokens</span>
              <p className="text-3xl font-extrabold text-purple-400">385,200</p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
