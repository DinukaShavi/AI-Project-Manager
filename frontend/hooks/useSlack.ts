"use client";

import { useState, useEffect, useCallback } from "react";
import { slackApi } from "../api/slack.api";
import { SlackChannel, SlackMessage, SlackUser, SlackActivityAnalysis } from "../types/slack";

export function useSlackChannels(orgId: string) {
  const [channels, setChannels] = useState<SlackChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getChannels(orgId);
      setChannels(res.channels || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack channels");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  return { channels, loading, error, refresh: fetchChannels };
}

export function useSlackMessages(orgId: string, channelId: string = "C01ABCDEF01") {
  const [messages, setMessages] = useState<SlackMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMessages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getMessages(orgId, channelId);
      setMessages(res.messages || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack messages");
    } finally {
      setLoading(false);
    }
  }, [orgId, channelId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  return { messages, loading, error, refresh: fetchMessages };
}

export function useSlackUsers(orgId: string) {
  const [users, setUsers] = useState<SlackUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getUsers(orgId);
      setUsers(res.users || []);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack users");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  return { users, loading, error, refresh: fetchUsers };
}

export function useSlackActivity(orgId: string) {
  const [activity, setActivity] = useState<SlackActivityAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchActivity = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await slackApi.getActivityAnalysis(orgId);
      setActivity(res);
    } catch (err: any) {
      setError(err.message || "Failed to load Slack activity analysis");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchActivity();
  }, [fetchActivity]);

  return { activity, loading, error, refresh: fetchActivity };
}
