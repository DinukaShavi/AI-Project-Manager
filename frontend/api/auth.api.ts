import { httpClient } from "./client";
import { AuthResponse, LoginRequest, RoleAssignRequest, User } from "./types";

export const authApi = {
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    return httpClient<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
      skipAuth: true,
    });
  },

  getCurrentUser: async (): Promise<User> => {
    return httpClient<User>("/users/me");
  },

  assignRole: async (userId: string, payload: RoleAssignRequest): Promise<User> => {
    return httpClient<User>(`/users/${userId}/roles`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  revokeRole: async (userId: string, roleName: string): Promise<User> => {
    return httpClient<User>(`/users/${userId}/roles/${roleName}`, {
      method: "DELETE",
    });
  },
};
