"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getStoredAuthToken } from "../api/client";
import { IntegrationConnectionStatus, IntegrationStatus } from "../types/integrationStatus";

const WS_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/^http/, "ws");
const RECONNECT_DELAY_MS = 3000;

export type IntegrationSocketState = "connecting" | "open" | "closed" | "error";

/**
 * Live integration connection-status feed, per api_contract.md section 17's documented
 * WebSocket contract (JWT via ?token= query param, path /api/v1/ws). Reconnects
 * automatically on drop while the component stays mounted; stops and closes cleanly on
 * unmount. Never touches localStorage for anything but the already-stored JWT -- no
 * credential material is read from or written into socket state.
 */
export function useIntegrationStatusSocket() {
  const [statusUpdates, setStatusUpdates] = useState<Record<string, IntegrationStatus>>({});
  const [socketState, setSocketState] = useState<IntegrationSocketState>("connecting");
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
        if (msg.event === "integration_status_update" && msg.payload?.provider) {
          const { provider, status, timestamp } = msg.payload as {
            provider: string;
            status: IntegrationConnectionStatus;
            timestamp: string;
          };
          setStatusUpdates((prev) => ({
            ...prev,
            [provider]: { provider, status, updated_at: timestamp },
          }));
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

  return { statusUpdates, socketState };
}
