# API Contract Specification: AI-Powered TPM

This document outlines the API specifications for the AI-Powered Technical Project Manager (AI-TPM). 

To comply with project specifications, **no execution code is generated**. All payloads and schemas are documented using JSON structures and descriptive specifications.

---

## 1. Global API Standards

### API Versioning Strategy
* **URL Versioning**: All API paths are prefixed with the active major version (e.g., `/api/v1/`).
* **Deprecation Policy**: When a breaking change is introduced, a new major version route is deployed. The legacy route is maintained for a 6-month deprecation period, returning a `Warning: 299 - "Deprecation Warning"` header in responses.

### Error Response Standard (RFC 7807 Problem Details)
All error payloads return a `Content-Type: application/problem+json` response body matching the RFC 7807 standard:

```json
{
  "type": "https://api.ai-tpm.com/v1/errors/validation-failed",
  "title": "Validation Failed",
  "status": 420,
  "detail": "The parameter 'sprint_id' must be a valid UUID v4.",
  "instance": "/api/v1/projects/123/sprints",
  "invalid_params": [
    {
      "name": "sprint_id",
      "reason": "Not a valid UUID v4 format"
    }
  ]
}
```

### Common Request Headers
* `Authorization`: `Bearer <JWT_TOKEN>` (Required for authenticated endpoints).
* `X-Tenant-ID`: `UUID` (Identifies the target organization database scope).
* `Idempotency-Key`: `UUID` (Optional for reads; required for writes to prevent duplicate operations).

---

## 2. API Endpoint Catalog

### 1. Authentication APIs

#### A. Login (Local Credentials)
* **Method & URL**: `POST /api/v1/auth/login`
* **Authorization**: None (Public).
* **Rate Limit**: 10 requests per minute per IP.
* **Request Schema**:
  ```json
  {
    "email": "user@organization.com",
    "password": "SecurePassword123!"
  }
  ```
* **Response Schema (200 OK)**:
  ```json
  {
    "access_token": "jwt-access-token-string",
    "refresh_token": "jwt-refresh-token-string",
    "token_type": "Bearer",
    "expires_in": 3600
  }
  ```
* **Error Codes**: `401 Unauthorized` (Invalid credentials).

#### B. Logout
* **Method & URL**: `POST /api/v1/auth/logout`
* **Authorization**: Logged-in user token.
* **Rate Limit**: 60 requests per minute.
* **Request Schema**: None.
* **Response Schema (204 No Content)**: Empty body.

#### C. Refresh Token
* **Method & URL**: `POST /api/v1/auth/refresh`
* **Authorization**: Refresh token header.
* **Request Schema**:
  ```json
  {
    "refresh_token": "jwt-refresh-token-string"
  }
  ```
* **Response Schema (200 OK)**:
  ```json
  {
    "access_token": "new-jwt-access-token-string",
    "refresh_token": "new-jwt-refresh-token-string",
    "expires_in": 3600
  }
  ```

#### D. Get Current User Profile
* **Method & URL**: `GET /api/v1/auth/me`
* **Authorization**: Bearer Token.
* **Response Schema (200 OK)**:
  ```json
  {
    "id": "uuid-v4",
    "email": "user@org.com",
    "full_name": "Developer Name",
    "organization_id": "uuid-v4",
    "role": "Developer"
  }
  ```

---

## 2. Workspace APIs

#### A. List Workspaces
* **Method & URL**: `GET /api/v1/workspaces`
* **Pagination**: Limit/Offset query parameters (`?limit=20&offset=0`).
* **Filtering**: `?name=development`
* **Sorting**: `?sort_by=created_at&sort_direction=desc`
* **Response Schema (200 OK)**:
  ```json
  {
    "workspaces": [
      {
        "id": "uuid-v4",
        "name": "Engineering Workspace",
        "created_at": "2026-07-17T21:30:00Z"
      }
    ],
    "pagination": { "total": 1, "limit": 20, "offset": 0 }
  }
  ```

#### B. Create Workspace
* **Method & URL**: `POST /api/v1/workspaces`
* **Idempotency**: Required via `Idempotency-Key` header.
* **Request Schema**:
  ```json
  {
    "name": "Marketing Operations"
  }
  ```
* **Response Schema (201 Created)**: Returns the created workspace object.

---

## 3. Organization APIs

