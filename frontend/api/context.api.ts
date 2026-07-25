import { httpClient } from "./client";
import { ContextSearchRequest, ContextSearchResponse, IndexDocumentRequest, MemorySearchRequest, MemorySearchResponse } from "./types";

export const contextApi = {
  searchContext: async (payload: ContextSearchRequest): Promise<ContextSearchResponse> => {
    return httpClient<ContextSearchResponse>("/context/search", {
      method: "POST",
      body: JSON.stringify({
        organization_id: payload.organization_id,
        query: payload.query || payload.query_text,
        query_text: payload.query_text || payload.query,
        project_id: payload.project_id,
        top_k: payload.top_k || 5,
      }),
    });
  },

  indexDocument: async (payload: IndexDocumentRequest): Promise<{ status: string; chunks_indexed: number }> => {
    return httpClient<{ status: string; chunks_indexed: number }>("/context/index", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  searchMemory: async (payload: MemorySearchRequest): Promise<MemorySearchResponse> => {
    return httpClient<MemorySearchResponse>("/memory/search", {
      method: "POST",
      body: JSON.stringify({
        organization_id: payload.organization_id,
        query: payload.query,
        limit: payload.limit || 5,
      }),
    });
  },
};
