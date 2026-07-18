"use client";

import React from "react";

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onOpenAgentModal: () => void;
}

export default function Navbar({ activeTab, setActiveTab, onOpenAgentModal }: NavbarProps) {
  return (
    <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 px-6 py-3.5 flex items-center justify-between">
      {/* Brand Identity */}
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center">
          <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
            <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
            AI-TPM <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium">v1.0 Enterprise</span>
          </h1>
          <p className="text-xs text-slate-400">Technical Project Management Kernel</p>
        </div>
      </div>

      {/* System Status & Action Button */}
      <div className="flex items-center space-x-4">
        {/* Live Backend Pulse Badge */}
        <div className="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-slate-800 text-xs text-slate-300">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span>FastAPI Engine Operational</span>
        </div>

        {/* AI Action Trigger Button */}
        <button
          onClick={onOpenAgentModal}
          className="gradient-btn px-4 py-2 rounded-xl text-xs font-semibold text-white flex items-center space-x-2 shadow-lg"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <span>Trigger AI Agent</span>
        </button>

        {/* User Profile Badge */}
        <div className="w-9 h-9 rounded-full bg-indigo-950 border border-indigo-500/30 flex items-center justify-center text-xs font-bold text-indigo-300">
          AP
        </div>
      </div>
    </header>
  );
}
