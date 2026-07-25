import { httpClient } from "./client";
import { AuthResponse, LoginRequest, RegisterRequest, User, UserUpdateRequest } from "./types";

export const authApi = {
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    return httpClient<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
      skipAuth: true,
    });
  },

  register: async (payload: RegisterRequest): Promise<AuthResponse> => {
    return httpClient<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
      skipAuth: true,
    });
  },

  getCurrentUser: async (): Promise<User> => {
    return httpClient<User>("/auth/me");
  },

  updateUserProfile: async (payload: UserUpdateRequest): Promise<User> => {
    return httpClient<User>("/users/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
};
