import { httpClient } from "./client";
import { TracesResponse, MetricsSummaryResponse } from "./types";

export const observabilityApi = {
  getTraces: async (): Promise<TracesResponse> => {
    return httpClient<TracesResponse>("/observability/traces");
  },

  getMetrics: async (): Promise<MetricsSummaryResponse> => {
    return httpClient<MetricsSummaryResponse>("/observability/metrics");
  },
};
