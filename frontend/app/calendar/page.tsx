"use client";

import React, { useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { useCalendarEvents, useCalendarMeetings, useCalendarAvailability } from "../../hooks/useCalendar";
import { Calendar, Video, Clock, Users, ExternalLink, RefreshCw } from "lucide-react";

const DUMMY_ORG_ID = "00000000-0000-0000-0000-000000000001";

export default function CalendarIntegrationPage() {
  const [activeTab, setActiveTab] = useState<"events" | "meetings" | "availability">("events");

  const { events, loading: loadingEvents, error: errorEvents, refresh: refreshEvents } = useCalendarEvents(DUMMY_ORG_ID);
  const { meetings, loading: loadingMeetings, error: errorMeetings, refresh: refreshMeetings } = useCalendarMeetings(DUMMY_ORG_ID);
  const { slots, loading: loadingSlots, error: errorSlots, refresh: refreshSlots } = useCalendarAvailability(DUMMY_ORG_ID);

  const handleRefreshAll = () => {
    refreshEvents();
    refreshMeetings();
    refreshSlots();
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

            <button
              onClick={handleRefreshAll}
              className="px-4 py-2.5 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 font-semibold text-sm border border-amber-500/30 transition-all flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" /> Refresh Calendar Sync
            </button>
          </div>

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
              <Calendar className="w-4 h-4" /> Events & Standups ({events.length})
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
              {loadingEvents ? (
                <div className="p-8 text-center text-slate-400 font-medium">Loading Events...</div>
              ) : (
                events.map((evt) => (
                  <div key={evt.id} className="p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-amber-500/40 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 mt-1">
                        <Calendar className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-base font-bold text-white">{evt.summary}</h4>
                        <p className="text-xs text-slate-400 mt-1 flex items-center gap-2">
                          <span>Location: <strong className="text-slate-200">{evt.location}</strong></span>
                          <span>•</span>
                          <span>Organizer: {evt.organizer}</span>
                        </p>
                      </div>
                    </div>
                    <div className="text-xs text-amber-300 font-mono font-semibold">
                      {new Date(evt.start_time).toLocaleTimeString()} - {new Date(evt.end_time).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "meetings" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {meetings.map((meet) => (
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
              ))}
            </div>
          )}

          {activeTab === "availability" && (
            <div className="space-y-3">
              {slots.map((slot, idx) => (
                <div key={idx} className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-bold text-white">{slot.date} — {slot.slot}</h4>
                    <p className="text-xs text-slate-400 mt-1">Available: {slot.participants_available.join(", ")}</p>
                  </div>
                  <span className="px-3 py-1 rounded-lg bg-amber-500/10 text-amber-300 text-xs font-semibold border border-amber-500/20">
                    <Users className="w-3.5 h-3.5 inline mr-1" /> {slot.participants_available.length} Ready
                  </span>
                </div>
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
