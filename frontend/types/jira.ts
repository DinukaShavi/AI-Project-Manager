// TypeScript Models for Jira Integration

export interface JiraProject {
  key: string;
  name: string;
}

export interface JiraIssue {
  id: string;
  key: string;
  summary: string;
  status: string;
  priority: string;
  assignee: string;
  // null (not 0) when the Story Points custom field couldn't be confidently resolved on this
  // Jira site -- Jira exposes it only as a per-instance custom field with no fixed id.
  story_points: number | null;
}

export interface JiraSprint {
  id: number;
  name: string;
  state: "active" | "future" | "closed" | string;
  start_date: string;
  end_date: string;
  completed_story_points: number | null;
  total_story_points: number | null;
}

export interface JiraTeamWorkload {
  assignee: string;
  assigned_issues: number;
  // null (not 0) when the Story Points field couldn't be resolved on this Jira site.
  total_story_points: number | null;
  // Real relative share of the project's total resolved points -- not an assumed capacity
  // baseline (nothing in this system tracks per-person sprint capacity). null when points
  // couldn't be resolved.
  percentage_of_team_points: number | null;
}

export interface JiraSprintVelocityHistory {
  sprint: string;
  committed: number;
  completed: number;
}

export interface JiraVelocityMetrics {
  organization_id: string;
  // null when no closed sprint has a resolved Story Points value yet.
  average_velocity: number | null;
  sprint_velocity_history: JiraSprintVelocityHistory[];
}
