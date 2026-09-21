"use client";

import { useState, useEffect, useCallback } from "react";
import { slackApi } from "../api/slack.api";
import { SlackMessage, SlackUser, SlackActivityAnalysis } from "../types/slack";

/** Real (Phase 63), scoped to a real mapped channel id. Skips fetching while none is selected. */
export function useSlackMessages(channelId: string | null) {
  const [messages, setMessages] = useState<SlackMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMessages = useCallback(async () => {
    if (!channelId) {
      setMessages([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getMessages(channelId);
      setMessages(res.messages || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack messages");
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  return { messages, loading, error, refresh: fetchMessages };
}

/** Real (Phase 63) -- organization derived from the authenticated JWT server-side. */
export function useSlackUsers() {
  const [users, setUsers] = useState<SlackUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getUsers();
      setUsers(res.users || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  return { users, loading, error, refresh: fetchUsers };
}

/** Real (Phase 72), scoped to a real mapped channel id. Skips fetching while none is selected. */
export function useSlackActivity(channelId: string | null) {
  const [activity, setActivity] = useState<SlackActivityAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchActivity = useCallback(async () => {
    if (!channelId) {
      setActivity(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getActivityAnalysis(channelId);
      setActivity(res);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack activity analysis");
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    fetchActivity();
  }, [fetchActivity]);

  return { activity, loading, error, refresh: fetchActivity };
}
