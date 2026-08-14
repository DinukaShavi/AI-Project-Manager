import { httpClient } from "./client";
import { AuditLogListResponse, AuditLogFilters } from "./types";

export const auditLogApi = {
  listAuditLogs: async (filters: AuditLogFilters = {}): Promise<AuditLogListResponse> => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") params.set(key, String(value));
    });
    const qs = params.toString();
    return httpClient<AuditLogListResponse>(`/audit-logs${qs ? `?${qs}` : ""}`);
  },
};
