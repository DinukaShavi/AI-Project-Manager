"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { contextApi } from "../../api";
import { Search, Database, Cpu, ArrowRight, RefreshCw, CheckCircle2 } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function ContextSearchPage() {
  const [query, setQuery] = useState("OpenTelemetry distributed tracing and Redis rate limiter");
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResults(null);
    try {
      const res = await contextApi.searchContext({
        organization_id: DUMMY_ORG_ID,
        query: query,
        query_text: query,
        top_k: 5,
      });
      setResults(res);
    } catch (err: any) {
      setResults({ error: err.message || "Search failed" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="context" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Database className="w-8 h-8 text-cyan-400" /> Context Vector Search & Memory Retrieval
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Query PostgreSQL pgvector HNSW embedding index across project documentation and codebases.
            </p>
          </div>

          <form onSubmit={handleSearch} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search semantic context vectors..."
                className="w-full px-4 py-3.5 pl-11 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-cyan-500"
                required
              />
              <Search className="w-5 h-5 text-slate-400 absolute left-3.5 top-3.5" />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-cyan-500/20 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Execute HNSW Cosine Similarity Vector Search
            </button>
          </form>

          {results && (
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-cyan-400" /> Vector Matches Returned
              </h3>
              <pre className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono text-cyan-300 overflow-x-auto">
                {JSON.stringify(results, null, 2)}
              </pre>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
