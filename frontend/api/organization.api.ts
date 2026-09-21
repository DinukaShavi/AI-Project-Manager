import { httpClient } from "./client";
import {
  OrganizationSettings,
  OrganizationMembersResponse,
  MemberDirectoryResponse,
  CreateOrganizationRequest,
  CreateOrganizationResponse,
  CreateInvitationRequest,
  InvitationResponse,
  InvitationsListResponse,
  AcceptInvitationRequest,
  ExternalIdentitiesResponse,
  User,
} from "./types";

export const organizationApi = {
  getSettings: async (): Promise<OrganizationSettings> => {
    return httpClient<OrganizationSettings>("/organizations/settings");
  },

  listMembers: async (): Promise<OrganizationMembersResponse> => {
    return httpClient<OrganizationMembersResponse>("/organizations/members");
  },

  // Self-service (Phase 64) -- any org member, for picking real teammates as meeting attendees.
  listMembersDirectory: async (): Promise<MemberDirectoryResponse> => {
    return httpClient<MemberDirectoryResponse>("/organizations/members/directory");
  },

  createOrganization: async (payload: CreateOrganizationRequest): Promise<CreateOrganizationResponse> => {
    return httpClient<CreateOrganizationResponse>("/organizations", {
      method: "POST",
      body: JSON.stringify(payload),
      skipAuth: true,
    });
  },

  createInvitation: async (payload: CreateInvitationRequest): Promise<InvitationResponse> => {
    return httpClient<InvitationResponse>("/organizations/invitations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  listInvitations: async (): Promise<InvitationsListResponse> => {
    return httpClient<InvitationsListResponse>("/organizations/invitations");
  },

  revokeInvitation: async (invitationId: string): Promise<{ invitation_id: string; status: string }> => {
    return httpClient<{ invitation_id: string; status: string }>(`/organizations/invitations/${invitationId}`, {
      method: "DELETE",
    });
  },

  acceptInvitation: async (token: string, payload: AcceptInvitationRequest): Promise<User> => {
    return httpClient<User>(`/organizations/invitations/${token}/accept`, {
      method: "POST",
      body: JSON.stringify(payload),
      skipAuth: true,
    });
  },

  listMyExternalIdentities: async (): Promise<ExternalIdentitiesResponse> => {
    return httpClient<ExternalIdentitiesResponse>("/organizations/external-identities/me");
  },

  unlinkExternalIdentity: async (identityId: string): Promise<{ identity_id: string; status: string }> => {
    return httpClient<{ identity_id: string; status: string }>(`/organizations/external-identities/${identityId}`, {
      method: "DELETE",
    });
  },
};
