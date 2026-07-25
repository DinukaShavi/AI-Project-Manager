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
