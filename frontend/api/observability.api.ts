import { httpClient } from "./client";
import { TracesResponse, MetricsSummaryResponse } from "./types";

export const observabilityApi = {
  getTraces: async (): Promise<TracesResponse> => {
    return httpClient<TracesResponse>("/observability/traces");
  },

  getMetrics: async (): Promise<MetricsSummaryResponse> => {
    return httpClient<MetricsSummaryResponse>("/observability/metrics");
  },

  injectSpan: async (payload: { name: string; duration_ms: number; correlation_id?: string; attributes?: Record<string, any> }): Promise<any> => {
    return httpClient<any>("/observability/spans", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
