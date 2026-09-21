// Real ContextSnapshot (Phase 68) -- a templated summary of a project's real recent activity
// and real knowledge graph bottlenecks, per GET/POST /context/projects/{id}/snapshot.

export interface ContextSnapshotActivityItem {
  source_type: string;
  title: string | null;
  created_at: string;
}

export interface ContextSnapshotBottleneck {
  urn: string;
  type: string;
  blocking_count: number;
  blocked_by_count: number;
  properties: Record<string, any>;
}

export interface ContextSnapshotStatePayload {
  summary: string;
  recent_activity: ContextSnapshotActivityItem[];
  bottlenecks: ContextSnapshotBottleneck[];
}

export interface ContextSnapshot {
  id: string;
  project_id: string;
  snapshot_timestamp: string;
  state_payload: ContextSnapshotStatePayload;
}
