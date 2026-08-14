"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useSlackMessages, useSlackUsers, useSlackActivity } from "../../hooks/useSlack";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, slackApi, Project, ApiError } from "../../api";
import { DiscoveredSlackChannel, MappedSlackChannel } from "../../types/slack";
import { Hash, MessageSquare, Users, BarChart3, RefreshCw, Lock, Globe, Search, Link2, ShieldAlert } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function SlackIntegrationPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  const [activeTab, setActiveTab] = useState<"channels" | "messages" | "users" | "activity">("channels");
  const [selectedChannel, setSelectedChannel] = useState<string>("C01ABCDEF01");

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established across this session's other real-data-wiring pages).
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  const [mappedChannels, setMappedChannels] = useState<MappedSlackChannel[]>([]);
  const [loadingMapped, setLoadingMapped] = useState(true);
  const [mappedError, setMappedError] = useState<string | null>(null);

  const [discovered, setDiscovered] = useState<DiscoveredSlackChannel[] | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [mappingChannelId, setMappingChannelId] = useState<string | null>(null);

  // Messages/Users/Activity remain sourced from the documented Slack mock GET endpoints
  // (confirmed hardcoded server-side, ignoring organization_id entirely) -- real message
  // ingestion into centralized project context is separate, larger work this turn doesn't build.
  const { messages, loading: loadingMessages, error: errorMessages, refresh: refreshMessages } = useSlackMessages(DUMMY_ORG_ID, selectedChannel);
  const { users, loading: loadingUsers, error: errorUsers, refresh: refreshUsers } = useSlackUsers(DUMMY_ORG_ID);
  const { activity, loading: loadingActivity, error: errorActivity, refresh: refreshActivity } = useSlackActivity(DUMMY_ORG_ID);

  const loadProjects = useCallback(async () => {
    if (!organizationId) return;
    setProjectsLoading(true);
    try {
      const wsRes = await projectApi.getWorkspaces(organizationId);
      const projectLists = await Promise.all((wsRes.workspaces || []).map((ws) => projectApi.getProjects(ws.workspace_id)));
      const allProjects = projectLists.flatMap((p) => p.projects);
      setProjects(allProjects);
      setSelectedProjectId((prev) => (prev && allProjects.some((p) => p.project_id === prev) ? prev : allProjects[0]?.project_id || null));
    } catch (err) {
      setProjects([]);
      setSelectedProjectId(null);
    } finally {
      setProjectsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const loadMappedChannels = useCallback(async (projectId: string) => {
    setLoadingMapped(true);
    setMappedError(null);
    try {
      const res = await slackApi.getMappedChannels(projectId);
      setMappedChannels(res.channels);
    } catch (err) {
      setMappedError(err instanceof ApiError ? err.message : "Failed to load mapped channels.");
    } finally {
      setLoadingMapped(false);
    }
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadMappedChannels(selectedProjectId);
    } else {
      setMappedChannels([]);
      setLoadingMapped(false);
    }
  }, [selectedProjectId, loadMappedChannels]);

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoverError(null);
    try {
      const res = await slackApi.discoverChannels();
      setDiscovered(res.channels);
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Failed to discover channels.");
    } finally {
      setDiscovering(false);
    }
  };

  const handleMap = async (channel: DiscoveredSlackChannel) => {
    if (!selectedProjectId) return;
    setMappingChannelId(channel.slack_channel_id);
    try {
      await slackApi.mapChannelToProject({ project_id: selectedProjectId, slack_channel_id: channel.slack_channel_id });
      await loadMappedChannels(selectedProjectId);
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Failed to map channel.");
    } finally {
      setMappingChannelId(null);
    }
  };

  const handleRefreshAll = () => {
    if (selectedProjectId) loadMappedChannels(selectedProjectId);
    refreshMessages();
    refreshUsers();
    refreshActivity();
  };

  const mappedChannelIds = new Set(mappedChannels.map((c) => c.slack_channel_id));

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

            <div className="flex items-center gap-3">
              {projects.length > 1 && (
                <select
                  value={selectedProjectId || ""}
                  onChange={(e) => setSelectedProjectId(e.target.value || null)}
                  className="px-3 py-2 rounded-xl text-xs bg-white/5 border border-white/10 text-slate-200"
                >
                  {projects.map((p) => (
                    <option key={p.project_id} value={p.project_id} className="bg-slate-900">
                      {p.name}
                    </option>
                  ))}
                </select>
              )}
              <button
                onClick={handleRefreshAll}
                className="px-4 py-2.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 font-semibold text-sm border border-emerald-500/30 transition-all flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" /> Refresh Slack Stream
              </button>
            </div>
          </div>

          {/* Map a Channel -- real Slack API discovery + real mapping */}
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Link2 className="w-5 h-5 text-emerald-400" /> Map a Channel
              </h2>
              <button
                onClick={handleDiscover}
                disabled={discovering || !selectedProjectId}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-2 disabled:opacity-50"
              >
                {discovering ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />} Discover Channels
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Lists real channels your connected Slack workspace bot can see, and maps one to the selected project so
              incoming messages auto-route to it. Requires Slack to be connected on the Integrations page.
            </p>

            {discoverError && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                <ShieldAlert className="w-3.5 h-3.5 shrink-0" /> {discoverError}
              </div>
            )}

            {discovered && (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {discovered.length === 0 ? (
                  <p className="text-xs text-slate-500">No channels found for the connected workspace.</p>
                ) : (
                  discovered.map((chan) => {
                    const alreadyMapped = mappedChannelIds.has(chan.slack_channel_id);
                    return (
                      <div key={chan.slack_channel_id} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
                        <div>
                          <p className="text-sm text-white flex items-center gap-1.5">
                            <Hash className="w-3.5 h-3.5 text-emerald-400" /> {chan.name}
                          </p>
                          <p className="text-xs text-slate-500">{chan.is_private ? "Private" : "Public"} · {chan.num_members} members</p>
                        </div>
                        <button
                          onClick={() => handleMap(chan)}
                          disabled={alreadyMapped || mappingChannelId === chan.slack_channel_id || !selectedProjectId}
                          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 disabled:opacity-50"
                        >
                          {alreadyMapped ? "Mapped" : mappingChannelId === chan.slack_channel_id ? "Mapping..." : "Map to Project"}
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            )}
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
              <Hash className="w-4 h-4" /> Mapped Channels ({mappedChannels.length})
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
            <div className="space-y-3">
              {loadingMapped ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading mapped channels...</div>
              ) : mappedError ? (
                <div className="p-8 text-center text-rose-300 text-sm">{mappedError}</div>
              ) : !selectedProjectId ? (
                <div className="p-8 text-center text-slate-400 text-sm">Select a project above to view its mapped channels.</div>
              ) : mappedChannels.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  No channels mapped to this project yet. Use "Discover Channels" above to map one.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {mappedChannels.map((chan) => (
                    <div key={chan.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <Hash className="w-4 h-4" />
                      </div>
                      <p className="text-sm font-bold text-white font-mono">{chan.slack_channel_id}</p>
                    </div>
                  ))}
                </div>
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
