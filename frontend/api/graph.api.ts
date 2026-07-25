import { httpClient } from "./client";
import { GraphTraverseResponse } from "./types";

export const graphApi = {
  traverseGraph: async (startNodeId: string, minWeight: number = 0.10): Promise<GraphTraverseResponse> => {
    return httpClient<GraphTraverseResponse>(`/graph-evolution/traverse/${startNodeId}?min_weight=${minWeight}`);
  },

  linkEntities: async (payload: { source_id: string; target_id: string; relation_type: string; base_weight?: number }): Promise<any> => {
    return httpClient<any>("/graph-evolution/link", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  inferEdges: async (events: any[]): Promise<any> => {
    return httpClient<any>("/graph-evolution/infer", {
      method: "POST",
      body: JSON.stringify({ events }),
    });
  },

  decaySweep: async (simulatedAgeDays: number = 30.0, decayFactor: number = 0.01): Promise<any> => {
    return httpClient<any>("/graph-evolution/decay-sweep", {
      method: "POST",
      body: JSON.stringify({ simulated_age_days: simulatedAgeDays, decay_factor: decayFactor }),
    });
  },
};
