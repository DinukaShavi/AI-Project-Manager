import { httpClient } from "./client";
import { ModelMatrixResponse, ModelRouteResponse } from "./types";

export const modelRouterApi = {
  getModelMatrix: async (): Promise<ModelMatrixResponse> => {
    return httpClient<ModelMatrixResponse>("/models/matrix");
  },

  routeTask: async (taskCategory: string, budgetTier: string = "standard", payloadLength: number = 500): Promise<ModelRouteResponse> => {
    return httpClient<ModelRouteResponse>("/models/route", {
      method: "POST",
      body: JSON.stringify({
        task_category: taskCategory,
        budget_tier: budgetTier,
        payload_token_length: payloadLength,
      }),
    });
  },
};
