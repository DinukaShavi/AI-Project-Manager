import { httpClient } from "./client";
import { RecommendationActionResponse, RecommendationActionType, RecommendationListParams, RecommendationsResponse } from "../types/recommendation";

export const recommendationApi = {
  list: async (params?: RecommendationListParams): Promise<RecommendationsResponse> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.type) query.set("type", params.type);
    const qs = query.toString();
    return httpClient<RecommendationsResponse>(`/recommendations${qs ? `?${qs}` : ""}`, {
      method: "GET",
    });
  },

  applyAction: async (id: string, action: RecommendationActionType): Promise<RecommendationActionResponse> => {
    return httpClient<RecommendationActionResponse>(`/recommendations/${id}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
  },
};
