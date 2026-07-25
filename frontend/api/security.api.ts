import { httpClient } from "./client";
import { SecurityScanResponse, SecuritySanitizeResponse } from "./types";

export const securityApi = {
  scanPrompt: async (text: string): Promise<SecurityScanResponse> => {
    return httpClient<SecurityScanResponse>("/security/scan-prompt", {
      method: "POST",
      body: JSON.stringify({ input_text: text }),
    });
  },

  maskPII: async (text: string): Promise<{ sanitized_text: string; masked_counts: Record<string, number> }> => {
    return httpClient<{ sanitized_text: string; masked_counts: Record<string, number> }>("/security/mask-pii", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  sanitizeInput: async (text: string): Promise<SecuritySanitizeResponse> => {
    return httpClient<SecuritySanitizeResponse>("/security/sanitize", {
      method: "POST",
      body: JSON.stringify({ input_text: text }),
    });
  },
};
