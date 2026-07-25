import { httpClient } from "./client";
import { SlackChannel, SlackMessage, SlackUser, SlackActivityAnalysis } from "../types/slack";

export const slackApi = {
  getChannels: async (orgId: string): Promise<{ channels: SlackChannel[] }> => {
    return httpClient<{ channels: SlackChannel[] }>(`/integrations/slack/channels?organization_id=${orgId}`);
  },

  getMessages: async (orgId: string, channelId: string = "C01ABCDEF01"): Promise<{ messages: SlackMessage[] }> => {
    return httpClient<{ messages: SlackMessage[] }>(`/integrations/slack/messages?organization_id=${orgId}&channel_id=${channelId}`);
  },

  getUsers: async (orgId: string): Promise<{ users: SlackUser[] }> => {
    return httpClient<{ users: SlackUser[] }>(`/integrations/slack/users?organization_id=${orgId}`);
  },

  getActivityAnalysis: async (orgId: string): Promise<SlackActivityAnalysis> => {
    return httpClient<SlackActivityAnalysis>(`/integrations/slack/activity?organization_id=${orgId}`);
  },
};
