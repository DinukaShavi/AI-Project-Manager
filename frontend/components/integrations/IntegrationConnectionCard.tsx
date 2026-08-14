"use client";

import React, { useState } from "react";
import Link from "next/link";
import { LucideIcon, CheckCircle2, ShieldCheck, Unlink, AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { integrationOAuthApi } from "../../api/integrationOAuth.api";
import { IntegrationConnectionStatus } from "../../types/integrationStatus";

interface Props {
  provider: string;
  name: string;
  category: string;
  description: string;
  icon: LucideIcon;
  gradient: string;
  manageHref?: string;
  status: IntegrationConnectionStatus | undefined;
  statusLoading: boolean;
  /** Providers without a real per-organization OAuth flow in this deployment (e.g. Jira,
   * which authenticates via a single deployment-wide static API token) render status only
   * -- no Connect/Disconnect controls that would imply a per-tenant action this system
   * doesn't actually support. */
  oauthSupported?: boolean;
  onStatusChange?: (status: IntegrationConnectionStatus) => void;
}

export default function IntegrationConnectionCard({
  provider,
  name,
  category,
  description,
  icon: Icon,
  gradient,
  manageHref,
  status,
  statusLoading,
  oauthSupported = true,
  onStatusChange,
}: Props) {
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const isConnected = status === "connected";
  const needsReauth = status === "reauth_required";

  const handleConnect = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await integrationOAuthApi.getAuthorizeUrl(provider);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (err: any) {
      setActionError(err.message || "Failed to start the authorization flow.");
      setActionLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm(`Disconnect ${name}? Existing syncs for this provider will stop until it's reconnected.`)) {
      return;
    }
    setActionLoading(true);
    setActionError(null);
    try {
      await integrationOAuthApi.revokeConnection(provider);
      onStatusChange?.("disconnected");
    } catch (err: any) {
      setActionError(err.message || "Failed to disconnect.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl hover:border-purple-500/40 transition-all flex flex-col justify-between space-y-4 shadow-xl">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center text-white shadow-lg`}>
            <Icon className="w-6 h-6" />
          </div>

          {statusLoading ? (
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-slate-700/30 text-slate-400 border border-slate-600/30">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Checking...
            </span>
          ) : isConnected ? (
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" /> Connected
            </span>
          ) : needsReauth ? (
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <AlertTriangle className="w-3.5 h-3.5" /> Reauthorize
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
              Disconnected
            </span>
          )}
        </div>

        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{category}</span>
          <h3 className="text-xl font-bold text-white mt-0.5">{name}</h3>
          <p className="text-xs text-slate-400 mt-1">{description}</p>
        </div>

        {!oauthSupported && (
          <p className="text-[11px] text-slate-500 italic">
            Configured via deployment-level credentials, not a per-organization OAuth connection.
          </p>
        )}

        {actionError && (
          <div role="alert" className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
            {actionError}
          </div>
        )}
      </div>

      <div className="space-y-2">
        {oauthSupported && (
          isConnected ? (
            <button
              onClick={handleDisconnect}
              disabled={actionLoading || statusLoading}
              className="w-full py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-sm font-medium border border-rose-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Unlink className="w-4 h-4" />} Disconnect
            </button>
          ) : (
            <button
              onClick={handleConnect}
              disabled={actionLoading || statusLoading}
              className={`w-full py-2.5 rounded-xl bg-gradient-to-r ${gradient} hover:opacity-90 text-white text-sm font-medium shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-60`}
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
              {needsReauth ? `Reauthorize ${name}` : `Connect ${name}`}
            </button>
          )
        )}

        {manageHref && (
          <Link
            href={manageHref}
            className="w-full py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white font-semibold text-xs border border-white/10 transition-all flex items-center justify-center gap-2"
          >
            <span>Manage {name} Integration</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        )}
      </div>
    </div>
  );
}
