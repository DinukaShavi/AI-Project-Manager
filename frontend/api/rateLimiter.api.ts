import { httpClient } from "./client";
import { RateLimitCheckResponse } from "./types";

export const rateLimiterApi = {
  checkRateLimit: async (dimension: string, identifier: string, tokensNeeded: number = 1.0): Promise<RateLimitCheckResponse> => {
    return httpClient<RateLimitCheckResponse>("/rate-limit/check", {
      method: "POST",
      body: JSON.stringify({ dimension, identifier, tokens_needed: tokensNeeded }),
    });
  },

  getBucketStatus: async (dimension: string, identifier: string): Promise<RateLimitCheckResponse> => {
    return httpClient<RateLimitCheckResponse>(`/rate-limit/status/${dimension}/${identifier}`);
  },
};
