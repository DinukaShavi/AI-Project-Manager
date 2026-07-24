# 🧭 AI-TPM: Complete User Interaction Guide

## 🖥️ What's Running Right Now

| URL | What it is |
| :--- | :--- |
| `http://localhost:3000` | **Frontend Dashboard** — Your main UI |
| `http://localhost:8000/docs` | **Swagger API Explorer** — Test every API endpoint manually |
| `http://localhost:8000/health` | **Backend Health** — Confirm backend is alive |

---

## 🗂️ Dashboard Layout

```
┌─────────────────────────────────────────────────────────┐
│  NAVBAR ─ AI-TPM logo │ Status │ [Trigger AI Agent] btn │
├──────────┬──────────────────────────────────────────────┤
│          │  Sprint Metric Cards (4 KPIs)                │
│ SIDEBAR  │  Agent Persona Cards (4 quick-launch tiles)  │
│          │  Sprint Kanban Board (Todo/In Prog/Review/Done│
│ Overview │  Context Vector Search Inspector             │
│ Tasks    │                                              │
│ Workflows│                                              │
│ Context  │                                              │
│ Integr.  │                                              │
└──────────┴──────────────────────────────────────────────┘
```

---

## ✅ Things You Can Do RIGHT NOW (No Setup Required)

### 1. 📊 View Sprint KPI Metrics

The 4 metric cards at the top show:
- **Sprint Velocity** — Completed vs total story points with progress bar
- **Completion Rate %** — Tasks done / total tasks
- **Delivery Risk Index** — `0.0` (safe) → `1.0` (critical)
- **AI Agents Active** — Shows 4 active personas, 6 tools

> These load from demo data. Once you have real projects in the database, they will update automatically.

---

### 2. 🤖 Run an AI Agent (Most Important Feature)

**Step 1:** Click **"Run Agent Audit"** button (top-right of the dashboard header)  
**OR** click any of the 4 Agent Persona tiles below the metrics.

**Step 2:** In the modal that opens:
- **Select Agent Persona** from the dropdown:
  - `TechnicalPMAgent` — Analyzes sprint velocity, assigns story points
  - `CodeAnalystAgent` — Reviews PR diffs and code quality
  - `RiskManagerAgent` — Detects bottlenecks and delivery risks
  - `ArchitectureReviewerAgent` — Audits system design and APIs
  - `[Workflow DAG] Sprint Review` — Chains 3 agents sequentially
  - `[Workflow DAG] Architecture Audit` — Chains 2 agents sequentially

- **Edit the Task Prompt** (the text area) — describe what you want the agent to analyze

**Step 3:** Click **"Execute Persona"**

**What happens:**
1. Request is sent to `POST /api/v1/agents/execute`
2. Agent runs synthetic reasoning (no OpenAI key needed locally)
3. JSON output appears in the panel below the button

> [!TIP]
> Try this prompt in TechnicalPMAgent: `"Review all in-progress tasks. Identify blockers and recommend priority changes for Sprint 14."`

---

### 3. 📋 Manage Tasks on the Kanban Board

**Add a new task:**
1. Type a task title in the `"New task title..."` input
2. Select priority: Low / Medium / High / Critical
3. Click **"+ Add Task"** → task appears in the **Todo** column instantly

**Move tasks across columns:**
- Click **`→`** on a card to advance it: `Todo → In Progress → Review → Done`
- Click **`←`** on a card to move it back

**Each task card shows:**
- Jira issue key (`TPM-XXX`)
- Priority badge (color-coded)
- Task title
- Story points

---

### 4. 🔍 Search the Context Vector Engine

Located at the bottom of the **Overview** tab (or click **Context** in the sidebar).

1. Type a natural language query in the search box  
   Examples:
   - `"outbox pattern event bus"`
   - `"vector database migration"`
   - `"multi-agent DAG workflow"`
2. Click **"Search Vectors"**
3. Results show **Cosine Similarity scores** — higher = more semantically relevant

> [!NOTE]
> If no documents have been indexed yet, the system returns local fallback demo results. To index real documents, use `POST /api/v1/context/index` in Swagger (`http://localhost:8000/docs`).

---

### 5. 🧪 Use Swagger to Test All APIs Manually

Go to **`http://localhost:8000/docs`** to see every single API endpoint.

**Recommended things to try:**

**Create a real project:**
```
POST /api/v1/projects
Body: {
  "workspace_id": "00000000-0000-0000-0000-000000000001",
  "name": "My First Project",
  "description": "Testing the AI-TPM system"
}
```

**Run an agent via API:**
```
POST /api/v1/agents/execute
Body: {
  "agent_type": "TechnicalPMAgent",
  "task": "Analyze sprint health",
  "organization_id": "00000000-0000-0000-0000-000000000001"
}
```

**Index a document into the vector engine:**
```
POST /api/v1/context/index
Body: {
  "organization_id": "00000000-0000-0000-0000-000000000001",
  "document_id": "doc-001",
  "content": "This is my technical documentation about the system design.",
  "source": "confluence"
}
```

