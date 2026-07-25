"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import Link from "next/link";
import { Github, Ticket, MessageSquare, Calendar, CheckCircle2, ArrowRight, ShieldCheck, RefreshCw } from "lucide-react";

export default function IntegrationsOverviewPage() {
  const integrations = [
    {
      id: "github",
      name: "GitHub",
      category: "Version Control & CI/CD",
      description: "Pull request monitoring, commit log activity, and webhook HMAC signature verification.",
      connected: true,
      href: "/github",
      icon: Github,
      gradient: "from-purple-600 to-indigo-600",
    },
    {
      id: "jira",
      name: "Jira Software",
      category: "Issue Tracking & Agile Sprints",
      description: "Sprint backlog synchronization, team story points workload distribution, and historical velocity.",
      connected: true,
      href: "/jira",
      icon: Ticket,
      gradient: "from-blue-600 to-cyan-600",
    },
    {
      id: "slack",
      name: "Slack Events API",
      category: "Team Messaging & Bot Alerts",
      description: "Real-time channel message ingestion, discussion sentiment scoring, and automated AI risk alerts.",
      connected: true,
      href: "/slack",
      icon: MessageSquare,
      gradient: "from-emerald-600 to-teal-600",
    },
    {
      id: "calendar",
      name: "Google Calendar & Meet",
      category: "Calendar Scheduling & Video Sync",
      description: "Automated daily standup scheduling, team availability slot matrix, and Google Meet integration.",
      connected: true,
      href: "/calendar",
      icon: Calendar,
      gradient: "from-amber-600 to-orange-600",
    },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-purple-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="integrations" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
              Platform Integration Connection Portal
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Manage multi-platform OAuth credentials, webhook endpoints, and outbox event streams.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {integrations.map((item) => {
              const IconComponent = item.icon;
              return (
                <div
                  key={item.id}
                  className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl hover:border-purple-500/40 transition-all flex flex-col justify-between space-y-4 shadow-xl"
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${item.gradient} flex items-center justify-center text-white shadow-lg`}>
                        <IconComponent className="w-6 h-6" />
                      </div>
                      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{item.category}</span>
                      <h3 className="text-xl font-bold text-white mt-0.5">{item.name}</h3>
                      <p className="text-xs text-slate-400 mt-1">{item.description}</p>
                    </div>
                  </div>

                  <Link
                    href={item.href}
                    className="w-full py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white font-semibold text-xs border border-white/10 transition-all flex items-center justify-center gap-2"
                  >
                    <span>Manage {item.name} Integration</span>
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}
