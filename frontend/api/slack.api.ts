import { httpClient } from "./client";
import {
  SlackMessage,
  SlackUser,
  SlackActivityAnalysis,
  SlackChannelMappingRequest,
  SlackChannelMappingResponse,
  DiscoverSlackChannelsResponse,
  MappedSlackChannelsResponse,
} from "../types/slack";

export const slackApi = {
  mapChannelToProject: async (payload: SlackChannelMappingRequest): Promise<SlackChannelMappingResponse> => {
    return httpClient<SlackChannelMappingResponse>("/integrations/slack/mappings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  discoverChannels: async (): Promise<DiscoverSlackChannelsResponse> => {
    return httpClient<DiscoverSlackChannelsResponse>("/integrations/slack/discover-channels");
  },

  getMappedChannels: async (projectId: string): Promise<MappedSlackChannelsResponse> => {
    return httpClient<MappedSlackChannelsResponse>(`/integrations/slack/mapped-channels?project_id=${projectId}`);
  },

  // Real (Phase 63) -- organization is derived from the authenticated JWT server-side.
  // channelId must be one of the org's real mapped channels (see getMappedChannels).
  getMessages: async (channelId: string): Promise<{ messages: SlackMessage[] }> => {
    return httpClient<{ messages: SlackMessage[] }>(`/integrations/slack/messages?channel_id=${channelId}`);
  },

  getUsers: async (): Promise<{ users: SlackUser[] }> => {
    return httpClient<{ users: SlackUser[] }>("/integrations/slack/users");
  },

  // Real, channel-scoped (Phase 72) -- activity_by_hour/message_count computed from real
  // message timestamps; sentiment_score/top_discussed_topics from a real LLM call.
  getActivityAnalysis: async (channelId: string): Promise<SlackActivityAnalysis> => {
    return httpClient<SlackActivityAnalysis>(`/integrations/slack/activity?channel_id=${channelId}`);
  },
};
