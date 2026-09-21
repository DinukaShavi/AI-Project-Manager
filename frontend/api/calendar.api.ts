import { httpClient } from "./client";
import { AvailabilitySlot, CalendarSyncRequest, CalendarSyncResponse, SyncedMeetingsResponse, CreateCalendarEventRequest, SyncedMeeting } from "../types/calendar";

export const calendarApi = {
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

  // Real (Phase 65) -- organization is derived from the authenticated JWT server-side.
  getAvailability: async (startDate: string, endDate: string): Promise<{ available_slots: AvailabilitySlot[] }> => {
    return httpClient<{ available_slots: AvailabilitySlot[] }>(
      `/integrations/calendar/availability?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`
    );
  },
};
