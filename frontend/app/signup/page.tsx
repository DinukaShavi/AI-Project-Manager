"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, RefreshCw, ShieldAlert } from "lucide-react";
import { organizationApi, ApiError } from "../../api";

export default function SignupPage() {
  const router = useRouter();
  const [organizationName, setOrganizationName] = useState("");
  const [adminFullName, setAdminFullName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await organizationApi.createOrganization({
        organization_name: organizationName,
        admin_full_name: adminFullName,
        admin_email: adminEmail,
        admin_password: adminPassword,
      });
      router.push("/login?created=1");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to create organization. Please try again.";
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
              <Building2 className="w-6 h-6 text-indigo-400" />
            </div>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">Create Your Organization</h1>
          <p className="text-xs text-slate-400 mt-1 text-center">
            Set up a new AI-TPM workspace for your team. You'll become the organization's founding admin.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4 shadow-xl"
        >
          <div>
            <label htmlFor="organizationName" className="text-xs font-semibold text-slate-300 block mb-1">
              Organization Name
            </label>
            <input
              id="organizationName"
              type="text"
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
              required
            />
          </div>

          <div>
            <label htmlFor="adminFullName" className="text-xs font-semibold text-slate-300 block mb-1">
              Your Full Name
            </label>
            <input
              id="adminFullName"
              type="text"
              value={adminFullName}
              onChange={(e) => setAdminFullName(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
              required
            />
          </div>

          <div>
            <label htmlFor="adminEmail" className="text-xs font-semibold text-slate-300 block mb-1">
              Your Email
            </label>
            <input
              id="adminEmail"
              type="email"
              autoComplete="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
              required
            />
          </div>

          <div>
            <label htmlFor="adminPassword" className="text-xs font-semibold text-slate-300 block mb-1">
              Password
            </label>
            <input
              id="adminPassword"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
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
            {isSubmitting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
            Create Organization
          </button>

          <p className="text-center text-xs text-slate-500">
            Already have an account?{" "}
            <a href="/login" className="text-indigo-400 hover:text-indigo-300 font-semibold">
              Sign in
            </a>
          </p>
        </form>
      </div>
    </div>
  );
}
