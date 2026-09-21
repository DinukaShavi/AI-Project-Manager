"use client";

import { useState, useEffect, useCallback } from "react";
import { calendarApi } from "../api/calendar.api";
import { AvailabilitySlot } from "../types/calendar";

/**
 * Real (Phase 65) team availability across the org's real members, for a given date range.
 * Skips fetching while no range is provided.
 */
export function useCalendarAvailability(startDate: string | null, endDate: string | null) {
  const [slots, setSlots] = useState<AvailabilitySlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAvailability = useCallback(async () => {
    if (!startDate || !endDate) {
      setSlots([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await calendarApi.getAvailability(startDate, endDate);
      setSlots(res.available_slots || []);
    } catch (err: any) {
      setError(err.message || "Failed to load team availability slots");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    fetchAvailability();
  }, [fetchAvailability]);

  return { slots, loading, error, refresh: fetchAvailability };
}
