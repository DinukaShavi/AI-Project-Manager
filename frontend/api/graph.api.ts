import { httpClient } from "./client";
import { GraphTraverseResponse } from "./types";

export const graphApi = {
  traverseGraph: async (startNodeId: string, minWeight: number = 0.10): Promise<GraphTraverseResponse> => {
    return httpClient<GraphTraverseResponse>(`/graph-evolution/traverse/${startNodeId}?min_weight=${minWeight}`);
  },
};
