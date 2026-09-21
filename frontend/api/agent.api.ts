import { httpClient } from "./client";
import { AgentExecutionRequest, AgentExecutionResponse } from "./types";

export const agentApi = {
  executeAgentPersona: async (payload: AgentExecutionRequest): Promise<AgentExecutionResponse> => {
    return httpClient<AgentExecutionResponse>("/agents/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
