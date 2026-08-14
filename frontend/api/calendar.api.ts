import { httpClient } from "./client";
import { CalendarEvent, GoogleMeeting, AvailabilitySlot, CalendarSyncRequest, CalendarSyncResponse, SyncedMeetingsResponse, CreateCalendarEventRequest, SyncedMeeting } from "../types/calendar";

export const calendarApi = {
  getEvents: async (orgId: string): Promise<{ events: CalendarEvent[] }> => {
    return httpClient<{ events: CalendarEvent[] }>(`/integrations/google/events?organization_id=${orgId}`);
  },

  syncEvents: async (payload: CalendarSyncRequest): Promise<CalendarSyncResponse> => {
    return httpClient<CalendarSyncResponse>("/integrations/calendar/sync", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getSyncedMeetings: async (projectId: string): Promise<SyncedMeetingsResponse> => {
    return httpClient<SyncedMeetingsResponse>(`/integrations/calendar/meetings?project_id=${projectId}`);
  },

  createEvent: async (payload: CreateCalendarEventRequest): Promise<SyncedMeeting> => {
    return httpClient<SyncedMeeting>("/integrations/calendar/meetings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getMeetings: async (orgId: string): Promise<{ meetings: GoogleMeeting[] }> => {
    return httpClient<{ meetings: GoogleMeeting[] }>(`/integrations/google/meetings?organization_id=${orgId}`);
  },

  getAvailability: async (orgId: string): Promise<{ available_slots: AvailabilitySlot[] }> => {
    return httpClient<{ available_slots: AvailabilitySlot[] }>(`/integrations/google/availability?organization_id=${orgId}`);
  },
};
