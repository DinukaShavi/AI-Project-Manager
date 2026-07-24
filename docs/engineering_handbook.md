# Engineering Handbook: AI-Powered TPM

This handbook establishes the coding conventions, architectural boundaries, testing standards, and development pipelines for the AI-Powered Technical Project Manager (AI-TPM). 

To comply with project specifications, **no application code is generated**. Instead, this document provides the code standards and processes to guide implementation.

---

## 1. Directory & Naming Conventions

### Folder Structure Overview
* **Backend**: FastAPI modules must strictly segregate presentation (`api/`), business use cases (`services/`), persistence (`db/` / `crud/`), domain schemas (`schemas/`), and cognitive layers (`agents/` / `tools/`).
* **Frontend**: Next.js 15 App Router utilizes `/app` for file-based routing and page layouts, `/components` for visual building blocks, and `/hooks` for state hooks.

### Naming Conventions

| Language/Asset | Context | Convention | Example |
| :--- | :--- | :--- | :--- |
| **Python** | Filenames | Lowercase Snake Case | `auth_service.py` |
| **Python** | Class names | PascalCase | `DatabaseConnector` |
| **Python** | Variables & Functions | Snake Case | `get_user_by_email()` |
| **TypeScript** | Components | PascalCase | `WorkspaceCard.tsx` |
| **TypeScript** | Utility files / hooks | Kebab Case | `use-websocket.ts` |
| **Database** | Tables & Columns | Snake Case, lowercase | `workflow_executions` |
| **Docker** | Images & Configs | Kebab Case, lowercase | `ai-tpm-backend` |

---

## 2. Clean Architecture & Dependency Injection Rules

The project enforces strict separation of concerns, ensuring core business logic remains independent of external frameworks:

```
  [Presentation: FastAPI Controllers] ──► [Dependency Injection Providers]
                                                    │
                                                    ▼ (Injects Services)
  [Business Logic: Services Layer]   ──► [Entities: Domain Schemas]
                                                    │
                                                    ▼ (Injects Repositories)
  [Data Access: CRUD / Databases]    ──► [External Infrastructure Interfaces]
```

### Dependency Rules
* **Inner circles cannot reference outer circles**. Domain schemas (`schemas/`) and entities (`models/`) must not import database session managers or API routing frameworks.
* **Stateless Services**: Service classes must be stateless. They accept database sessions or adapters via dependency injection on every call.

### Dependency Injection (DI) in FastAPI
* Use FastAPI's native `Depends()` provider system to resolve database sessions, authenticated users, and external clients at the controller level:
  ```python
  # Conceptual DI usage:
  # async def create_task(task_in: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user))
  ```

### Repository Pattern (CRUD)
* Direct database queries using SQLAlchemy must not be written inside API routers or services.
* All queries must be encapsulated inside CRUD classes (in `app/crud/`) that implement simple database read/write interfaces.

---

## 3. Core Engine Implementation Rules

### Event Bus Rules
* **Outbox Pattern**: Updates to database models must be committed in the same transaction as their corresponding event records in the `events` outbox table.
* **Idempotent Consumers**: Event consumers must check the event ID cache in Redis before executing tasks to prevent duplicate processing.

### Agent Rules
* **Stateless Execution**: Agents must not maintain local execution state in memory. Every execution cycle must read state from the database and write results back before exiting.
* **Thought Logging**: Agents must write their reasoning steps and context logs to the `agent_executions` table during each run.

### Memory System Rules
* **Layer Segregation**: Ephemeral thought states belong in Redis (Short-term), user messages are saved in PostgreSQL (Conversation), and semantic memories are stored in pgvector (Project).
* **Summarization Triggers**: Conversation logs must be summarized when they exceed 8,000 tokens to keep prompt contexts within model limits.

### Tool Calling Rules
* **Schema Validation**: All tools must define input parameter constraints using Pydantic models.
* **Approval Gates**: Tools that perform write operations (e.g., merging code or deleting tickets) must register with `requires_approval = True`.

### Workflow Engine Rules
* **DAG Design**: Workflows must be configured as Directed Acyclic Graphs (DAGs) in JSON format.
* **Saga Rollbacks**: Each workflow node must define a compensating action to roll back changes if downstream steps fail.

---

## 4. Database & Migration Conventions

* **Primary Keys**: All tables must use randomly generated UUIDv4 values as primary keys.
* **Soft Delete**: Tables that track user data must use a `deleted_at` timestamp. Query filters must check for null values to exclude soft-deleted records.
* **Timezones**: All timestamp columns must use `TIMESTAMP WITH TIME ZONE` (UTC).
* **Migrations (Alembic)**:
  * Auto-generated migrations must be reviewed before deployment to verify constraints and indexes.
  * Migrations must support both upgrade (`upgrade()`) and rollback (`downgrade()`) paths.
  * Adding columns to high-volume tables must specify a default value or run in batches to prevent database locks.

