import { httpClient } from "./client";
import { AuthResponse, LoginRequest, RegisterRequest, RoleAssignRequest, User, UserUpdateRequest } from "./types";

export const authApi = {
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    return httpClient<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
      skipAuth: true,
    });
  },

  register: async (payload: RegisterRequest): Promise<User> => {
    return httpClient<User>("/users/register", {
      method: "POST",
      body: JSON.stringify(payload),
      skipAuth: true,
    });
  },

  getCurrentUser: async (): Promise<User> => {
    return httpClient<User>("/users/me");
  },

  updateUserProfile: async (payload: UserUpdateRequest): Promise<User> => {
    return httpClient<User>("/users/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
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
