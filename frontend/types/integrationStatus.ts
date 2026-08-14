// TypeScript Models for Integration Connection Status (Connection Center dashboard)

export type IntegrationConnectionStatus = "connected" | "disconnected" | "reauth_required";

export interface IntegrationStatus {
  provider: string;
  status: IntegrationConnectionStatus;
  updated_at: string | null;
}

export interface IntegrationStatusListResponse {
  organization_id: string;
  integrations: IntegrationStatus[];
}

export interface IntegrationStatusUpdateEvent {
  event: "integration_status_update";
  payload: {
    provider: string;
    status: IntegrationConnectionStatus;
    timestamp: string;
  };
}
