// TypeScript Models for Jira Integration

export interface JiraProject {
  id: string;
  key: string;
  name: string;
  project_type: string;
  lead: string;
  total_issues: number;
}

export interface JiraIssue {
  id: string;
  key: string;
  summary: string;
  status: string;
  priority: string;
  assignee: string;
  story_points: number;
}

export interface JiraSprint {
  id: number;
  name: string;
  state: "active" | "future" | "closed" | string;
  start_date: string;
  end_date: string;
  completed_story_points: number;
  total_story_points: number;
}

export interface JiraTeamWorkload {
  assignee: string;
  assigned_issues: number;
  total_story_points: number;
  capacity_percentage: number;
}

export interface JiraSprintVelocityHistory {
  sprint: string;
  committed: number;
  completed: number;
}

export interface JiraVelocityMetrics {
  organization_id: string;
  average_velocity: number;
  sprint_velocity_history: JiraSprintVelocityHistory[];
}
