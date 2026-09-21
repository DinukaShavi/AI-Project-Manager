// Real-time activity feed (Phase 66) -- one entry per real GitHub/Jira/Slack event as it's
// ingested and indexed (app/services/context_ingestion.py), pushed live over the existing
// org-scoped WebSocket channel.

export interface ActivityUpdate {
  source_type: string;
  provider: string;
  title: string;
  project_id: string;
  url: string | null;
  timestamp: string;
}
