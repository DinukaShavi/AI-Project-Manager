"use client";

import React, { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { auditLogApi, ApiError } from "../../api";
import { AuditLogEntry } from "../../api/types";
import { ClipboardList, RefreshCw, ShieldAlert, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 25;

export default function AuditLogsPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionFilter, setActionFilter] = useState("");
  const [emailFilter, setEmailFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const fetchLogs = async (nextOffset = offset) => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditLogApi.listAuditLogs({
        limit: PAGE_SIZE,
        offset: nextOffset,
        action: actionFilter || undefined,
        user_email: emailFilter || undefined,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
      });
      setEntries(res.entries);
      setTotal(res.total);
      setOffset(nextOffset);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load audit log.";
      setError(message);
      setEntries([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchLogs(0);
  };

  const handleExport = () => {
    const rows = entries.map((e) => ({
      timestamp: e.timestamp,
      user: e.user_email || e.user_id || "system",
      action: e.action,
      ip_address: e.ip_address || "",
      details: JSON.stringify(e.details),
    }));
    const header = "timestamp,user,action,ip_address,details\n";
    const csv = rows
      .map((r) => [r.timestamp, r.user, r.action, r.ip_address, JSON.stringify(r.details)].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([header + csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-log-export-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-amber-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="audit_logs" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <ClipboardList className="w-8 h-8 text-amber-400" /> Audit Logs Viewer
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Read-only, append-only security event trail for this organization (OrgAdmin / SuperAdmin only).
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleExport}
                disabled={entries.length === 0}
                className="px-4 py-2.5 rounded-xl bg-slate-800/60 hover:bg-slate-800 text-slate-200 text-sm font-semibold border border-slate-700 disabled:opacity-50"
              >
                Export CSV
              </button>
              <button
                onClick={() => fetchLogs(offset)}
                className="px-4 py-2.5 rounded-xl bg-amber-600/20 text-amber-300 text-sm font-semibold border border-amber-500/30 flex items-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh
              </button>
            </div>
          </div>

          <form onSubmit={handleFilterSubmit} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl grid grid-cols-1 md:grid-cols-5 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">Action</label>
              <input
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                placeholder="tool:execute"
                className="w-full px-3 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">User email</label>
              <input
                value={emailFilter}
                onChange={(e) => setEmailFilter(e.target.value)}
                placeholder="user@example.com"
                className="w-full px-3 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">Start date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">End date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="flex items-end">
              <button type="submit" className="w-full py-2 rounded-lg gradient-btn text-white text-sm font-semibold">
                Apply Filters
              </button>
            </div>
          </form>

          {error && (
            <div role="alert" className="flex items-center gap-2 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-xs text-slate-400 uppercase tracking-wider">
                    <th className="px-4 py-3">Timestamp</th>
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">IP Address</th>
                    <th className="px-4 py-3">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.length === 0 && !loading && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                        No audit log entries match the current filters.
                      </td>
                    </tr>
                  )}
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b border-slate-800/60 hover:bg-slate-900/40">
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap font-mono text-xs">
                        {new Date(entry.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-slate-200">{entry.user_email || entry.user_id || "system"}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono">
                          {entry.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 font-mono text-xs">{entry.ip_address || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 font-mono text-xs max-w-md truncate" title={JSON.stringify(entry.details)}>
                        {JSON.stringify(entry.details)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800 text-xs text-slate-400">
              <span>
                Showing {entries.length === 0 ? 0 : offset + 1}–{offset + entries.length} of {total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchLogs(Math.max(0, offset - PAGE_SIZE))}
                  disabled={!canPrev || loading}
                  className="p-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 disabled:opacity-40"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => fetchLogs(offset + PAGE_SIZE)}
                  disabled={!canNext || loading}
                  className="p-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 disabled:opacity-40"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