#### A. Get Organization Settings
* **Method & URL**: `GET /api/v1/organizations/settings`
* **Authorization**: `OrgAdmin` role required.
* **Response Schema (200 OK)**:
  ```json
  {
    "organization_id": "uuid-v4",
    "name": "Acme Corp",
    "domain": "acme.com",
    "allowed_email_domains": ["acme.com"],
    "created_at": "2026-07-17T21:30:00Z"
  }
  ```

---

## 4. GitHub Integration APIs

#### A. Link Repository
* **Method & URL**: `POST /api/v1/integrations/github/repositories`
* **Request Schema**:
  ```json
  {
    "project_id": "uuid-v4",
    "external_repo_id": "987654321",
    "name": "backend-core",
    "clone_url": "https://github.com/acme/backend-core.git"
  }
  ```
* **Response Schema (201 Created)**: Link confirmation object.

---

## 5. Jira Integration APIs

#### A. Import Jira Projects List
* **Method & URL**: `GET /api/v1/integrations/jira/projects`
* **Response Schema (200 OK)**:
  ```json
  {
    "projects": [
      { "key": "PROJ", "name": "Core Service Development" }
    ]
  }
  ```

---

## 6. Slack Integration APIs

#### A. Map Project to Slack Channel
* **Method & URL**: `POST /api/v1/integrations/slack/mappings`
* **Request Schema**:
  ```json
  {
    "project_id": "uuid-v4",
    "slack_channel_id": "C12345678"
  }
  ```
* **Response Schema (200 OK)**: Status confirmation payload.

---

## 7. Google Calendar Integration APIs

#### A. Sync Calendar Events Range
* **Method & URL**: `POST /api/v1/integrations/calendar/sync`
* **Request Schema**:
  ```json
  {
    "project_id": "uuid-v4",
    "start_date": "2026-07-17T00:00:00Z",
    "end_date": "2026-07-24T00:00:00Z"
  }
  ```
* **Response Schema (202 Accepted)**: Sync task token details.

---

## 8. Context Engine APIs

#### A. Get Current Project Unified State Graph
* **Method & URL**: `GET /api/v1/context/projects/{id}/graph`
* **Response Schema (200 OK)**:
  ```json
  {
    "nodes": [
      { "urn": "urn:jira:issue:PROJ-101", "type": "issue", "status": "blocked" }
    ],
    "edges": [
      { "source": "urn:github:pr:404", "target": "urn:jira:issue:PROJ-101", "relation": "blocks" }
    ]
  }
  ```

---

## 9. Event Bus APIs

#### A. Replay Events Log
* **Method & URL**: `POST /api/v1/events/replay`
* **Authorization**: `OrgAdmin` role required.
* **Request Schema**:
  ```json
  {
    "routing_key_pattern": "org123.*.github.*",
    "start_timestamp": "2026-07-17T00:00:00Z"
  }
  ```
* **Response Schema (202 Accepted)**: Replay task tracking details.

---

## 10. Workflow APIs

#### A. Deploy Workflow DAG
* **Method & URL**: `POST /api/v1/workflows`
* **Request Schema**:
  ```json
  {
    "name": "Automated Pull Request Code Quality Review",
    "trigger_event": "org.project.github.pr_opened",
    "dag_definition": {
      "start_at": "LintCheck",
      "steps": {
        "LintCheck": { "type": "tool_call", "tool": "run_linter", "next": "Complete" }
      }
    }
  }
  ```
* **Response Schema (201 Created)**: Workflow registration payload.

---

## 11. Agent APIs

#### A. Query Agent Execution Logs
* **Method & URL**: `GET /api/v1/agents/executions/{id}`
* **Response Schema (200 OK)**:
  ```json
  {
    "execution_id": "uuid-v4",
    "agent_name": "PlanningAgent",
    "status": "completed",
    "thought_log": "Analyzing sprint backlog story points. Identified 2 issues on critical path.",
    "created_at": "2026-07-17T21:40:00Z"
  }
  ```

---

## 12. Recommendation APIs

#### A. Fetch Active Team Suggestions
* **Method & URL**: `GET /api/v1/recommendations`
* **Filtering**: `?status=active&type=overload`
* **Response Schema (200 OK)**:
  ```json
  {
    "recommendations": [
      {
        "id": "uuid-v4",
        "title": "Developer Overload Warning",
        "description": "User John Doe is assigned 32 story points in Sprint 25 (historical average: 18).",
        "score": 0.85,
        "created_at": "2026-07-17T21:45:00Z"
      }
    ]
  }
  ```

---

## 13. Analytics APIs

