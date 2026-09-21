import { httpClient } from "./client";
import { WorkflowExecutionRequest, WorkflowExecutionResponse } from "./types";

export const workflowApi = {
  executeWorkflow: async (payload: WorkflowExecutionRequest): Promise<WorkflowExecutionResponse> => {
    return httpClient<WorkflowExecutionResponse>("/workflows/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
