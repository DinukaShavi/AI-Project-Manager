import { httpClient } from "./client";
import { CostSummaryResponse, CostAlertResponse } from "./types";

export const costsApi = {
  getCostSummary: async (orgId: string): Promise<CostSummaryResponse> => {
    return httpClient<CostSummaryResponse>(`/costs/summary/${orgId}`);
  },

  getCostAlerts: async (orgId: string): Promise<CostAlertResponse> => {
    return httpClient<CostAlertResponse>(`/costs/alerts/${orgId}`);
  },

  recordUsage: async (payload: { organization_id: string; model_name: string; prompt_tokens: number; completion_tokens: number; cache_hit_tokens?: number }): Promise<any> => {
    return httpClient<any>("/costs/record", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
