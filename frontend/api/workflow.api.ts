import { httpClient } from "./client";
import { WorkflowExecutionRequest, WorkflowExecutionResponse } from "./types";

export const workflowApi = {
  executeWorkflow: async (payload: WorkflowExecutionRequest): Promise<WorkflowExecutionResponse> => {
    return httpClient<WorkflowExecutionResponse>("/workflows/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getTemplates: async (): Promise<{ templates: any[] }> => {
    return httpClient<{ templates: any[] }>("/workflows/templates");
  },

  getExecutionStatus: async (executionId: string): Promise<any> => {
    return httpClient<any>(`/workflows/executions/${executionId}`);
  },
};
