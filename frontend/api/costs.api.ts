import { httpClient } from "./client";
import { CostSummaryResponse } from "./types";

export const costsApi = {
  getCostSummary: async (orgId: string): Promise<CostSummaryResponse> => {
    return httpClient<CostSummaryResponse>(`/costs/summary/${orgId}`);
  },
};
