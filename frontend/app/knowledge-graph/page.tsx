"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { graphApi } from "../../api";
import { Network, RefreshCw, CheckCircle2 } from "lucide-react";

export default function KnowledgeGraphPage() {
  const [startNode, setStartNode] = useState("node-task-101");
  const [minWeight, setMinWeight] = useState(0.10);
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleTraverse = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setGraphData(null);
    try {
      const res = await graphApi.traverseGraph(startNode, minWeight);
      setGraphData(res);
    } catch (err: any) {
      setGraphData({ error: err.message || "Traversal failed" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="knowledge_graph" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              <Network className="w-8 h-8 text-purple-400" /> Knowledge Graph Weight Decay & Traverser
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              $Weight = BaseWeight \times (1 - DecayFactor \times AgeDays)$ relationship link decay calculation.
            </p>
          </div>

          <form onSubmit={handleTraverse} className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Start Node ID</label>
                <input
                  type="text"
                  value={startNode}
                  onChange={(e) => setStartNode(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-purple-500 font-mono"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Minimum Edge Weight Threshold</label>
                <input
                  type="number"
                  step="0.05"
                  value={minWeight}
                  onChange={(e) => setMinWeight(parseFloat(e.target.value))}
                  className="w-full px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-purple-500"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-purple-500/20 transition-all flex items-center justify-center gap-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Network className="w-4 h-4" />} Traverse Graph & Prune Expired Edges
            </button>
          </form>

          {graphData && (
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-purple-400" /> Knowledge Graph Traversal Result
              </h3>
              <pre className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-mono text-purple-300 overflow-x-auto">
                {JSON.stringify(graphData, null, 2)}
              </pre>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
