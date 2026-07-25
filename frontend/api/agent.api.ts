import { httpClient } from "./client";
import { AgentExecutionRequest, AgentExecutionResponse, AgentPersona } from "./types";

export const agentApi = {
  executeAgentPersona: async (payload: AgentExecutionRequest): Promise<AgentExecutionResponse> => {
    return httpClient<AgentExecutionResponse>("/agents/execute", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getPersonas: async (): Promise<{ personas: AgentPersona[] }> => {
    return httpClient<{ personas: AgentPersona[] }>("/agents/personas");
  },

  getAgentState: async (agentId: string): Promise<any> => {
    return httpClient<any>(`/agents/state/${agentId}`);
  },

  transitionAgentState: async (agentId: string, state: string): Promise<any> => {
    return httpClient<any>("/agents/state/transition", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, target_state: state }),
    });
  },
};
