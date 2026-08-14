import { httpClient } from "./client";
import { IntegrationStatusListResponse } from "../types/integrationStatus";

export const integrationStatusApi = {
  getStatuses: async (): Promise<IntegrationStatusListResponse> => {
    return httpClient<IntegrationStatusListResponse>("/integrations/status");
  },
};
