"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  authApi,
  getStoredAuthToken,
  setStoredAuthToken,
  clearStoredAuthToken,
  ApiError,
  User,
} from "../api";

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const loadCurrentUser = useCallback(async () => {
    if (!getStoredAuthToken()) {
      setUser(null);
      setIsAuthenticated(false);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
      setIsAuthenticated(true);
    } catch (err) {
      clearStoredAuthToken();
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCurrentUser();
  }, [loadCurrentUser]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login({ email, password });
    setStoredAuthToken(tokens.access_token, tokens.refresh_token);
    const currentUser = await authApi.getCurrentUser();
    setUser(currentUser);
    setIsAuthenticated(true);
    return currentUser;
  }, []);

  const logout = useCallback(() => {
    clearStoredAuthToken();
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const value: AuthContextValue = { user, isAuthenticated, isLoading, login, logout };
  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

export type { ApiError };
