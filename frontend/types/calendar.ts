// TypeScript Models for Google Calendar Integration

export interface AvailabilitySlot {
  date: string;
  slot: string;
  participants_available: string[];
}

export interface CalendarSyncRequest {
  project_id: string;
  start_date: string;
  end_date: string;
}

export interface CalendarSyncResponse {
  sync_task_id: string;
  status: string;
  project_id: string;
  events_synced: number;
  events_found: number;
}

// Real synced meeting, per GET /integrations/calendar/meetings (database_schema_design.md
// section 19 `meetings` table). meet_link (Phase 65) is the event's real Google Meet join URL
// when it has one -- null if the event has no conference attached.
export interface SyncedMeeting {
  id: string;
  external_event_id: string;
  title: string;
  start_time: string;
  end_time: string;
  attendees: string[];
  meet_link: string | null;
}

export interface SyncedMeetingsResponse {
  project_id: string;
  total_meetings: number;
  meetings: SyncedMeeting[];
}

export interface CreateCalendarEventRequest {
  project_id: string;
  title: string;
  start_time: string;
  end_time: string;
  attendee_emails?: string[];
  // Real org members picked from organizationApi.listMembersDirectory() (Phase 64) -- resolved
  // to their real emails server-side.
  attendee_user_ids?: string[];
  description?: string;
}
