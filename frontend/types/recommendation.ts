// Recommendation API types (api_contract.md section 12.A)

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  score: number;
  created_at: string;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
}

export interface RecommendationListParams {
  status?: string;
  type?: string;
}

export type RecommendationActionType = "dismiss" | "accept";

export interface RecommendationActionResponse {
  id: string;
  status: string;
  title: string;
}
