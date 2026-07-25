import { httpClient } from "./client";
import { CalendarEvent, GoogleMeeting, AvailabilitySlot } from "../types/calendar";

export const calendarApi = {
  getEvents: async (orgId: string): Promise<{ events: CalendarEvent[] }> => {
    return httpClient<{ events: CalendarEvent[] }>(`/integrations/google/events?organization_id=${orgId}`);
  },

  getMeetings: async (orgId: string): Promise<{ meetings: GoogleMeeting[] }> => {
    return httpClient<{ meetings: GoogleMeeting[] }>(`/integrations/google/meetings?organization_id=${orgId}`);
  },

  getAvailability: async (orgId: string): Promise<{ available_slots: AvailabilitySlot[] }> => {
    return httpClient<{ available_slots: AvailabilitySlot[] }>(`/integrations/google/availability?organization_id=${orgId}`);
  },
};
