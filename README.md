# AI-Powered Technical Project Manager (AI-TPM)

This is an enterprise-grade, event-driven, context-centric autonomous system designed to monitor engineering projects in real-time across GitHub, Jira, Slack, and Google Calendar, coordinated by a multi-agent system.

## Project Structure

```
.
├── backend/            # FastAPI app + Celery Workers + Agents
├── frontend/           # Next.js 15 App Router
├── infrastructure/     # Terraform scripts + deployment manifests
├── docs/               # System documentation & ADRs
└── scripts/            # Database backups and management scripts
```

## Running the Application Locally (Phase 0)

1. Copy the environment configuration template:
   ```bash
   cp .env.example .env
   ```
2. Build and spin up the multi-container stack:
   ```bash
   docker compose up --build
   ```
3. Verify backend health check endpoint:
   ```bash
   curl http://localhost:8000/health
   ```
4. Access the frontend dashboard at `http://localhost:3000`.
