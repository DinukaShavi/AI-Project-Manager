// TypeScript Models for Slack Integration

export interface SlackChannel {
  id: string;
  name: string;
  is_private: boolean;
  members_count: number;
  topic?: string;
}

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
  daily_message_volume: number;
  sentiment_score: number;
  top_discussed_topics: string[];
  activity_by_hour: SlackActivityByHour[];
}
