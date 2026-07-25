// Central HTTP Client with Token Injection, Interceptors, Error Handling & Loading States

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface ApiClientOptions extends RequestInit {
  token?: string;
  skipAuth?: boolean;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/**
 * Standard Token Resolver: Retrieves JWT from localStorage or cookie storage.
 */
export function getStoredAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("ai_tpm_jwt_token");
  }
  return null;
}

/**
 * Centralized HTTP Client Request Function with interceptor hooks.
 */
export async function httpClient<T>(endpoint: string, options: ApiClientOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  // 1. Request Interceptor: Attach Content-Type & Bearer JWT Token
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (!options.skipAuth) {
    const token = options.token || getStoredAuthToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  // 2. Execute Fetch Call
  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // 3. Response Interceptor & Error Handler
    if (!response.ok) {
      let errorData: any = null;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      
      const errorMessage = typeof errorData === "object" && errorData?.detail
        ? (typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail))
        : `HTTP Error ${response.status}: ${response.statusText}`;

      throw new ApiError(response.status, errorMessage, errorData);
    }

    return await response.json();
  } catch (error: any) {
    if (error instanceof ApiError) {
      throw error;
    }
    console.warn(`[API Client Network Error] Request failed for ${endpoint}:`, error);
    throw new ApiError(500, error.message || "Network request failed", error);
  }
}
