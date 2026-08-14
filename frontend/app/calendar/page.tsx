"use client";

import React, { useCallback, useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useCalendarMeetings, useCalendarAvailability } from "../../hooks/useCalendar";
import { useAuth } from "../../hooks/use-auth";
import { projectApi, calendarApi, Project, ApiError } from "../../api";
import { SyncedMeeting } from "../../types/calendar";
import { Calendar, Video, Clock, Users, ExternalLink, RefreshCw, AlertCircle, CalendarPlus } from "lucide-react";

export default function CalendarIntegrationPage() {
  const { user } = useAuth();
  const organizationId = user?.organization_id;

  const [activeTab, setActiveTab] = useState<"events" | "meetings" | "availability">("events");

  // Real tenant/project context -- never a hardcoded id (matches the pattern already
  // established in frontend/app/workflows/page.tsx). GET /integrations/calendar/meetings and
  // POST /integrations/calendar/sync both require a real project_id.
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectsLoading, setProjectsLoading] = useState(true);

  const [syncedMeetings, setSyncedMeetings] = useState<SyncedMeeting[]>([]);
  const [loadingSyncedMeetings, setLoadingSyncedMeetings] = useState(true);
  const [syncedMeetingsError, setSyncedMeetingsError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [meetingTitle, setMeetingTitle] = useState("");
  const [meetingStart, setMeetingStart] = useState("");
  const [meetingEnd, setMeetingEnd] = useState("");
  const [meetingAttendees, setMeetingAttendees] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  // "Google Meet Links" and "Team Availability Slots" remain backed by the documented demo
  // endpoints -- unlike synced calendar events, no real backend model exists yet for either
  // Meet call links or an availability matrix, so these two tabs are left untouched.
  const { meetings, loading: loadingMeetings, refresh: refreshMeetings } = useCalendarMeetings(organizationId || "");
  const { slots, loading: loadingSlots, refresh: refreshSlots } = useCalendarAvailability(organizationId || "");

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

  const loadSyncedMeetings = useCallback(async (projectId: string) => {
    setLoadingSyncedMeetings(true);
    setSyncedMeetingsError(null);
    try {
      const res = await calendarApi.getSyncedMeetings(projectId);
      setSyncedMeetings(res.meetings);
    } catch (err) {
      setSyncedMeetingsError(err instanceof ApiError ? err.message : "Failed to load synced calendar meetings.");
    } finally {
      setLoadingSyncedMeetings(false);
    }
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadSyncedMeetings(selectedProjectId);
    } else {
      setSyncedMeetings([]);
      setLoadingSyncedMeetings(false);
    }
  }, [selectedProjectId, loadSyncedMeetings]);

  const handleRefreshAll = async () => {
    if (selectedProjectId) {
      setSyncing(true);
      setSyncError(null);
      try {
        const now = new Date();
        const startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        const endDate = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        await calendarApi.syncEvents({
          project_id: selectedProjectId,
          start_date: startDate.toISOString(),
          end_date: endDate.toISOString(),
        });
        await loadSyncedMeetings(selectedProjectId);
      } catch (err) {
        setSyncError(err instanceof ApiError ? err.message : "Calendar sync failed.");
      } finally {
        setSyncing(false);
      }
    }
    refreshMeetings();
    refreshSlots();
  };

  const handleScheduleMeeting = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId) return;
    setScheduling(true);
    setScheduleError(null);
    try {
      const attendee_emails = meetingAttendees
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await calendarApi.createEvent({
        project_id: selectedProjectId,
        title: meetingTitle,
        start_time: new Date(meetingStart).toISOString(),
        end_time: new Date(meetingEnd).toISOString(),
        attendee_emails: attendee_emails.length > 0 ? attendee_emails : undefined,
      });
      setMeetingTitle("");
      setMeetingStart("");
      setMeetingEnd("");
      setMeetingAttendees("");
      setShowScheduleForm(false);
      await loadSyncedMeetings(selectedProjectId);
    } catch (err) {
      setScheduleError(err instanceof ApiError ? err.message : "Failed to schedule meeting.");
    } finally {
      setScheduling(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-amber-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="calendar" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          {/* Header Title */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                Google Calendar & Meet Integration
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Automated standup scheduling, team availability matrix, and Google Meet integration.
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
                disabled={syncing}
                className="px-4 py-2.5 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 font-semibold text-sm border border-amber-500/30 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${syncing ? "animate-spin" : ""}`} /> Refresh Calendar Sync
              </button>
            </div>
          </div>

          {!projectsLoading && projects.length === 0 && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" /> No projects in this organization yet -- create one from the Projects page before syncing calendar events.
            </div>
          )}

          {syncError && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" /> {syncError}
            </div>
          )}

          {/* Sub-Navigation Tabs */}
          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-x-auto">
            <button
              onClick={() => setActiveTab("events")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "events"
                  ? "bg-gradient-to-r from-amber-600 to-orange-600 text-white shadow-lg shadow-amber-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Calendar className="w-4 h-4" /> Synced Calendar Events ({syncedMeetings.length})
            </button>

            <button
              onClick={() => setActiveTab("meetings")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "meetings"
                  ? "bg-gradient-to-r from-amber-600 to-orange-600 text-white shadow-lg shadow-amber-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Video className="w-4 h-4" /> Google Meet Links ({meetings.length})
            </button>

            <button
              onClick={() => setActiveTab("availability")}
              className={`px-4 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
                activeTab === "availability"
                  ? "bg-gradient-to-r from-amber-600 to-orange-600 text-white shadow-lg shadow-amber-500/20"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Clock className="w-4 h-4" /> Team Availability Slots ({slots.length})
            </button>
          </div>

          {/* Tab Views */}
          {activeTab === "events" && (
            <div className="space-y-3">
              {selectedProjectId && (
                <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
                  <button
                    onClick={() => setShowScheduleForm((v) => !v)}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 font-semibold text-sm border border-amber-500/30 transition-all"
                  >
                    <CalendarPlus className="w-4 h-4" /> {showScheduleForm ? "Cancel" : "Schedule a Meeting"}
                  </button>

                  {showScheduleForm && (
                    <form onSubmit={handleScheduleMeeting} className="space-y-3 pt-1">
                      <input
                        type="text"
                        placeholder="Meeting title"
                        value={meetingTitle}
                        onChange={(e) => setMeetingTitle(e.target.value)}
                        required
                        className="w-full px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                      />
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Start</label>
                          <input
                            type="datetime-local"
                            value={meetingStart}
                            onChange={(e) => setMeetingStart(e.target.value)}
                            required
                            className="w-full px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">End</label>
                          <input
                            type="datetime-local"
                            value={meetingEnd}
                            onChange={(e) => setMeetingEnd(e.target.value)}
                            required
                            className="w-full px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                          />
                        </div>
                      </div>
                      <input
                        type="text"
                        placeholder="Attendee emails, comma-separated (optional)"
                        value={meetingAttendees}
                        onChange={(e) => setMeetingAttendees(e.target.value)}
                        className="w-full px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-amber-500"
                      />

                      {scheduleError && (
                        <div className="px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                          {scheduleError}
                        </div>
                      )}

                      <button
                        type="submit"
                        disabled={scheduling}
                        className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:opacity-90 text-white font-bold text-sm shadow-lg shadow-amber-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                      >
                        {scheduling ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CalendarPlus className="w-4 h-4" />} Create Real Google Calendar Event
                      </button>
                    </form>
                  )}
                </div>
              )}

              {loadingSyncedMeetings ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading synced calendar events...</div>
              ) : syncedMeetingsError ? (
                <div className="p-8 text-center text-rose-300 text-sm">{syncedMeetingsError}</div>
              ) : !selectedProjectId ? (
                <div className="p-8 text-center text-slate-400 text-sm">Select a project above to view its synced calendar events.</div>
              ) : syncedMeetings.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  No synced events yet for this project. Click "Refresh Calendar Sync" to pull events from Google Calendar
                  (requires an active Google Calendar connection -- see the Integrations page).
                </div>
              ) : (
                syncedMeetings.map((m) => (
                  <div key={m.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-amber-500/40 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 mt-1">
                        <Calendar className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-base font-bold text-white">{m.title}</h4>
                        <p className="text-xs text-slate-400 mt-1">
                          {m.attendees.length > 0 ? `Attendees: ${m.attendees.join(", ")}` : "No attendees recorded"}
                        </p>
                      </div>
                    </div>
                    <div className="text-xs text-amber-300 font-mono font-semibold">
                      {new Date(m.start_time).toLocaleString()} - {new Date(m.end_time).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "meetings" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {loadingMeetings ? (
                <div className="p-8 text-center text-slate-400 font-medium col-span-2">Loading Meet links...</div>
              ) : (
                meetings.map((meet) => (
                  <div key={meet.meeting_id} className="p-5 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-base font-bold text-white flex items-center gap-2">
                        <Video className="w-4 h-4 text-emerald-400" /> {meet.title}
                      </h4>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Scheduled</span>
                    </div>
                    <a
                      href={meet.join_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-xs font-semibold border border-emerald-500/30 transition-all"
                    >
                      <ExternalLink className="w-3.5 h-3.5" /> Join Google Meet
                    </a>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "availability" && (
            <div className="space-y-3">
              {loadingSlots ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading availability...</div>
              ) : (
                slots.map((slot, idx) => (
                  <div key={idx} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-bold text-white">{slot.date} — {slot.slot}</h4>
                      <p className="text-xs text-slate-400 mt-1">Available: {slot.participants_available.join(", ")}</p>
                    </div>
                    <span className="px-3 py-1 rounded-lg bg-amber-500/10 text-amber-300 text-xs font-semibold border border-amber-500/20">
                      <Users className="w-3.5 h-3.5 inline mr-1" /> {slot.participants_available.length} Ready
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
