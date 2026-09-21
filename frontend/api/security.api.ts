import { httpClient } from "./client";
import { SecurityScanResponse } from "./types";

export const securityApi = {
  scanPrompt: async (text: string): Promise<SecurityScanResponse> => {
    return httpClient<SecurityScanResponse>("/security/scan-prompt", {
      method: "POST",
      body: JSON.stringify({ input_text: text }),
    });
  },
};
