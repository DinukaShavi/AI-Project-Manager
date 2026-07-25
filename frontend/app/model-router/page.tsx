"use client";

import React, { useState, useEffect } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { modelRouterApi } from "../../api";
import { Cpu, RefreshCw, CheckCircle2 } from "lucide-react";

export default function ModelRouterPage() {
  const [matrix, setMatrix] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchMatrix() {
      setLoading(true);
      try {
        const res = await modelRouterApi.getModelMatrix();
        setMatrix(res);
      } catch (e) {
        // Fallback
      } finally {
        setLoading(false);
      }
    }
    fetchMatrix();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="model_router" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Cpu className="w-8 h-8 text-purple-400" /> Dynamic Model Router & Tiered Matrix
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Dynamic model selection matrix balancing reasoning quality, token budget, and payload length.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
            <h3 className="text-lg font-bold text-white">Active LLM Routing Matrix</h3>
            <pre className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono text-purple-300 overflow-x-auto">
              {JSON.stringify(matrix || {
                available_tiers: ["standard", "economy", "premium"],
                supported_models: ["gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet"],
              }, null, 2)}
            </pre>
          </div>
        </main>
      </div>
    </div>
  );
}
