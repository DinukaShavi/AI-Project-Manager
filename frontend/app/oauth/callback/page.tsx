"use client";

import React, { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";
import { integrationOAuthApi } from "../../../api/integrationOAuth.api";
import { ApiError } from "../../../api/client";

type CallbackState = "processing" | "success" | "error";

/**
 * Shared OAuth redirect target for every provider (GitHub, Slack, Jira, Google Calendar),
 * matching the single redirect_uri (http(s)://<host>/oauth/callback) the backend's
 * generate_oauth_authorize_url encodes into every provider's authorize URL. The provider
 * is recovered from the `state` param the backend embedded ("org_id=...&provider=...") and
 * echoed back unchanged by the provider, per standard OAuth2 behavior -- never trusted for
 * authorization, only used to route the callback to the right provider endpoint. The
 * actual token exchange happens entirely server-side; this page only forwards the
 * authorization code to it.
 */
export default function OAuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<CallbackState>("processing");
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const oauthState = searchParams.get("state") || "";
    const providerMatch = oauthState.match(/provider=([a-z_]+)/i);
    const resolvedProvider = providerMatch ? providerMatch[1] : null;
    const providerError = searchParams.get("error") || searchParams.get("error_description");

    setProvider(resolvedProvider);

    if (providerError) {
      setState("error");
      setMessage(`Authorization was denied: ${providerError}`);
      return;
    }
    if (!code || !resolvedProvider) {
      setState("error");
      setMessage("This callback is missing an authorization code or provider identifier.");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        await integrationOAuthApi.completeCallback(resolvedProvider, code);
        if (!cancelled) {
          setState("success");
          setTimeout(() => router.push("/integrations"), 1500);
        }
      } catch (err) {
        if (!cancelled) {
          setState("error");
          setMessage(err instanceof ApiError ? err.message : "Failed to complete the connection.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex items-center justify-center p-6">
      <div className="w-full max-w-sm p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl shadow-xl text-center space-y-4">
        {state === "processing" && (
          <>
            <RefreshCw className="w-8 h-8 mx-auto text-indigo-400 animate-spin" />
            <h1 className="text-lg font-bold text-white">
              Completing {provider ? provider.replace("_", " ") : ""} connection...
            </h1>
            <p className="text-xs text-slate-400">Please wait while we finish authorizing this integration.</p>
          </>
        )}

        {state === "success" && (
          <>
            <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400" />
            <h1 className="text-lg font-bold text-white">Connected successfully</h1>
            <p className="text-xs text-slate-400">Redirecting back to the Connection Center...</p>
          </>
        )}

        {state === "error" && (
          <>
            <ShieldAlert className="w-8 h-8 mx-auto text-rose-400" />
            <h1 className="text-lg font-bold text-white">Connection failed</h1>
            <p className="text-xs text-rose-300">{message}</p>
            <button
              onClick={() => router.push("/integrations")}
              className="mt-2 w-full py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white font-semibold text-xs border border-white/10 transition-all"
            >
              Return to Connection Center
            </button>
          </>
        )}
      </div>
    </div>
  );
}
