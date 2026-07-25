"use client";

import { useState, useEffect, useCallback } from "react";
import { calendarApi } from "../api/calendar.api";
import { CalendarEvent, GoogleMeeting, AvailabilitySlot } from "../types/calendar";

export function useCalendarEvents(orgId: string) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await calendarApi.getEvents(orgId);
      setEvents(res.events || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Google Calendar events");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  return { events, loading, error, refresh: fetchEvents };
}

export function useCalendarMeetings(orgId: string) {
  const [meetings, setMeetings] = useState<GoogleMeeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMeetings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await calendarApi.getMeetings(orgId);
      setMeetings(res.meetings || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Google Meetings");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchMeetings();
  }, [fetchMeetings]);

  return { meetings, loading, error, refresh: fetchMeetings };
}

export function useCalendarAvailability(orgId: string) {
  const [slots, setSlots] = useState<AvailabilitySlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAvailability = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await calendarApi.getAvailability(orgId);
      setSlots(res.available_slots || []);
    } catch (err: any) {
      setError(err.message || "Failed to load team availability slots");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchAvailability();
  }, [fetchAvailability]);

  return { slots, loading, error, refresh: fetchAvailability };
}
