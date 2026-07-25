import { httpClient } from "./client";

export const integrationsApi = {
  getIntegrations: async (orgId: string): Promise<{ integrations_count: number; integrations: any[] }> => {
    return httpClient<{ integrations_count: number; integrations: any[] }>(`/integrations?organization_id=${orgId}`);
  },

  getConnectUrl: async (provider: string, orgId: string): Promise<{ connect_url: string }> => {
    return httpClient<{ connect_url: string }>(`/integrations/connect/${provider}?organization_id=${orgId}`);
  },

  handleCallback: async (provider: string, code: string, state?: string): Promise<{ status: string; integration_id: string }> => {
    return httpClient<{ status: string; integration_id: string }>(`/integrations/callback/${provider}?code=${code}&state=${state || ""}`);
  },
};
