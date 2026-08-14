"use client";

import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { UserPlus, RefreshCw, ShieldAlert } from "lucide-react";
import { organizationApi, ApiError } from "../../api";

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await organizationApi.acceptInvitation(token, { full_name: fullName, password });
      router.push("/login?joined=1");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to accept invitation. Please try again.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center mb-4">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <UserPlus className="w-6 h-6 text-indigo-400" />
            </div>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">Join Your Team on AI-TPM</h1>
          <p className="text-xs text-slate-400 mt-1 text-center">Complete your account to accept the invitation.</p>
        </div>

        {!token ? (
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl text-center space-y-2">
            <ShieldAlert className="w-6 h-6 text-rose-400 mx-auto" />
            <p className="text-sm text-rose-300">This invitation link is missing its token.</p>
            <p className="text-xs text-slate-500">Ask your organization admin for a new invite link.</p>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl"
          >
            <div>
              <label htmlFor="fullName" className="text-xs font-semibold text-slate-300 block mb-1">
                Your Full Name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="text-xs font-semibold text-slate-300 block mb-1">
                Choose a Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                required
              />
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs"
              >
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 rounded-xl gradient-btn text-white font-bold text-sm shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
              Join Organization
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={null}>
      <AcceptInviteForm />
    </Suspense>
  );
}
