import { httpClient } from "./client";

/**
 * Generic OAuth authorize/revoke actions shared by every provider that uses the backend's
 * real per-organization OAuth flow (Slack, Google Calendar; GitHub has its own equivalent
 * methods in github.api.ts). The backend derives the organization from the authenticated
 * JWT, never from a client-supplied id -- these calls never carry organization_id.
 */
export const integrationOAuthApi = {
  getAuthorizeUrl: async (provider: string): Promise<{ authorization_url: string }> => {
    return httpClient<{ authorization_url: string }>(`/integrations/oauth/${provider}/authorize`);
  },

  completeCallback: async (provider: string, code: string): Promise<{ status: string }> => {
    return httpClient<{ status: string }>(`/integrations/oauth/${provider}/callback?code=${encodeURIComponent(code)}`);
  },

  revokeConnection: async (provider: string): Promise<{ status: string }> => {
    return httpClient<{ status: string }>(`/integrations/oauth/${provider}`, {
      method: "DELETE",
    });
  },
};