---

## 🔌 Connecting External Integrations

> [!IMPORTANT]
> Integrations (GitHub, Slack, Jira, Google Calendar) require you to register **webhook URLs** in each platform's developer settings. The backend already handles all the HMAC signature verification and event normalization — you just need to point the platforms to your server.

---

### 🐙 GitHub Integration

**What it does:** Receives GitHub events (PR opened, PR merged, issue created, push) → stores them as outbox events → AI agents can analyze them.

**Setup Steps:**

1. Go to your GitHub repo → **Settings → Webhooks → Add webhook**
2. Set **Payload URL**: `http://YOUR_SERVER_IP:8000/api/v1/integrations/github/webhook`
3. Set **Content type**: `application/json`
4. Set **Secret**: Add a secret string and put it in your `.env`:
   ```env
   GITHUB_WEBHOOK_SECRET=your_secret_here
   ```
5. Select events to send:
   - ✅ Pull requests
   - ✅ Pushes
   - ✅ Issues
6. Click **Add webhook**

**Test it locally:** Use [ngrok](https://ngrok.com/) to expose port 8000 publicly:
```powershell
ngrok http 8000
```
Then use the ngrok URL as your webhook URL in GitHub.

---

### 💬 Slack Integration

**What it does:** Receives Slack events (messages, channel activity) → AI agents can post summaries back to channels.

**Setup Steps:**

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From Scratch**
2. Give it a name and select your workspace
3. Go to **Event Subscriptions → Enable Events**
4. Set **Request URL**: `http://YOUR_NGROK_URL/api/v1/integrations/slack/webhook`
   - Slack will immediately send a `url_verification` challenge → the backend automatically responds ✅
5. Under **Subscribe to Bot Events**, add:
   - `message.channels`
   - `app_mention`
6. Go to **OAuth & Permissions → Install to Workspace**
7. Copy **Bot User OAuth Token** → add to `.env`:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-token-here
   SLACK_SIGNING_SECRET=your_signing_secret_here
   ```

---

### 📋 Jira Integration

**What it does:** Receives Jira events (issue created, status changed, sprint started) → syncs task states.

**Setup Steps:**

1. Go to your Jira project → **Project Settings → Webhooks**
2. Click **Create a webhook**
3. Set **URL**: `http://YOUR_NGROK_URL/api/v1/integrations/jira/webhook`
4. Select events:
   - ✅ Issue: created, updated, deleted
   - ✅ Sprint: started, closed
5. Click **Save**

Add to `.env`:
```env
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_api_token
```

---

### 📅 Google Calendar Integration

**What it does:** Receives calendar event notifications (meetings, deadlines) → AI agents can correlate sprint deadlines with team availability.

**Setup Steps:**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **Google Calendar API**
3. Create **OAuth 2.0 credentials**
4. Use the Calendar API to register a **Push Notification channel**:
   ```
   POST https://www.googleapis.com/calendar/v3/calendars/{calendarId}/events/watch
   Body: {
     "id": "unique-channel-id",
     "type": "web_hook",
     "address": "http://YOUR_NGROK_URL/api/v1/integrations/google/webhook"
   }
   ```

Add to `.env`:
```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

---

## 🐛 Common Issues & Fixes

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| Dashboard shows demo data only | No real org/project in DB | Use Swagger to `POST /api/v1/projects` to create one |
| Agent execution shows "local fallback" | No `OPENAI_API_KEY` set | Set `OPENAI_API_KEY=sk-...` in `.env` — OR ignore, local synthetic reasoning still works |
| Vector search returns demo results | No documents indexed | Use `POST /api/v1/context/index` in Swagger to index a document |
| Webhook not triggering | Webhook URL is `localhost` | Use `ngrok http 8000` to get a public URL for GitHub/Slack |
| `429 Too Many Requests` | Rate limiter triggered | Wait 60 seconds — rate limit is 120 req/min per IP |
| Slack `url_verification` fails | Wrong URL or server offline | Make sure backend is running + ngrok tunnel is active |
| `Integration mapper error` in logs | Fixed ✅ | Already patched — `import app.db.base` added to worker |

---

## 🔑 `.env` Variables Reference

```env
# Database
DATABASE_URL=postgresql://postgres:12345@localhost:5432/ai_tpm
ASYNC_DATABASE_URL=postgresql+asyncpg://postgres:12345@localhost:5432/ai_tpm

# JWT Auth
SECRET_KEY=your-secret-key-change-this-in-production

# Feature Flags
USE_PGVECTOR=False
USE_REDIS=False

# OpenAI (optional — local synthetic fallback works without it)
OPENAI_API_KEY=sk-...

# GitHub
GITHUB_WEBHOOK_SECRET=your_github_secret

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=your_slack_signing_secret

# Jira
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_api_token

# Google
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```
