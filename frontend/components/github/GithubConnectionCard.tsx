"use client";

import React, { useEffect, useState } from "react";
import { githubApi } from "../../api/github.api";
import { integrationStatusApi } from "../../api/integrationStatus.api";
import { useIntegrationStatusSocket } from "../../hooks/useIntegrationStatusSocket";
import { IntegrationConnectionStatus } from "../../types/integrationStatus";
import { Github, CheckCircle2, ShieldCheck, RefreshCw, Unlink, AlertTriangle } from "lucide-react";

interface Props {
  orgId: string;
  onRefreshAll?: () => void;
}

export default function GithubConnectionCard({ orgId, onRefreshAll }: Props) {
  const [status, setStatus] = useState<IntegrationConnectionStatus>("disconnected");
  const [statusLoading, setStatusLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // Live connection-status updates over the authenticated WebSocket
  // (implementation_roadmap.md Milestone 6: "connection dashboard updates in real-time").
  const { statusUpdates, socketState } = useIntegrationStatusSocket();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await integrationStatusApi.getStatuses();
        const github = res.integrations.find((i) => i.provider === "github");
        if (!cancelled && github) {
          setStatus(github.status);
        }
      } catch (err) {
        console.error("Failed to load integration status:", err);
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // A live update for GitHub always supersedes the initially-fetched status.
  useEffect(() => {
    const liveUpdate = statusUpdates["github"];
    if (liveUpdate) {
      setStatus(liveUpdate.status);
    }
  }, [statusUpdates]);

  const isConnected = status === "connected";
  const needsReauth = status === "reauth_required";

  const handleConnect = async () => {
    setActionLoading(true);
    try {
      const res = await githubApi.getAuthorizeUrl(orgId);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (err) {
      console.error("OAuth error:", err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisconnect = async () => {
    setActionLoading(true);
    try {
      await githubApi.revokeConnection(orgId);
      setStatus("disconnected");
    } catch (err) {
      console.error("Revoke error:", err);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl shadow-2xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-purple-500/20">
          <Github className="w-6 h-6" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-white">GitHub Integration Portal</h2>
            {statusLoading ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-700/30 text-slate-400 border border-slate-600/30">
                Loading...
              </span>
            ) : isConnected ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5" /> Connected
              </span>
            ) : needsReauth ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <AlertTriangle className="w-3.5 h-3.5" /> Needs Reauthorization
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                Disconnected
              </span>
            )}
            <span
              title={`Live updates: ${socketState}`}
              className={`w-2 h-2 rounded-full ${socketState === "open" ? "bg-emerald-400" : "bg-slate-600"}`}
            />
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Real-time webhook sync for PRs, Commits, and Issues with HMAC SHA-256 validation.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 w-full md:w-auto">
        {onRefreshAll && (
          <button
            onClick={onRefreshAll}
            className="flex-1 md:flex-none px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-200 text-sm font-medium border border-white/10 transition-all flex items-center justify-center gap-2"
          >
            <RefreshCw className="w-4 h-4" /> Refresh Sync
          </button>
        )}

        {isConnected ? (
          <button
            onClick={handleDisconnect}
            disabled={actionLoading}
            className="flex-1 md:flex-none px-4 py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-sm font-medium border border-rose-500/20 transition-all flex items-center justify-center gap-2"
          >
            <Unlink className="w-4 h-4" /> Disconnect
          </button>
        ) : (
          <button
            onClick={handleConnect}
            disabled={actionLoading}
            className="flex-1 md:flex-none px-4 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-sm font-medium shadow-lg shadow-purple-500/20 transition-all flex items-center justify-center gap-2"
          >
            <ShieldCheck className="w-4 h-4" /> {needsReauth ? "Reconnect GitHub" : "Connect GitHub"}
          </button>
        )}
      </div>
    </div>
  );
}