#### A. Fetch Sprint Metrics
* **Method & URL**: `GET /api/v1/analytics/projects/{id}/sprints`
* **Response Schema (200 OK)**:
  ```json
  {
    "metrics": {
      "sprint_velocity": 24.5,
      "lead_time_days": 12.4,
      "cycle_time_days": 4.2,
      "active_blockers_count": 2
    }
  }
  ```

---

## 14. Memory APIs

#### A. Query Vector Index
* **Method & URL**: `POST /api/v1/memory/search`
* **Request Schema**:
  ```json
  {
    "project_id": "uuid-v4",
    "query": "Architecture decisions regarding outbox database transactions",
    "limit": 3
  }
  ```
* **Response Schema (200 OK)**:
  ```json
  {
    "results": [
      {
        "content": "ADR 002: Implemented Transactional Outbox pattern to guarantee event delivery.",
        "similarity": 0.92
      }
    ]
  }
  ```

---

## 15. Tool Registry APIs

#### A. List Registered Agent Tools
* **Method & URL**: `GET /api/v1/tools`
* **Response Schema (200 OK)**:
  ```json
  {
    "tools": [
      {
        "name": "create_jira_issue",
        "description": "Creates a ticket in JIRA",
        "args_schema": { "project_key": "string", "summary": "string" },
        "requires_approval": true
      }
    ]
  }
  ```

---

## 16. Notification APIs

#### A. Mark Notifications as Read
* **Method & URL**: `PUT /api/v1/notifications/read`
* **Request Schema**:
  ```json
  {
    "notification_ids": ["uuid-v4"]
  }
  ```
* **Response Schema (200 OK)**: Operations confirmation object.

---

## 17. WebSocket API

* **Protocol**: RFC 6455 WebSocket.
* **Authentication**: Handled via JWT token query parameter: `ws://api.domain/v1/ws?token=<JWT_TOKEN>`.
* **Path**: `/api/v1/ws`

---

## 3. WebSocket Message Contracts

All WebSocket communication uses structured JSON envelopes:

```
  [Client App] ──(Subscribe to Project)──► [WS Server Instance]
                                                    │
                                                    ▼ (Listen on Redis Channel)
  [Client App] ◄──(Dynamic Event Feed) ◄────────────┘
```

### Client Request Envelope
* **Subscribe to project updates**:
  ```json
  {
    "action": "subscribe",
    "channel": "project:123:context",
    "correlation_id": "client-msg-101"
  }
  ```

### Server Response Envelopes
* **Connection Acknowledged**:
  ```json
  {
    "event": "connected",
    "status": "success",
    "details": { "user_id": "uuid-v4" }
  }
  ```
* **Real-Time Data Feed Update**:
  ```json
  {
    "event": "channel_update",
    "channel": "project:123:context",
    "payload": {
      "urn": "urn:jira:issue:PROJ-101",
      "type": "issue",
      "status": "Done"
    }
  }
  ```

---

## 4. Ingestion Webhook Event Schemas

Below are the JSON payloads expected from third-party webhook integrations.

### GitHub: `pull_request.opened`
```json
{
  "action": "opened",
  "number": 404,
  "pull_request": {
    "id": 98765432,
    "title": "Fix validation bug in auth middleware",
    "state": "open",
    "user": { "id": 112233, "login": "dev-user" },
    "head": { "ref": "feature/auth-validation", "sha": "sha-value" },
    "base": { "ref": "main" }
  },
  "repository": { "id": 87654321, "name": "backend-core" }
}
```

### Jira: `issue_updated`
```json
{
  "timestamp": 1784382000000,
  "webhookEvent": "jira:issue_updated",
  "issue_event_type_name": "issue_generic",
  "issue": {
    "id": "10001",
    "key": "PROJ-101",
    "fields": {
      "summary": "Implement context parsing middleware",
      "status": { "name": "In Progress" },
      "priority": { "name": "High" },
      "updated": "2026-07-17T21:55:00.000+0000"
    }
  }
}
```

---

## 5. OpenAPI Folder Organization

To keep the repository clean and maintainable, OpenAPI files are organized in a modular structure:

```
openapi/
├── openapi.yaml                 # Core Entrypoint (references components)
├── paths/                       # API endpoint paths
│   ├── auth.yaml
│   ├── workspaces.yaml
│   ├── integrations/
│   │   ├── github.yaml
│   │   ├── jira.yaml
│   │   └── slack.yaml
│   └── workflows.yaml
└── components/                  # Shared database objects
    ├── schemas/
    │   ├── user.yaml
    │   ├── project.yaml
    │   └── error.yaml
    └── security.yaml            # Authentication protocols
```
