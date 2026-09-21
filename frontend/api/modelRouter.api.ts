import { httpClient } from "./client";
import { ModelMatrixResponse } from "./types";

export const modelRouterApi = {
  getModelMatrix: async (): Promise<ModelMatrixResponse> => {
    return httpClient<ModelMatrixResponse>("/models/matrix");
  },
};
