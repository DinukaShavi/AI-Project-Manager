// TypeScript Models for Google Calendar Integration

export interface CalendarEvent {
  id: string;
  summary: string;
  start_time: string;
  end_time: string;
  organizer: string;
  location?: string;
  attendees_count: number;
}

export interface GoogleMeeting {
  meeting_id: string;
  title: string;
  join_url: string;
  start_time: string;
  status: string;
}

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
// section 19 `meetings` table) -- distinct from GoogleMeeting above, which is the hardcoded
// GET /integrations/google/meetings mock's "Meet call link" shape.
export interface SyncedMeeting {
  id: string;
  external_event_id: string;
  title: string;
  start_time: string;
  end_time: string;
  attendees: string[];
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
  description?: string;
}