---

## 5. Logging, Error Handling & Validation

### Logging Standards
* Use structured JSON logging format.
* Sensitive personal data (such as emails, tokens, and passwords) must be masked before logging.
* Log levels:
  * `DEBUG`: Logs tool arguments, database queries, and raw events.
  * `INFO`: Logs agent transitions, workflow completions, and API accesses.
  * `WARNING`: Logs failed login attempts, tool execution retries, and API rate limits.
  * `ERROR`: Logs DB failures, unhandled exceptions, and API outages.

### Error Handling Standard
* API errors must return the RFC 7807 problem details schema.
* Use structured Python exceptions (e.g., `ValidationError`, `PermissionError`, `DatabaseConnectionError`) and map them to HTTP status codes at the controller layer.

### Validation Rules
* **Request Validation**: FastAPI routes validate request inputs using Pydantic models.
* **Frontend Validation**: Forms validate fields on submission using client-side libraries (e.g., Zod) before making API calls.

---

## 6. Testing Standards

```
        [Testing Pyramid]
               ▲
              ╱ ╲
             ╱E2E╲     (Playwright UI tests)
            ╱─────╲
           ╱Contra╲    (Pact contract validation)
          ╱────────╲
         ╱Integrat.╲   (Pytest HTTP endpoints client)
        ╱───────────╲
       ╱   Unit      ╲ (Mocked services, isolated logic)
      └───────────────┘
```

* **Unit Testing**: Tests isolate logic by mocking external calls, databases, and APIs. Target code coverage: $> 85\%$.
* **Integration Testing**: Runs end-to-end tests against real PostgreSQL, Redis, and Celery containers.
* **Contract Testing**: Verifies API endpoints against the frontend consumer schema to prevent breaking changes.
* **E2E Testing**: Runs simulated user workflows using Playwright to test the full stack from login to dashboard update.

---

## 7. Performance & Security Requirements

### Performance Margins
* **API Response Time**: Reads must return in $< 150\text{ms}$; writes must return in $< 200\text{ms}$ (excluding asynchronous processing).
* **WebSocket Ingestion**: Real-time broadcasts must deliver messages to connected clients within $< 50\text{ms}$ of database commit.
* **Agent Latency**: An agent reasoning cycle (single node run) must compile and dispatch in $< 5\text{s}$ (excluding LLM API latency).

### Security Baselines
* **OAuth Encryptions**: Access tokens must be encrypted using AES-256-GCM before database insertion.
* **Tenant Isolation**: Row-Level Security (RLS) must be enabled on all tenant-specific tables to enforce database boundaries.
* **Rate Limits**: Rate limits are enforced per tenant (e.g., 100 requests per minute) and per user (e.g., 20 requests per minute) using Redis token buckets.

---

## 8. Code Quality & Git Pipelines

### Git Branching Strategy
* The project uses **Trunk-Based Development** with short-lived feature branches.
* Branch naming: `feature/short-description`, `bugfix/issue-key`, `chore/task-name`.

### Commit Message Conventions (Conventional Commits)
* Format: `<type>(<scope>): <subject>`
  * `feat(auth): add PKCE support to Google login`
  * `fix(db): add index on event timestamp to improve query speeds`
  * `docs(readme): update setup instructions`

### Pull Request Template
```markdown
## Goal / Description
Brief describe the purpose of this change.

## Changes
- List key modifications.

## Verification
- Paste test command outputs or link to manual verification screenshots.

## Checklist
- [ ] Code follows architectural boundaries.
- [ ] Unit tests are written and passing.
- [ ] Database migrations include a downgrade path (if applicable).
```

### Definition of Done (DoD)
A task is considered complete when:
1. Code meets style guidelines, and linting checks pass.
2. Unit and integration tests pass.
3. API endpoints are documented in the OpenAPI schema.
4. Database migrations are generated and tested (upgrade/downgrade).
5. The pull request is reviewed and approved by at least one engineer.
6. The changes are deployed and verified in the staging environment.

---

## 9. Architectural Decision Records (ADR) Process

We use Architectural Decision Records to track key technical choices:
* **Record Structure**: ADRs are stored as markdown files under `docs/adr/`.
* **ADR Template**:
  ```markdown
  # ADR [Number]: [Title]
  
  ## Context
  Describe the problem we are solving and the options considered.
  
  ## Decision
  State the chosen solution.
  
  ## Consequences
  Detail the impacts (both positive and negative) of the decision.
  ```
* **ADR Workflow**:
  1. Create a draft ADR.
  2. Discuss options with the team.
  3. Merge the ADR branch once a decision is finalized.
