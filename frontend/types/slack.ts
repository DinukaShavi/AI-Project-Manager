// TypeScript Models for Slack Integration

export interface SlackMessage {
  ts: string;
  user: string;
  user_name: string;
  text: string;
  timestamp: string;
}

export interface SlackUser {
  id: string;
  name: string;
  real_name: string;
  role: string;
  is_bot: boolean;
  status_text?: string;
}

export interface SlackActivityByHour {
  hour: string;
  messages: number;
}

export interface SlackActivityAnalysis {
  organization_id: string;
  channel_id: string;
  message_count: number;
  // Real LLM-derived sentiment (0.0 very negative -- 1.0 very positive), or null when there's
  // nothing to analyze or the LLM call isn't configured/fails -- never a fabricated number.
  sentiment_score: number | null;
  top_discussed_topics: string[];
  activity_by_hour: SlackActivityByHour[];
}

export interface SlackChannelMappingRequest {
  project_id: string;
  slack_channel_id: string;
}

export interface SlackChannelMappingResponse {
  id: string;
  project_id: string;
  slack_channel_id: string;
  status: string;
}

// Real channel discovery/mapping
export interface DiscoveredSlackChannel {
  slack_channel_id: string;
  name: string;
  is_private: boolean;
  num_members: number;
  topic: string;
}

export interface DiscoverSlackChannelsResponse {
  total_channels: number;
  channels: DiscoveredSlackChannel[];
}

export interface MappedSlackChannel {
  id: string;
  slack_channel_id: string;
}

export interface MappedSlackChannelsResponse {
  project_id: string;
  total_channels: number;
  channels: MappedSlackChannel[];
}
