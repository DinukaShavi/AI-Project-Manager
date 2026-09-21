import { httpClient } from "./client";
import { SprintAnalytics } from "./types";

export const analyticsApi = {
  getSprintAnalytics: async (projectId: string): Promise<SprintAnalytics> => {
    return httpClient<SprintAnalytics>(`/analytics/sprint?project_id=${projectId}`);
  },
};
