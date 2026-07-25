"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useSlackChannels, useSlackMessages, useSlackUsers, useSlackActivity } from "../../hooks/useSlack";
import { Hash, MessageSquare, Users, BarChart3, RefreshCw, Lock, Globe, Bot } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function SlackIntegrationPage() {
  const [activeTab, setActiveTab] = useState<"channels" | "messages" | "users" | "activity">("channels");
  const [selectedChannel, setSelectedChannel] = useState<string>("C01ABCDEF01");

  const { channels, loading: loadingChannels, error: errorChannels, refresh: refreshChannels } = useSlackChannels(DUMMY_ORG_ID);
  const { messages, loading: loadingMessages, error: errorMessages, refresh: refreshMessages } = useSlackMessages(DUMMY_ORG_ID, selectedChannel);
  const { users, loading: loadingUsers, error: errorUsers, refresh: refreshUsers } = useSlackUsers(DUMMY_ORG_ID);
  const { activity, loading: loadingActivity, error: errorActivity, refresh: refreshActivity } = useSlackActivity(DUMMY_ORG_ID);

  const handleRefreshAll = () => {
    refreshChannels();
    refreshMessages();
    refreshUsers();
    refreshActivity();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="slack" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          {/* Header Title */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                Slack Events API Integration
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Real-time channel message ingestion, team activity sentiment analysis, and bot notifications.
              </p>
            </div>

            <button
              onClick={handleRefreshAll}
              className="px-4 py-2.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 font-semibold text-sm border border-emerald-500/30 transition-all flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" /> Refresh Slack Stream
            </button>
          </div>

          {/* Sub-Navigation Tabs */}
          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-x-auto">
            <button
              onClick={() => setActiveTab("channels")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "channels"
                  ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Hash className="w-4 h-4" /> Channels ({channels.length})
            </button>

            <button
              onClick={() => setActiveTab("messages")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "messages"
                  ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <MessageSquare className="w-4 h-4" /> Live Messages ({messages.length})
            </button>

            <button
              onClick={() => setActiveTab("users")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "users"
                  ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Users className="w-4 h-4" /> Workspace Members ({users.length})
            </button>

            <button
              onClick={() => setActiveTab("activity")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "activity"
                  ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-emerald-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <BarChart3 className="w-4 h-4" /> Activity Analytics
            </button>
          </div>

          {/* Tab Views */}
          {activeTab === "channels" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {loadingChannels ? (
                <div className="p-8 text-center text-slate-400 font-medium col-span-2">Loading Slack Channels...</div>
              ) : (
                channels.map((chan) => (
                  <div key={chan.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <Hash className="w-4 h-4 text-emerald-400" />
                        <h4 className="text-base font-bold text-white">{chan.name}</h4>
                        {chan.is_private ? (
                          <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 flex items-center gap-1"><Lock className="w-2.5 h-2.5" /> Private</span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-400 flex items-center gap-1"><Globe className="w-2.5 h-2.5" /> Public</span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{chan.topic}</p>
                    </div>
                    <span className="text-xs font-semibold text-slate-400">{chan.members_count} members</span>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "messages" && (
            <div className="space-y-3">
              {loadingMessages ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading Messages...</div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.ts} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-start gap-3">
                    <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
                      <MessageSquare className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <strong className="text-sm text-white">{msg.user_name}</strong>
                        <span className="text-[10px] text-slate-500">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1">{msg.text}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "users" && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {users.map((usr) => (
                <div key={usr.id} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center font-bold text-white">
                    {usr.real_name.charAt(0)}
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white">{usr.real_name}</h4>
                    <p className="text-xs text-slate-400">{usr.role}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "activity" && activity && (
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-white/5 text-center">
                  <p className="text-xs text-slate-400">Daily Volume</p>
                  <p className="text-2xl font-extrabold text-white mt-1">{activity.daily_message_volume} msg</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 text-center">
                  <p className="text-xs text-slate-400">Sentiment Score</p>
                  <p className="text-2xl font-extrabold text-emerald-400 mt-1">{activity.sentiment_score * 100}% Positive</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 text-center">
                  <p className="text-xs text-slate-400">Top Topics</p>
                  <p className="text-xs font-semibold text-white mt-2">{activity.top_discussed_topics.join(" • ")}</p>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
