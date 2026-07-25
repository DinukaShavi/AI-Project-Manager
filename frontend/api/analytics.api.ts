import { httpClient } from "./client";
import { SprintAnalytics, BurndownResponse, PredictiveCompletionForecast } from "./types";

export const analyticsApi = {
  getSprintAnalytics: async (projectId: string): Promise<SprintAnalytics> => {
    return httpClient<SprintAnalytics>(`/analytics/sprint?project_id=${projectId}`);
  },

  getBurndownTrajectory: async (projectId: string, totalDays: number = 14): Promise<BurndownResponse> => {
    return httpClient<BurndownResponse>(`/analytics/burndown?project_id=${projectId}&total_days=${totalDays}`);
  },

  getPredictiveCompletionForecast: async (projectId: string): Promise<PredictiveCompletionForecast> => {
    return httpClient<PredictiveCompletionForecast>(`/analytics/predict-completion?project_id=${projectId}`);
  },
};
