import { httpClient } from "./client";
import { ContextSearchRequest, ContextSearchResponse } from "./types";
import { ContextSnapshot } from "../types/contextSnapshot";

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

  // Real (Phase 68) -- latest templated summary of a project's real activity + real
  // knowledge graph bottlenecks. 404 (thrown by httpClient as ApiError) if none exists yet.
  getProjectSnapshot: async (projectId: string): Promise<ContextSnapshot> => {
    return httpClient<ContextSnapshot>(`/context/projects/${projectId}/snapshot`);
  },

  regenerateProjectSnapshot: async (projectId: string): Promise<ContextSnapshot> => {
    return httpClient<ContextSnapshot>(`/context/projects/${projectId}/snapshot`, {
      method: "POST",
    });
  },
};
