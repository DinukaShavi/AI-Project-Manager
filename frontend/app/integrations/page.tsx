"use client";

import React, { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import IntegrationConnectionCard from "../../components/integrations/IntegrationConnectionCard";
import { integrationStatusApi } from "../../api/integrationStatus.api";
import { useIntegrationStatusSocket } from "../../hooks/useIntegrationStatusSocket";
import { IntegrationConnectionStatus } from "../../types/integrationStatus";
import { Github, Ticket, MessageSquare, Calendar, Wifi, WifiOff } from "lucide-react";

const PROVIDERS: Array<{
  id: string;
  name: string;
  category: string;
  description: string;
  href: string;
  icon: typeof Github;
  gradient: string;
  oauthSupported: boolean;
}> = [
  {
    id: "github",
    name: "GitHub",
    category: "Version Control & CI/CD",
    description: "Pull request monitoring, commit log activity, and webhook HMAC signature verification.",
    href: "/github",
    icon: Github,
    gradient: "from-purple-600 to-indigo-600",
    oauthSupported: true,
  },
  {
    id: "jira",
    name: "Jira Software",
    category: "Issue Tracking & Agile Sprints",
    description: "Sprint backlog synchronization, team story points workload distribution, and historical velocity.",
    href: "/jira",
    icon: Ticket,
    gradient: "from-blue-600 to-cyan-600",
    oauthSupported: false,
  },
  {
    id: "slack",
    name: "Slack Events API",
    category: "Team Messaging & Bot Alerts",
    description: "Real-time channel message ingestion, discussion sentiment scoring, and automated AI risk alerts.",
    href: "/slack",
    icon: MessageSquare,
    gradient: "from-emerald-600 to-teal-600",
    oauthSupported: true,
  },
  {
    id: "google_calendar",
    name: "Google Calendar & Meet",
    category: "Calendar Scheduling & Video Sync",
    description: "Automated daily standup scheduling, team availability slot matrix, and Google Meet integration.",
    href: "/calendar",
    icon: Calendar,
    gradient: "from-amber-600 to-orange-600",
    oauthSupported: true,
  },
];

export default function IntegrationsOverviewPage() {
  const [statuses, setStatuses] = useState<Record<string, IntegrationConnectionStatus>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Real-time updates, per implementation_roadmap.md Milestone 6: "connection dashboard
  // updates in real-time" -- one shared WebSocket for the whole page, not one per card.
  const { statusUpdates, socketState } = useIntegrationStatusSocket();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await integrationStatusApi.getStatuses();
        if (!cancelled) {
          const initial: Record<string, IntegrationConnectionStatus> = {};
          for (const item of res.integrations) {
            initial[item.provider] = item.status;
          }
          setStatuses(initial);
        }
      } catch (err: any) {
        if (!cancelled) setLoadError(err.message || "Failed to load integration connection status.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Live status events always supersede the initially-fetched snapshot.
  useEffect(() => {
    if (Object.keys(statusUpdates).length === 0) return;
    setStatuses((prev) => {
      const next = { ...prev };
      for (const [provider, update] of Object.entries(statusUpdates)) {
        next[provider] = update.status;
      }
      return next;
    });
  }, [statusUpdates]);

  const handleStatusChange = (provider: string, status: IntegrationConnectionStatus) => {
    setStatuses((prev) => ({ ...prev, [provider]: status }));
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="integrations" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                Platform Integration Connection Portal
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Manage multi-platform OAuth credentials, webhook endpoints, and outbox event streams.
              </p>
            </div>
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${
                socketState === "open"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-slate-700/30 text-slate-400 border-slate-600/30"
              }`}
              title={`Live status connection: ${socketState}`}
            >
              {socketState === "open" ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {socketState === "open" ? "Live" : "Reconnecting..."}
            </span>
          </div>

          {loadError && (
            <div role="alert" className="px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              {loadError}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {PROVIDERS.map((item) => (
              <IntegrationConnectionCard
                key={item.id}
                provider={item.id}
                name={item.name}
                category={item.category}
                description={item.description}
                icon={item.icon}
                gradient={item.gradient}
                manageHref={item.href}
                status={statuses[item.id]}
                statusLoading={loading}
                oauthSupported={item.oauthSupported}
                onStatusChange={(status) => handleStatusChange(item.id, status)}
              />
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
