"use client";

import React from "react";

import Link from "next/link";

interface SidebarProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  setActiveTab?: (tab: string) => void;
}

export default function Sidebar({ activeTab, onTabChange, setActiveTab }: SidebarProps) {
  const changeTab = (tabId: string) => {
    if (onTabChange) onTabChange(tabId);
    if (setActiveTab) setActiveTab(tabId);
  };

  const navItems = [
    { id: "overview", label: "Executive Overview", path: "/", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" },
    { id: "agent_dashboard", label: "AI PM Dashboard", path: "/agent-dashboard", icon: "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" },
    { id: "tasks", label: "Sprint Kanban Board", path: "/", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 022 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" },
    { id: "github", label: "GitHub Integration", path: "/github", icon: "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" },
    { id: "jira", label: "Jira Integration", path: "/jira", icon: "M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7" },
    { id: "slack", label: "Slack Events", path: "/slack", icon: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" },
    { id: "calendar", label: "Google Calendar", path: "/calendar", icon: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" },
    { id: "workflows", label: "Multi-Agent Workflows", path: "/", icon: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" },
    { id: "context", label: "Context Vector Search", path: "/", icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" },
  ];

  return (
    <aside className="w-64 glass-panel border-r border-slate-800/80 min-h-[calc(100vh-65px)] p-4 flex flex-col justify-between">
      <div className="space-y-6">
        <div>
          <p className="text-[10px] font-bold tracking-wider text-slate-500 uppercase px-3 mb-3">
            Management Console
          </p>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              if (item.path !== "/" && item.path) {
                return (
                  <Link
                    key={item.id}
                    href={item.path}
                    className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 ${
                      isActive
                        ? "bg-purple-600/20 text-purple-300 border border-purple-500/30 shadow-md shadow-purple-500/10"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                    }`}
                  >
                    <svg className={`w-4 h-4 ${isActive ? "text-purple-400" : "text-slate-500"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={item.icon} />
                    </svg>
                    <span>{item.label}</span>
                  </Link>
                );
              }
              return (
                <button
                  key={item.id}
                  onClick={() => changeTab(item.id)}
                  className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-md shadow-indigo-500/10"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                  }`}
                >
                  <svg className={`w-4 h-4 ${isActive ? "text-indigo-400" : "text-slate-500"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={item.icon} />
                  </svg>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800 text-xs text-slate-400 space-y-1">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-semibold text-slate-300">Active Tenant</span>
          <span className="text-indigo-400">Acme Corp</span>
        </div>
        <p className="text-[10px] text-slate-500">PostgreSQL Vector DB Active</p>
      </div>
    </aside>
  );
}
