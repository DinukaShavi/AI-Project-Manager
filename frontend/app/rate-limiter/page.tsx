"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { rateLimiterApi } from "../../api";
import { Zap, ShieldCheck, AlertTriangle, RefreshCw } from "lucide-react";

export default function RateLimiterPage() {
  const [dimension, setDimension] = useState("llm_call");
  const [identifier, setIdentifier] = useState("tenant-acme-corp");
  const [tokens, setTokens] = useState(1.0);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleCheckLimit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      const res = await rateLimiterApi.checkRateLimit(dimension, identifier, tokens);
      setResult(res);
    } catch (err: any) {
      setResult({ error: err.message || "Rate limit check failed" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-amber-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="rate_limiter" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Zap className="w-8 h-8 text-amber-400" /> Multi-Dimensional Rate Limiting Engine
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Token Bucket algorithm for LLM calls, vector search queries, and HTTP REST endpoints.
            </p>
          </div>

          <form onSubmit={handleCheckLimit} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Dimension Category</label>
                <select
                  value={dimension}
                  onChange={(e) => setDimension(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="llm_call">LLM Call (Burst Limit: 30)</option>
                  <option value="vector_search">Vector Search (Burst Limit: 100)</option>
                  <option value="http_api">HTTP API (Burst Limit: 200)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Tenant Identifier</label>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Tokens Requested</label>
                <input
                  type="number"
                  step="0.1"
                  value={tokens}
                  onChange={(e) => setTokens(parseFloat(e.target.value))}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />} Consume Token Bucket
            </button>
          </form>

          {result && (
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
              <h3 className="text-lg font-bold text-white">Token Bucket Consumption Status</h3>
              <pre className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono text-amber-300 overflow-x-auto">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
