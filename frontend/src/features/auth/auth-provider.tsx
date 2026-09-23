"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, logout as logoutRequest, type AuthUser } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  sessionError: string | null;
  confirmSession: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  sessionError: null,
  confirmSession: async () => undefined,
  logout: async () => undefined,
});

function sessionErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The session could not be checked.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const sessionVersion = useRef(0);

  useEffect(() => {
    let active = true;
    const version = sessionVersion.current;
    getCurrentUser()
      .then((current) => {
        if (active && version === sessionVersion.current) {
          setUser(current);
          setSessionError(null);
        }
      })
      .catch((error) => {
        if (active && version === sessionVersion.current) {
          if (error instanceof ApiError && error.status === 401) setUser(null);
          else setSessionError(sessionErrorMessage(error));
        }
      })
      .finally(() => { if (active && version === sessionVersion.current) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const expired = () => { setUser(null); setSessionError(null); setLoading(false); };
    window.addEventListener("ielts:session-expired", expired);
    return () => window.removeEventListener("ielts:session-expired", expired);
  }, []);

  const confirmSession = useCallback(async () => {
    const version = ++sessionVersion.current;
    setLoading(true);
    try {
      const current = await getCurrentUser();
      if (version === sessionVersion.current) {
        setUser(current);
        setSessionError(null);
        router.refresh();
      }
    } catch (error) {
      if (version === sessionVersion.current) {
        if (error instanceof ApiError && error.status === 401) setUser(null);
        else setSessionError(sessionErrorMessage(error));
      }
      throw error;
    } finally {
      if (version === sessionVersion.current) setLoading(false);
    }
  }, [router]);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
      sessionVersion.current += 1;
      setUser(null);
      setSessionError(null);
      router.push("/login");
      router.refresh();
    } catch (error) {
      setSessionError(sessionErrorMessage(error));
    }
  }, [router]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    sessionError,
    confirmSession,
    logout,
  }), [confirmSession, loading, logout, sessionError, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
