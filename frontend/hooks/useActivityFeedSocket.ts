"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getStoredAuthToken } from "../api/client";
import { ActivityUpdate } from "../types/activityFeed";

const WS_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/^http/, "ws");
const RECONNECT_DELAY_MS = 3000;
const MAX_FEED_LENGTH = 50;

export type ActivityFeedSocketState = "connecting" | "open" | "closed" | "error";

/**
 * Live feed of real GitHub/Jira/Slack activity (Phase 66), structurally identical to
 * useIntegrationStatusSocket.ts's reconnect/JWT pattern -- same org-scoped WebSocket channel,
 * a different event type (activity_update instead of integration_status_update). Keeps only
 * the most recent MAX_FEED_LENGTH entries, newest first.
 */
export function useActivityFeedSocket() {
  const [feed, setFeed] = useState<ActivityUpdate[]>([]);
  const [socketState, setSocketState] = useState<ActivityFeedSocketState>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);

  const connect = useCallback(() => {
    const token = getStoredAuthToken();
    if (!token) {
      setSocketState("error");
      return;
    }

    setSocketState("connecting");
    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=${encodeURIComponent(token)}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setSocketState("open");
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === "activity_update" && msg.payload) {
          setFeed((prev) => [msg.payload as ActivityUpdate, ...prev].slice(0, MAX_FEED_LENGTH));
        }
      } catch {
        // Ignore malformed frames -- never let a bad payload crash the dashboard.
      }
    };

    ws.onclose = () => {
      setSocketState("closed");
      if (shouldReconnectRef.current) {
        reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      setSocketState("error");
    };
  }, []);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { feed, socketState };
}
