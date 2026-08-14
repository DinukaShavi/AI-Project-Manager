"use client";

import React, { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { organizationApi, projectApi, authApi, ApiError } from "../../api";
import { OrganizationSettings, OrganizationMember, Workspace, Invitation, ExternalIdentity } from "../../api/types";
import { useAuth } from "../../hooks/use-auth";
import { Settings, Building2, Folder, Users, ShieldAlert, RefreshCw, Send, Link2, Copy, X, Unlink } from "lucide-react";

const ASSIGNABLE_ROLES = ["SuperAdmin", "OrgAdmin", "ProjectManager", "Developer", "Viewer"];

const IDENTITY_PROVIDERS: { key: string; label: string }[] = [
  { key: "jira", label: "Jira" },
  { key: "github", label: "GitHub" },
  { key: "slack", label: "Slack" },
  { key: "google_calendar", label: "Google Calendar" },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const [org, setOrg] = useState<OrganizationSettings | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [externalIdentities, setExternalIdentities] = useState<ExternalIdentity[]>([]);
  const [unlinkingId, setUnlinkingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [roleChangeTarget, setRoleChangeTarget] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Developer");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  // Self-service, not admin-gated -- every user can see and manage their own connected
  // external accounts regardless of org role. Fetched independently of the admin-only
  // settings below so it still loads for non-admins.
  const fetchIdentities = async () => {
    try {
      const res = await organizationApi.listMyExternalIdentities();
      setExternalIdentities(res.identities);
    } catch {
      setExternalIdentities([]);
    }
  };

  const handleUnlinkIdentity = async (identityId: string) => {
    setUnlinkingId(identityId);
    try {
      await organizationApi.unlinkExternalIdentity(identityId);
      await fetchIdentities();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to unlink account.");
    } finally {
      setUnlinkingId(null);
    }
  };

  useEffect(() => {
    fetchIdentities();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      const [orgData, membersData, invitationsData] = await Promise.all([
        organizationApi.getSettings(),
        organizationApi.listMembers(),
        organizationApi.listInvitations(),
      ]);
      setOrg(orgData);
      setMembers(membersData.members);
      setInvitations(invitationsData.invitations);

      if (user?.organization_id) {
        try {
          const wsData = await projectApi.getWorkspaces(user.organization_id);
          setWorkspaces(wsData.workspaces);
        } catch {
          setWorkspaces([]);
        }
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to load organization settings.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    setInviteError(null);
    setInviteLink(null);
    setLinkCopied(false);
    try {
      const res = await organizationApi.createInvitation({ email: inviteEmail, role_name: inviteRole });
      const link = `${window.location.origin}/accept-invite?token=${res.token}`;
      setInviteLink(link);
      setInviteEmail("");
      await fetchAll();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Failed to create invitation.");
    } finally {
      setInviting(false);
    }
  };

  const handleCopyLink = async () => {
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setLinkCopied(true);
    } catch {
      // Clipboard access can fail (permissions/insecure context) -- the link remains
      // visible and manually selectable either way.
    }
  };

  const handleRevokeInvite = async (invitationId: string) => {
    setRevokingId(invitationId);
    try {
      await organizationApi.revokeInvitation(invitationId);
      await fetchAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke invitation.");
    } finally {
      setRevokingId(null);
    }
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.organization_id]);

  const handleGrant = async (memberId: string, roleName: string) => {
    setRoleChangeTarget(memberId);
    try {
      await authApi.assignRole(memberId, { role_name: roleName });
      await fetchAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to grant role.");
    } finally {
      setRoleChangeTarget(null);
    }
  };

  const handleRevoke = async (memberId: string, roleName: string) => {
    setRoleChangeTarget(memberId);
    try {
      await authApi.revokeRole(memberId, roleName);
      await fetchAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke role.");
    } finally {
      setRoleChangeTarget(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white">
      <Navbar />

      <div className="flex pt-16">
        <Sidebar activeTab="settings" />

        <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Settings className="w-8 h-8 text-indigo-400" /> Settings Console
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                Organization details, connected workspaces, and team member roles (OrgAdmin / SuperAdmin only).
              </p>
            </div>
            <button
              onClick={fetchAll}
              className="px-4 py-2.5 rounded-xl bg-indigo-600/20 text-indigo-300 text-sm font-semibold border border-indigo-500/30 flex items-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>

          {forbidden && (
            <div role="alert" className="flex items-center gap-3 px-4 py-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <span>Only OrgAdmin or SuperAdmin roles may view organization settings. Ask an administrator to grant you access.</span>
            </div>
          )}

          {error && !forbidden && (
            <div role="alert" className="flex items-center gap-3 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Connected Accounts -- self-service, every user manages their own regardless of
              org role. Only Slack currently auto-links on OAuth connect (real, not fabricated);
              the other three show an honest "Not linked yet" until their provider identity
              extraction ships. */}
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Link2 className="w-5 h-5 text-indigo-400" /> Connected Accounts
            </h2>
            <p className="text-xs text-slate-400">
              Your own identity on each connected provider. Linking currently happens automatically when you connect
              Slack from the Integrations page.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {IDENTITY_PROVIDERS.map(({ key, label }) => {
                const identity = externalIdentities.find((i) => i.provider === key);
                return (
                  <div key={key} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{label}</p>
                      {identity ? (
                        <p className="text-xs text-emerald-400 mt-1">
                          Connected · {identity.external_display_name || identity.external_account_id}
                        </p>
                      ) : (
                        <p className="text-xs text-slate-500 mt-1">Not linked yet</p>
                      )}
                    </div>
                    {identity && (
                      <button
                        onClick={() => handleUnlinkIdentity(identity.id)}
                        disabled={unlinkingId === identity.id}
                        className="p-2 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 disabled:opacity-50 shrink-0"
                        aria-label={`Unlink ${label}`}
                      >
                        <Unlink className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {!forbidden && (
            <>
              {/* Org info */}
              <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-indigo-400" /> Organization Info
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Name</span>
                    <span className="text-white font-semibold">{org?.name || "—"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Domain</span>
                    <span className="text-white font-semibold">{org?.domain || "—"}</span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Allowed Email Domains</span>
                    <span className="text-white font-semibold">
                      {org?.allowed_email_domains?.length ? org.allowed_email_domains.join(", ") : "Not restricted"}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 block mb-1">Created</span>
                    <span className="text-white font-semibold">{org?.created_at ? new Date(org.created_at).toLocaleDateString() : "—"}</span>
                  </div>
                </div>
              </div>

              {/* Workspaces */}
              <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Folder className="w-5 h-5 text-indigo-400" /> Connected Workspaces
                </h2>
                {workspaces.length === 0 ? (
                  <p className="text-sm text-slate-500">No workspaces found.</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {workspaces.map((ws) => (
                      <div key={ws.workspace_id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                        <p className="text-sm font-semibold text-white">{ws.name}</p>
                        {ws.description && <p className="text-xs text-slate-400 mt-1">{ws.description}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Invite Team Members */}
              <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl space-y-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Send className="w-5 h-5 text-indigo-400" /> Invite Team Members
                </h2>
                <p className="text-xs text-slate-400">
                  Generates a real, single-use invite link (valid 7 days). There's no email delivery yet -- copy the
                  link and send it to your teammate yourself.
                </p>

                <form onSubmit={handleInvite} className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="email"
                    placeholder="teammate@company.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                    className="flex-1 px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="px-3 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    {ASSIGNABLE_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <button
                    type="submit"
                    disabled={inviting}
                    className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm shadow-lg shadow-indigo-500/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {inviting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Invite
                  </button>
                </form>

                {inviteError && (
                  <div className="px-4 py-2 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                    {inviteError}
                  </div>
                )}

                {inviteLink && (
                  <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2">
                    <Link2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <code className="flex-1 text-xs text-emerald-300 truncate">{inviteLink}</code>
                    <button
                      onClick={handleCopyLink}
                      className="px-2.5 py-1.5 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-xs font-semibold flex items-center gap-1 shrink-0"
                    >
                      <Copy className="w-3.5 h-3.5" /> {linkCopied ? "Copied" : "Copy"}
                    </button>
                  </div>
                )}

                {invitations.filter((i) => i.status === "pending").length > 0 && (
                  <div className="pt-2 space-y-2">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Pending Invitations</span>
                    {invitations
                      .filter((i) => i.status === "pending")
                      .map((inv) => (
                        <div key={inv.id} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-slate-900/60 border border-slate-800">
                          <div>
                            <p className="text-sm text-white">{inv.email}</p>
                            <p className="text-xs text-slate-500">
                              {inv.role} · expires {new Date(inv.expires_at).toLocaleDateString()}
                            </p>
                          </div>
                          <button
                            onClick={() => handleRevokeInvite(inv.id)}
                            disabled={revokingId === inv.id}
                            aria-label={`Revoke invitation for ${inv.email}`}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-300 hover:bg-rose-500/10 disabled:opacity-50"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                  </div>
                )}
              </div>

              {/* Team roles table */}
              <div className="rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl overflow-hidden">
                <div className="p-6 pb-0">
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Users className="w-5 h-5 text-indigo-400" /> Team Member Roles
                  </h2>
                </div>
                <div className="overflow-x-auto mt-4">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-800 text-left text-xs text-slate-400 uppercase tracking-wider">
                        <th className="px-6 py-3">Member</th>
                        <th className="px-6 py-3">Roles</th>
                        <th className="px-6 py-3">Grant Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {members.map((m) => (
                        <tr key={m.id} className="border-b border-slate-800/60 hover:bg-slate-900/40">
                          <td className="px-6 py-3">
                            <p className="text-white font-medium">{m.full_name}</p>
                            <p className="text-xs text-slate-500">{m.email}</p>
                          </td>
                          <td className="px-6 py-3">
                            <div className="flex flex-wrap gap-1.5">
                              {m.roles.length === 0 && <span className="text-xs text-slate-500">No roles</span>}
                              {m.roles.map((r) => (
                                <span
                                  key={r}
                                  className="group inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs"
                                >
                                  {r}
                                  <button
                                    onClick={() => handleRevoke(m.id, r)}
                                    disabled={roleChangeTarget === m.id}
                                    aria-label={`Revoke ${r} from ${m.email}`}
                                    className="opacity-60 hover:opacity-100 hover:text-rose-300"
                                  >
                                    ×
                                  </button>
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="px-6 py-3">
                            <select
                              disabled={roleChangeTarget === m.id}
                              value=""
                              onChange={(e) => e.target.value && handleGrant(m.id, e.target.value)}
                              className="px-2 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-xs text-white focus:outline-none focus:border-indigo-500"
                            >
                              <option value="" disabled>
                                Grant a role…
                              </option>
                              {ASSIGNABLE_ROLES.filter((r) => !m.roles.includes(r)).map((r) => (
                                <option key={r} value={r}>
                                  {r}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
